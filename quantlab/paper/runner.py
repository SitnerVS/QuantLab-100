from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pandas as pd

from quantlab.paper.engine import apply_paper_signal, new_account
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
    if filename.startswith("forex_"):
        return "forex_spot_sim"
    return None


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
    state.setdefault("schema_version", 2)
    state.setdefault("accounts", {})
    paths = sorted(p for p in RAW.glob("*.csv") if _dataset_sleeve(p.name))
    state.setdefault("unsupported_sleeves", {
        "crypto_futures_sim": "disabled_until_futures_margin_engine_is_validated",
        "forex_leveraged_sim": "disabled_until_leverage_and_margin_engine_is_validated",
    })

    paths = sorted(p for p in RAW.glob("*.csv") if _dataset_sleeve(p.name))
    counts = {"crypto_spot": 0, "forex_spot_sim": 0}
    for path in paths:
        sleeve = _dataset_sleeve(path.name)
        counts[sleeve] += 1
    events = []
    snapshots = []

    for path in paths:
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
                allocation = sleeve_capital / max(1, counts[sleeve])
                account = new_account(allocation)

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
                "close": float(latest["close"]),
                "signal": signal,
                "cash": float(account["cash"]),
                "quantity": float(account["quantity"]),
                "equity": equity,
                "realized_pnl": float(account["realized_pnl"]),
                "unrealized_pnl": (
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
    print(f"Paper engine: {len(snapshots)} accounts scanned; {sum(e.get('status') in ('buy', 'sell') for e in events)} fills; no real orders.")
