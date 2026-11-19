from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pandas as pd

from quantlab.paper.engine import apply_paper_signal, new_account, rub_to_usd
from quantlab.strategies import build_signals

RAW = Path("data/raw")
REPORTS = Path("reports")
STATE = Path("data/processed/paper_state.json")

TIMEFRAME_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
    "1wk": 10080,
}


def _dataset_sleeve(filename):
    if filename.startswith("crypto_"):
        return "crypto_spot"
    if filename.startswith("forex_") and "EURUSD=X" in filename:
        return "forex_spot_sim"
    if filename.startswith("forex_") and "GBPUSD=X" in filename:
        return "forex_spot_sim"
    return None


def _latest_usd_rub_rate(cfg, now):
    path = RAW / "forex_RUB=X_1d.csv"
    if not path.exists():
        raise RuntimeError("USD/RUB conversion dataset forex_RUB=X_1d.csv is missing")
    frame = pd.read_csv(path)
    frame.columns = [str(col).lower() for col in frame.columns]
    result = _latest_closed_bar(frame, path.name, cfg, now)
    if result is None:
        raise RuntimeError("no completed USD/RUB conversion candle")
    row, _ = result
    rate = float(row["close"])
    if rate <= 0:
        raise RuntimeError("invalid USD/RUB conversion rate")
    return rate, pd.to_datetime(
        row.get("date", row.get("datetime", row.get("timestamp"))), utc=True
    ).isoformat()


def _bar_duration(filename, cfg):
    if filename.startswith("crypto_"):
        timeframe = cfg["data"]["crypto"].get("timeframe", "1h")
    else:
        timeframe = cfg["data"]["forex"].get("interval", "1d")
    return timedelta(minutes=TIMEFRAME_MINUTES.get(timeframe, 1440))


def _latest_closed_bar(frame, filename, cfg, now):
    time_col = next((c for c in ("timestamp", "datetime", "date") if c in frame.columns), None)
    if time_col is None:
        raise ValueError("dataset has no timestamp/date column; cannot prevent incomplete-bar trading")
    parsed = pd.to_datetime(frame[time_col], utc=True, errors="coerce")
    valid = parsed.notna()
    frame = frame.loc[valid].copy()
    frame["_bar_time"] = parsed.loc[valid]
    frame = frame.sort_values("_bar_time").drop_duplicates("_bar_time", keep="last")
    closed = frame.loc[frame["_bar_time"] + _bar_duration(filename, cfg) <= now]
    if closed.empty:
        return None
    return closed.drop(columns=["_bar_time"]).iloc[-1], closed.drop(columns=["_bar_time"])


def run_paper(cfg):
    REPORTS.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        state = {
            "schema_version": 2,
            "created_at": now.isoformat(),
            "accounts": {},
            "unsupported_sleeves": {
                "crypto_futures_sim": "disabled_until_futures_margin_engine_is_validated",
                "forex_leveraged_sim": "disabled_until_leverage_and_margin_engine_is_validated",
            },
        }

    # Backward-compatible state migration from the initial signal-only prototype.
    if int(state.get("schema_version", 1)) < 4:
        state["accounts"] = {}
    state["schema_version"] = 4
    state.setdefault("accounts", {})
    state.setdefault("unsupported_sleeves", {
        "crypto_futures_sim": "disabled_until_futures_margin_engine_is_validated",
        "forex_leveraged_sim": "disabled_until_leverage_and_margin_engine_is_validated",
    })

    usd_rub_rate, fx_timestamp = _latest_usd_rub_rate(cfg, now)
    state["base_currency"] = "RUB"
    state["quote_currency"] = "USD"
    state["usd_rub_rate"] = usd_rub_rate
    state["usd_rub_timestamp_utc"] = fx_timestamp

    paths = sorted(p for p in RAW.glob("*.csv") if _dataset_sleeve(p.name))
    counts = {"crypto_spot": 0, "forex_spot_sim": 0}
    for path in paths:
        sleeve = _dataset_sleeve(path.name)
        counts[sleeve] += 1
    events = []
    snapshots = []

    for path in paths:
        sleeve = _dataset_sleeve(path.name)
        try:
            frame = pd.read_csv(path)
            frame.columns = [str(col).lower() for col in frame.columns]
            required = {"open", "high", "low", "close", "volume"}
            if not required.issubset(frame.columns) or len(frame) < 60:
                print(f"[paper] SKIP {path.name}: missing OHLCV or insufficient history")
                continue

            latest_result = _latest_closed_bar(frame, path.name, cfg, now)
            if latest_result is None:
                print(f"[paper] SKIP {path.name}: no completed candle yet")
                continue
            latest_row, closed_frame = latest_result
            enriched = build_signals(closed_frame)
            latest = enriched.iloc[-1]
            key = path.stem
            account = state["accounts"].get(key)
            if account is None:
                sleeve_capital = float(cfg["capital"]["portfolios"][sleeve])
                allocation_rub = sleeve_capital / max(1, counts[sleeve])
                allocation_usd = rub_to_usd(allocation_rub, usd_rub_rate)
                account = new_account(allocation_usd)
                account["initial_capital_rub"] = allocation_rub

            signal = int(latest["ema_signal"])
            bar_time = pd.to_datetime(
                latest_row.get("timestamp", latest_row.get("datetime", latest_row.get("date"))),
                utc=True,
            ).isoformat()
            costs = cfg["costs"]
            account, event = apply_paper_signal(
                account,
                signal,
                float(latest["close"]),
                bar_time,
                fee_rate=float(costs["crypto_fee_rate"] if sleeve == "crypto_spot" else costs["forex_fee_rate"]),
                slippage_rate=float(costs["slippage_rate"]),
                spread_rate=float(costs.get("crypto_spread_rate" if sleeve == "crypto_spot" else "forex_spread_rate", 0.0)),
            )
            state["accounts"][key] = account
            events.append({"dataset": key, "sleeve": sleeve, **event})

            equity = float(account["cash"]) + float(account["quantity"]) * float(latest["close"])
            snapshots.append({
                "dataset": key,
                "sleeve": sleeve,
                "bar_time_utc": bar_time,
                "initial_capital_rub": float(account.get("initial_capital_rub", 0.0)),
                "close": float(latest["close"]),
                "signal": signal,
                "cash_usd": float(account["cash"]),
                "quantity": float(account["quantity"]),
                "equity_usd": equity,
                "equity_rub_estimate": equity * usd_rub_rate,
                "usd_rub_rate": usd_rub_rate,
                "realized_pnl_usd": float(account["realized_pnl"]),
                "realized_pnl_rub_estimate": float(account["realized_pnl"]) * usd_rub_rate,
                "unrealized_pnl_usd": (
                    float(account["quantity"]) * (float(latest["close"]) - float(account["position_entry_price"]))
                    if account["quantity"] > 0 and account["position_entry_price"] is not None else 0.0
                ),
                "trade_count": int(account["trade_count"]),
                "execution_model": "completed_bar_close_proxy_with_fee_spread_slippage",
            })
        except Exception as exc:
            print(f"[paper] ERROR {path.name}: {exc}")

    state["updated_at"] = now.isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(events).to_csv(REPORTS / "paper_events_latest.csv", index=False)
    pd.DataFrame(snapshots).to_csv(REPORTS / "paper_portfolio_latest.csv", index=False)

    active_initial_rub = sum(row["initial_capital_rub"] for row in snapshots)
    total_equity_rub = sum(row["equity_rub_estimate"] for row in snapshots)
    total_capital_rub = float(cfg["capital"]["total_rub"])
    summary = pd.DataFrame([{
        "timestamp_utc": now.isoformat(),
        "base_currency": "RUB",
        "usd_rub_rate": usd_rub_rate,
        "usd_rub_rate_timestamp_utc": fx_timestamp,
        "active_initial_capital_rub": active_initial_rub,
        "inactive_capital_rub": max(0.0, total_capital_rub - active_initial_rub),
        "active_equity_rub_estimate": total_equity_rub,
        "active_return_pct": ((total_equity_rub / active_initial_rub) - 1.0) * 100.0 if active_initial_rub else 0.0,
        "accounts": len(snapshots),
        "fills_this_run": sum(e.get("status") in ("buy", "sell") for e in events),
        "real_orders": False,
    }])
    summary.to_csv(REPORTS / "paper_portfolio_summary.csv", index=False)
    print(f"Paper engine: {len(snapshots)} accounts scanned; {sum(e.get('status') in ('buy', 'sell') for e in events)} fills; no real orders.")
