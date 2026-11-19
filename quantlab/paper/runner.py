from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pandas as pd

from quantlab.paper.engine import apply_paper_signal, new_account, rub_to_usd
from quantlab.futures.engine import apply_isolated_futures_signal, new_futures_account
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
    if filename.startswith("futures_"):
        return "crypto_futures_sim"
    if filename.startswith("crypto_"):
        return "crypto_spot"
    if filename.startswith("forex_") and ("EURUSD=X" in filename or "GBPUSD=X" in filename):
        return "forex_spot_sim"
    return None


def _paper_signal_for_latest(enriched, signal_col="ema_signal"):
    """Use the previous completed bar's signal for the current bar's close proxy."""
    if len(enriched) < 2:
        return None
    return int(enriched.iloc[-2][signal_col])


def _experiment_window(created_at, now, duration_hours=72):
    start = pd.to_datetime(created_at, utc=True).to_pydatetime()
    end = start + timedelta(hours=duration_hours)
    elapsed = max(0.0, (now - start).total_seconds() / 3600.0)
    remaining = max(0.0, (end - now).total_seconds() / 3600.0)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "elapsed_hours": elapsed,
        "remaining_hours": remaining,
        "status": "RUNNING" if now < end else "COMPLETED",
    }


def _latest_usd_rub_rate(cfg, now):
    quality_path = REPORTS / "data_quality.csv"
    if not quality_path.exists():
        raise RuntimeError("data quality report is missing")
    quality = pd.read_csv(quality_path)
    fx_status = quality.loc[quality["dataset"] == "forex_RUB=X_1d.csv", "status"]
    if fx_status.empty or fx_status.iloc[0] != "OK":
        raise RuntimeError("USD/RUB conversion data is not fresh and valid")
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
    if filename.startswith("futures_"):
        timeframe = cfg["data"]["futures"].get("timeframe", "1h")
    elif filename.startswith("crypto_"):
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
    clean = closed.drop(columns=["_bar_time"])
    return clean.iloc[-1], clean


def _snapshot_spot(account, latest, sleeve, key, bar_time, allocation_rub, usd_rub_rate, max_position_fraction=1.0):
    close = float(latest["close"])
    equity = float(account["cash"]) + float(account["quantity"]) * close
    unrealized = (
        float(account["quantity"]) * (close - float(account["position_entry_price"]))
        if account["quantity"] > 0 and account["position_entry_price"] is not None else 0.0
    )
    min_quantity = float(latest.get("min_order_size", 0.0) or 0.0)
    min_notional = float(latest.get("min_notional_usd", 0.0) or 0.0)
    required_capital_usd = max(min_quantity * close, min_notional) / max(float(max_position_fraction), 1e-12)
    return {
        "dataset": key,
        "sleeve": sleeve,
        "bar_time_utc": bar_time,
        "initial_capital_rub": float(account.get("initial_capital_rub", allocation_rub)),
        "close_or_mark": close,
        "signal": int(latest.get("paper_signal", 0)),
        "cash_usd": float(account["cash"]),
        "margin_balance_usd": 0.0,
        "quantity": float(account["quantity"]),
        "equity_usd": equity,
        "equity_rub_estimate": equity * usd_rub_rate,
        "usd_rub_rate": usd_rub_rate,
        "realized_pnl_usd": float(account["realized_pnl"]),
        "realized_pnl_rub_estimate": float(account["realized_pnl"]) * usd_rub_rate,
        "unrealized_pnl_usd": unrealized,
        "funding_paid_usd": 0.0,
        "fees_paid_usd": float(account.get("fees_paid", 0.0)),
        "rejected_min_size": int(account.get("rejected_min_size", 0)),
        "minimum_order_quantity": min_quantity,
        "minimum_order_notional_usd": min_notional,
        "required_account_capital_rub_for_minimum_order": required_capital_usd * usd_rub_rate,
        "liquidations": 0,
        "closed_trades": int(account["trade_count"] // 2),
        "trade_count": int(account["trade_count"]),
        "execution_model": "previous_bar_signal_current_completed_close_proxy",
    }


def _snapshot_futures(account, latest, sleeve, key, bar_time, allocation_rub, usd_rub_rate, leverage, max_margin_fraction):
    mark = float(latest["close"])
    position = account.get("position")
    quantity = float(position["quantity"]) if position is not None else 0.0
    margin_balance = float(position["margin_balance"]) if position is not None else 0.0
    unrealized = (
        quantity * (mark - float(position["entry_price"]))
        if position is not None else 0.0
    )
    equity = float(account["wallet"]) + margin_balance + unrealized
    min_quantity = float(latest.get("min_order_size", 0.0) or 0.0)
    required_capital_usd = (
        min_quantity * mark / (float(leverage) * float(max_margin_fraction))
        if min_quantity > 0 else 0.0
    )
    return {
        "dataset": key,
        "sleeve": sleeve,
        "bar_time_utc": bar_time,
        "initial_capital_rub": float(account.get("initial_capital_rub", allocation_rub)),
        "close_or_mark": mark,
        "signal": int(latest.get("paper_signal", 0)),
        "cash_usd": float(account["wallet"]),
        "margin_balance_usd": margin_balance,
        "quantity": quantity,
        "equity_usd": equity,
        "equity_rub_estimate": equity * usd_rub_rate,
        "usd_rub_rate": usd_rub_rate,
        "realized_pnl_usd": float(account["realized_pnl"]),
        "realized_pnl_rub_estimate": float(account["realized_pnl"]) * usd_rub_rate,
        "unrealized_pnl_usd": unrealized,
        "funding_paid_usd": float(account["funding_paid"]),
        "fees_paid_usd": float(account["fees_paid"]),
        "liquidations": int(account["liquidations"]),
        "rejected_min_size": int(account.get("rejected_min_size", 0)),
        "minimum_order_quantity": min_quantity,
        "minimum_order_notional_usd": min_quantity * mark,
        "required_account_capital_rub_for_minimum_order": required_capital_usd * usd_rub_rate,
        "closed_trades": int(account["closed_trades"]),
        "trade_count": int(account["closed_trades"] + account["liquidations"]),
        "execution_model": "previous_bar_signal_mark_close_proxy_observed_funding",
    }


def run_paper(cfg):
    REPORTS.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        state = {"created_at": now.isoformat(), "accounts": {}}

    # Reset pre-futures state and spot accounts after correcting signal timing.
    if int(state.get("schema_version", 1)) < 8:
        state["accounts"] = {}
        state["created_at"] = now.isoformat()
        state["experiment_id"] = "quantlab-100-paper-72h-v1"
    state["schema_version"] = 8
    state.setdefault("experiment_id", "quantlab-100-paper-72h-v1")
    state.setdefault("accounts", {})
    experiment = _experiment_window(state["created_at"], now, duration_hours=72)
    state["unsupported_sleeves"] = {
        "forex_leveraged_sim": "disabled_until_broker_grade_FX_margin_and_rollover_data_exists"
    }

    usd_rub_rate, fx_timestamp = _latest_usd_rub_rate(cfg, now)
    state["base_currency"] = "RUB"
    state["quote_currency"] = "USD"
    state["usd_rub_rate"] = usd_rub_rate
    state["usd_rub_timestamp_utc"] = fx_timestamp

    quality = pd.read_csv(REPORTS / "data_quality.csv")
    valid_names = set(quality.loc[quality["status"] == "OK", "dataset"].astype(str))
    paths = sorted(
        p for p in RAW.glob("*.csv")
        if _dataset_sleeve(p.name) and p.name in valid_names
    )
    counts = {
        "crypto_spot": 0,
        "crypto_futures_sim": 0,
        "forex_spot_sim": 0,
    }
    for path in paths:
        counts[_dataset_sleeve(path.name)] += 1

    events = []
    snapshots = []
    for path in paths:
        sleeve = _dataset_sleeve(path.name)
        try:
            frame = pd.read_csv(path)
            frame.columns = [str(col).lower() for col in frame.columns]
            required = {"open", "high", "low", "close", "volume"}
            if sleeve == "crypto_futures_sim":
                required.add("funding_rate")
            if not required.issubset(frame.columns) or len(frame) < 60:
                print(f"[paper] SKIP {path.name}: missing required columns or insufficient history")
                continue

            latest_result = _latest_closed_bar(frame, path.name, cfg, now)
            if latest_result is None:
                print(f"[paper] SKIP {path.name}: no completed candle yet")
                continue
            latest_row, closed_frame = latest_result
            enriched = build_signals(closed_frame)
            if len(enriched) < 2:
                print(f"[paper] SKIP {path.name}: insufficient bars for lagged signal")
                continue
            latest = enriched.iloc[-1].copy()
            signal = _paper_signal_for_latest(enriched)
            latest["paper_signal"] = signal

            key = path.stem
            account = state["accounts"].get(key)
            if account is None:
                if experiment["status"] == "COMPLETED":
                    continue
                sleeve_capital = float(cfg["capital"]["portfolios"][sleeve])
                allocation_rub = sleeve_capital / max(1, counts[sleeve])
                allocation_usd = rub_to_usd(allocation_rub, usd_rub_rate)
                if sleeve == "crypto_futures_sim":
                    account = new_futures_account(allocation_usd)
                else:
                    account = new_account(allocation_usd)
                account["initial_capital_rub"] = allocation_rub

            bar_time = pd.to_datetime(
                latest_row.get("timestamp", latest_row.get("datetime", latest_row.get("date"))),
                utc=True,
            ).isoformat()

            if sleeve == "crypto_futures_sim":
                futures_cfg = cfg["futures"]
                if experiment["status"] == "COMPLETED":
                    event = {"timestamp": bar_time, "status": "experiment_completed"}
                else:
                    account, event = apply_isolated_futures_signal(
                        account,
                        signal,
                        float(latest["close"]),
                        float(latest["funding_rate"]),
                        bar_time,
                        leverage=float(futures_cfg["leverage"]),
                        max_margin_fraction=float(futures_cfg["max_margin_fraction"]),
                        fee_rate=float(futures_cfg["fee_rate"]),
                        slippage_rate=float(futures_cfg["slippage_rate"]),
                        spread_rate=float(futures_cfg["spread_rate"]),
                        maintenance_margin_rate=float(futures_cfg["maintenance_margin_rate"]),
                        liquidation_fee_rate=float(futures_cfg["liquidation_fee_rate"]),
                        min_order_size=float(latest["min_order_size"]),
                    )
                snapshot = _snapshot_futures(
                    account, latest, sleeve, key, bar_time,
                    float(account.get("initial_capital_rub", 0.0)), usd_rub_rate,
                    leverage=float(futures_cfg["leverage"]),
                    max_margin_fraction=float(futures_cfg["max_margin_fraction"]),
                )
            else:
                if experiment["status"] == "COMPLETED":
                    event = {"timestamp": bar_time, "status": "experiment_completed"}
                else:
                    costs = cfg["costs"]
                    account, event = apply_paper_signal(
                        account,
                        signal,
                        float(latest["close"]),
                        bar_time,
                        fee_rate=float(costs["crypto_fee_rate"] if sleeve == "crypto_spot" else costs["forex_fee_rate"]),
                        slippage_rate=float(costs["slippage_rate"]),
                        spread_rate=float(costs.get("crypto_spread_rate" if sleeve == "crypto_spot" else "forex_spread_rate", 0.0)),
                        max_position_fraction=float(cfg.get("paper", {}).get("max_position_fraction", 1.0)),
                        min_order_size=float(latest.get("min_order_size", 0.0)) if sleeve == "crypto_spot" else 0.0,
                        min_notional=float(latest.get("min_notional_usd", 0.0)) if sleeve == "crypto_spot" else 0.0,
                    )
                snapshot = _snapshot_spot(
                    account, latest, sleeve, key, bar_time,
                    float(account.get("initial_capital_rub", 0.0)), usd_rub_rate,
                    max_position_fraction=float(cfg.get("paper", {}).get("max_position_fraction", 1.0)),
                )

            state["accounts"][key] = account
            events.append({"dataset": key, "sleeve": sleeve, **event})
            snapshots.append(snapshot)
        except Exception as exc:
            print(f"[paper] ERROR {path.name}: {exc}")

    state["updated_at"] = now.isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(events).to_csv(REPORTS / "paper_events_latest.csv", index=False)
    pd.DataFrame(snapshots).to_csv(REPORTS / "paper_portfolio_latest.csv", index=False)

    active_initial_rub = sum(row["initial_capital_rub"] for row in snapshots)
    total_equity_rub = sum(row["equity_rub_estimate"] for row in snapshots)
    minimum_lot_blocked_rub = sum(
        float(account.get("initial_capital_rub", 0.0))
        for key, account in state["accounts"].items()
        if (key.startswith("futures_") or key.startswith("crypto_"))
        and int(account.get("rejected_min_size", 0)) > 0
        and (
            account.get("position") is None
            if key.startswith("futures_")
            else float(account.get("quantity", 0.0)) <= 0
        )
    )
    fx_proxy_capital_rub = sum(
        float(account.get("initial_capital_rub", 0.0))
        for key, account in state["accounts"].items()
        if key.startswith("forex_")
    )
    crypto_min_capital_requirements = [
        float(row["required_account_capital_rub_for_minimum_order"])
        for row in snapshots
        if row["sleeve"] in ("crypto_spot", "crypto_futures_sim")
        and float(row["required_account_capital_rub_for_minimum_order"]) > 0
    ]
    total_capital_rub = float(cfg["capital"]["total_rub"])
    summary = pd.DataFrame([{
        "timestamp_utc": now.isoformat(),
        "experiment_id": state["experiment_id"],
        "experiment_start_utc": experiment["start_utc"],
        "experiment_end_utc": experiment["end_utc"],
        "experiment_elapsed_hours": experiment["elapsed_hours"],
        "experiment_remaining_hours": experiment["remaining_hours"],
        "experiment_status": experiment["status"],
        "target_equity_rub": 10000.0,
        "target_progress_pct": total_equity_rub / 10000.0 * 100.0,
        "base_currency": "RUB",
        "usd_rub_rate": usd_rub_rate,
        "usd_rub_rate_timestamp_utc": fx_timestamp,
        "active_initial_capital_rub": active_initial_rub,
        "inactive_capital_rub": max(0.0, total_capital_rub - active_initial_rub),
        "minimum_lot_blocked_capital_rub": minimum_lot_blocked_rub,
        "capital_not_blocked_by_crypto_minimums_rub": max(0.0, active_initial_rub - minimum_lot_blocked_rub),
        "fx_proxy_capital_rub": fx_proxy_capital_rub,
        "lowest_crypto_min_order_capital_rub": min(crypto_min_capital_requirements) if crypto_min_capital_requirements else 0.0,
        "active_equity_rub_estimate": total_equity_rub,
        "active_return_pct": ((total_equity_rub / active_initial_rub) - 1.0) * 100.0 if active_initial_rub else 0.0,
        "accounts": len(snapshots),
        "fills_this_run": sum(
            event.get("status") in ("buy", "sell", "open", "close", "liquidation")
            for event in events
        ),
        "rejected_orders_this_run": sum(
            event.get("status") == "below_minimum_size" for event in events
        ),
        "real_orders": False,
    }])
    summary.to_csv(REPORTS / "paper_portfolio_summary.csv", index=False)
    print(
        f"Paper engine: {len(snapshots)} accounts scanned; "
        f"{sum(event.get('status') in ('buy', 'sell', 'open', 'close', 'liquidation') for event in events)} fills/events; "
        "no real orders."
    )
