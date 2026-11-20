from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math

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





def _unprocessed_signal_rows(enriched, last_bar):
    """Return every completed bar after the persisted cursor, with its prior-bar signal."""
    if len(enriched) < 2:
        return []
    time_col = next((c for c in ("timestamp", "datetime", "date") if c in enriched.columns), None)
    if time_col is None:
        return [(len(enriched) - 1, int(enriched.iloc[-2]["ema_signal"]))]
    timestamps = pd.to_datetime(enriched[time_col], utc=True, errors="coerce")
    latest_index = len(enriched) - 1
    if not last_bar:
        indices = [latest_index]
    else:
        previous = pd.to_datetime(last_bar, utc=True, errors="coerce")
        if pd.isna(previous):
            indices = [latest_index]
        elif previous < timestamps.iloc[0]:
            print("[paper] State cursor is older than retained history; processing only the latest available candle.")
            indices = [latest_index]
        else:
            indices = [
                index for index in range(1, len(enriched))
                if pd.notna(timestamps.iloc[index]) and timestamps.iloc[index] > previous
            ]
    return [
        (index, int(enriched.iloc[index - 1]["ema_signal"]))
        for index in indices
        if index > 0
    ]


def _process_account_bars(cfg, account, enriched, sleeve, key, usd_rub_rate, experiment, ignore_venue_minimums=False):
    continuous_mode = bool(cfg.get("paper", {}).get("continuous_mode", False))
    pending = (
        []
        if experiment["status"] == "COMPLETED" and not continuous_mode
        else _unprocessed_signal_rows(enriched, account.get("last_bar"))
    )
    account_events = []
    for index, signal in pending:
        latest = enriched.iloc[index].copy()
        latest["paper_signal"] = signal
        bar_time = pd.to_datetime(
            latest.get("timestamp", latest.get("datetime", latest.get("date"))),
            utc=True,
        ).isoformat()
        if sleeve == "crypto_futures_sim":
            futures_cfg = cfg["futures"]
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
                min_order_size=(
                    0.0 if ignore_venue_minimums
                    else float(latest.get("min_order_size", 0.0))
                ),
                min_notional_usd=(
                    0.0 if ignore_venue_minimums
                    else float(latest.get("min_notional_usd", 0.0))
                ),
            )
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
                min_order_size=(
                    0.0 if ignore_venue_minimums
                    else float(latest.get("min_order_size", 0.0)) if sleeve == "crypto_spot" else 0.0
                ),
                min_notional=(
                    0.0 if ignore_venue_minimums
                    else float(latest.get("min_notional_usd", 0.0)) if sleeve == "crypto_spot" else 0.0
                ),
            )
        event["backfilled"] = index < len(enriched) - 1
        account_events.append(event)

    if pending:
        final_index, final_signal = pending[-1]
    else:
        final_index = len(enriched) - 1
        final_signal = _paper_signal_for_latest(enriched)
    latest = enriched.iloc[final_index].copy()
    latest["paper_signal"] = int(final_signal or 0)
    bar_time = pd.to_datetime(
        latest.get("timestamp", latest.get("datetime", latest.get("date"))),
        utc=True,
    ).isoformat()

    if sleeve == "crypto_futures_sim":
        futures_cfg = cfg["futures"]
        snapshot = _snapshot_futures(
            account, latest, sleeve, key, bar_time,
            float(account.get("initial_capital_rub", 0.0)), usd_rub_rate,
            leverage=float(futures_cfg["leverage"]),
            max_margin_fraction=float(futures_cfg["max_margin_fraction"]),
        )
    else:
        snapshot = _snapshot_spot(
            account, latest, sleeve, key, bar_time,
            float(account.get("initial_capital_rub", 0.0)), usd_rub_rate,
            max_position_fraction=float(cfg.get("paper", {}).get("max_position_fraction", 1.0)),
        )
    if ignore_venue_minimums:
        snapshot["execution_model"] = "fractional_shadow_ignore_venue_minimums"
        snapshot["venue_minimums_ignored"] = True
    else:
        snapshot["venue_minimums_ignored"] = False
    if experiment["status"] == "COMPLETED" and not continuous_mode:
        account_events.append({"timestamp": bar_time, "status": "experiment_completed"})
    return account, account_events, snapshot


def _run_fractional_shadow(cfg, paths, counts, accounts, experiment, usd_rub_rate, now):
    """Run a separate non-executable fractional-lot research portfolio."""
    events = []
    snapshots = []
    for path in paths:
        sleeve = _dataset_sleeve(path.name)
        if sleeve is None or counts.get(sleeve, 0) <= 0:
            continue
        try:
            frame = pd.read_csv(path)
            frame.columns = [str(col).lower() for col in frame.columns]
            required = {"open", "high", "low", "close", "volume"}
            if sleeve == "crypto_futures_sim":
                required.add("funding_rate")
            if not required.issubset(frame.columns) or len(frame) < 60:
                continue

            latest_result = _latest_closed_bar(frame, path.name, cfg, now)
            if latest_result is None:
                continue
            _, closed_frame = latest_result
            enriched = build_signals(closed_frame)
            if len(enriched) < 2:
                continue

            key = path.stem
            account = accounts.get(key)
            if account is None:
                if experiment["status"] == "COMPLETED" and not bool(cfg.get("paper", {}).get("continuous_mode", False)):
                    continue
                sleeve_capital = float(cfg["capital"]["portfolios"][sleeve])
                allocation_rub = sleeve_capital / max(1, counts[sleeve])
                allocation_usd = rub_to_usd(allocation_rub, usd_rub_rate)
                account = (
                    new_futures_account(allocation_usd)
                    if sleeve == "crypto_futures_sim"
                    else new_account(allocation_usd)
                )
                account["initial_capital_rub"] = allocation_rub

            account, account_events, snapshot = _process_account_bars(
                cfg, account, enriched, sleeve, key, usd_rub_rate, experiment,
                ignore_venue_minimums=True,
            )
            accounts[key] = account
            events.extend({"dataset": key, "sleeve": sleeve, **event} for event in account_events)
            snapshots.append(snapshot)
        except Exception as exc:
            print(f"[fractional shadow] ERROR {path.name}: {exc}")
    return events, snapshots



def _write_experiment_status_report(venue_summary, fractional_summary):
    """Write a concise, human-readable view of execution and research status."""
    venue = venue_summary.iloc[0].to_dict()
    fractional = fractional_summary.iloc[0].to_dict()

    def number(row, key, default=0.0):
        value = row.get(key, default)
        return float(value) if pd.notna(value) else float(default)

    lines = [
        "# QuantLab 100 — experiment status",
        "",
        f"Updated (UTC): {venue.get('timestamp_utc', 'unknown')}",
        f"Experiment: {venue.get('experiment_id', 'unknown')} — {venue.get('experiment_status', 'unknown')}",
        f"Window: {venue.get('experiment_start_utc', 'unknown')} → {venue.get('experiment_end_utc', 'unknown')}",
        f"Elapsed: {number(venue, 'experiment_elapsed_hours'):.2f} h; remaining: {number(venue, 'experiment_remaining_hours'):.2f} h",
        "",
        "## Target",
        "",
        f"- Starting capital: {number(venue, 'total_initial_capital_rub'):.2f} RUB",
        f"- Target equity: {number(venue, 'target_equity_rub'):.2f} RUB",
        f"- Current venue-constrained equity: {number(venue, 'total_equity_rub_estimate'):.4f} RUB",
        f"- Target progress: {number(venue, 'target_progress_pct'):.4f}%",
        f"- Required compound return to reach the target in 72 hours: {number(venue, 'target_required_hourly_return_pct'):.4f}% per hour",
        "",
        "## Venue-constrained paper portfolio",
        "",
        f"- Equity: {number(venue, 'total_equity_rub_estimate'):.4f} RUB; total return: {number(venue, 'total_return_pct'):+.5f}%",
        f"- Active capital: {number(venue, 'active_initial_capital_rub'):.2f} RUB; idle capital: {number(venue, 'inactive_capital_rub'):.2f} RUB",
        f"- Capital blocked by venue minimum lots: {number(venue, 'minimum_lot_blocked_capital_rub'):.2f} RUB",
        f"- Lowest configured crypto minimum-order capital: {number(venue, 'lowest_crypto_min_order_capital_rub'):.2f} RUB; budget shortfall: {max(0.0, number(venue, 'lowest_crypto_min_order_capital_rub') - number(venue, 'total_initial_capital_rub')):.2f} RUB",
        f"- Fills this run: {int(number(venue, 'fills_this_run'))}; open positions: {int(number(venue, 'open_positions'))}; closed trades: {int(number(venue, 'closed_trades'))}",
        f"- Cumulative rejected minimum-size orders: {int(number(venue, 'rejected_min_size_total'))}; new rejections this run: {int(number(venue, 'rejected_orders_this_run'))}",
        "",
        "## Fractional shadow portfolio — NON-EXECUTABLE",
        "",
        "This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.",
        "",
        f"- Equity: {number(fractional, 'total_equity_rub_estimate'):.4f} RUB; total return: {number(fractional, 'total_return_pct'):+.5f}%",
        f"- Active return: {number(fractional, 'active_return_pct'):+.5f}%; fills this run: {int(number(fractional, 'fills_this_run'))}; open positions: {int(number(fractional, 'open_positions'))}; closed trades: {int(number(fractional, 'closed_trades'))}",
        f"- Fees paid: {number(fractional, 'fees_paid_usd'):.8f} USD; funding paid (net sign as recorded): {number(fractional, 'funding_paid_usd'):.8f} USD",
        f"- Liquidations: {int(number(fractional, 'liquidations'))}",
        "",
        "## Historical out-of-sample research",
        "",
        "The tables below are exploratory rankings of fixed strategy rules on chronological test folds. They are not forecasts and do not automatically activate a strategy.",
    ]

    for label, filename in (
        ("Spot / FX proxy", "walk_forward_ranking.csv"),
        ("Crypto futures", "futures_walk_forward_ranking.csv"),
    ):
        path = REPORTS / filename
        if not path.exists():
            continue
        ranking = pd.read_csv(path)
        if ranking.empty:
            continue
        top = ranking.sort_values("median_test_return_pct", ascending=False).head(3)
        lines.extend([
            "",
            f"### {label}",
            "",
            "| Dataset | Strategy | Median OOS return | Positive folds | Folds |",
            "|---|---|---:|---:|---:|",
        ])
        for _, row in top.iterrows():
            lines.append(
                f"| {row['dataset']} | {row['strategy']} | "
                f"{float(row['median_test_return_pct']):+.4f}% | "
                f"{float(row['positive_fold_pct']):.1f}% | {int(row['folds'])} |"
            )

    statistical_path = REPORTS / "statistical_validation.csv"
    if statistical_path.exists():
        statistical = pd.read_csv(statistical_path)
        if not statistical.empty and "holm_adjusted_p_value" in statistical:
            best_adjusted_p = float(statistical["holm_adjusted_p_value"].min())
            lines.extend([
                "",
                f"Minimum Holm-adjusted p-value across tested dataset/strategy combinations: {best_adjusted_p:.4f}.",
                "No tested strategy passes the 5% family-wise significance threshold."
                if best_adjusted_p >= 0.05
                else "At least one tested strategy passes the 5% family-wise significance threshold; it still requires independent validation.",
            ])

    lines.extend([
        "",
        "---",
        "",
        "Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.",
    ])
    (REPORTS / "experiment_status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _portfolio_target_metrics(
    active_equity_rub,
    inactive_capital_rub,
    total_capital_rub,
    target_equity_rub=10000.0,
    duration_hours=72.0,
):
    """Include idle cash in total equity and quantify the target's required pace."""
    values = [active_equity_rub, inactive_capital_rub, total_capital_rub, target_equity_rub, duration_hours]
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in values):
        raise ValueError("portfolio amounts and target must be finite and non-negative")
    if total_capital_rub <= 0 or target_equity_rub <= 0 or duration_hours <= 0:
        raise ValueError("total capital, target equity and duration must be positive")
    total_equity = float(active_equity_rub) + float(inactive_capital_rub)
    return {
        "total_equity_rub_estimate": total_equity,
        "total_return_pct": (total_equity / float(total_capital_rub) - 1.0) * 100.0,
        "target_progress_pct": total_equity / float(target_equity_rub) * 100.0,
        "target_required_hourly_return_pct": (
            (float(target_equity_rub) / float(total_capital_rub)) ** (1.0 / float(duration_hours)) - 1.0
        ) * 100.0,
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
            _, closed_frame = latest_result
            enriched = build_signals(closed_frame)
            if len(enriched) < 2:
                print(f"[paper] SKIP {path.name}: insufficient bars for lagged signal")
                continue

            key = path.stem
            account = state["accounts"].get(key)
            if account is None:
                if experiment["status"] == "COMPLETED" and not bool(cfg.get("paper", {}).get("continuous_mode", False)):
                    continue
                sleeve_capital = float(cfg["capital"]["portfolios"][sleeve])
                allocation_rub = sleeve_capital / max(1, counts[sleeve])
                allocation_usd = rub_to_usd(allocation_rub, usd_rub_rate)
                if sleeve == "crypto_futures_sim":
                    account = new_futures_account(allocation_usd)
                else:
                    account = new_account(allocation_usd)
                account["initial_capital_rub"] = allocation_rub

            account, account_events, snapshot = _process_account_bars(
                cfg, account, enriched, sleeve, key, usd_rub_rate, experiment,
                ignore_venue_minimums=False,
            )
            state["accounts"][key] = account
            events.extend({"dataset": key, "sleeve": sleeve, **event} for event in account_events)
            snapshots.append(snapshot)
        except Exception as exc:
            print(f"[paper] ERROR {path.name}: {exc}")

    state.setdefault("fractional_accounts", {})
    fractional_events, fractional_snapshots = _run_fractional_shadow(
        cfg, paths, counts, state["fractional_accounts"], experiment, usd_rub_rate, now
    )

    state["updated_at"] = now.isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(events).to_csv(REPORTS / "paper_events_latest.csv", index=False)
    pd.DataFrame(snapshots).to_csv(REPORTS / "paper_portfolio_latest.csv", index=False)
    pd.DataFrame(fractional_events).to_csv(REPORTS / "paper_fractional_events_latest.csv", index=False)
    pd.DataFrame(fractional_snapshots).to_csv(REPORTS / "paper_fractional_portfolio_latest.csv", index=False)

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
    inactive_capital_rub = max(0.0, total_capital_rub - active_initial_rub)
    target_equity_rub = 10000.0
    target_metrics = _portfolio_target_metrics(
        total_equity_rub,
        inactive_capital_rub,
        total_capital_rub,
        target_equity_rub=target_equity_rub,
        duration_hours=72.0,
    )
    summary = pd.DataFrame([{
        "timestamp_utc": now.isoformat(),
        "experiment_id": state["experiment_id"],
        "experiment_start_utc": experiment["start_utc"],
        "experiment_end_utc": experiment["end_utc"],
        "experiment_elapsed_hours": experiment["elapsed_hours"],
        "experiment_remaining_hours": experiment["remaining_hours"],
        "experiment_status": "CONTINUOUS_PAPER" if bool(cfg.get("paper", {}).get("continuous_mode", False)) else experiment["status"],
        "benchmark_status": experiment["status"],
        "target_equity_rub": target_equity_rub,
        "total_initial_capital_rub": total_capital_rub,
        "execution_mode": "venue_constrained",
        "venue_minimums_ignored": False,
        **target_metrics,
        "base_currency": "RUB",
        "usd_rub_rate": usd_rub_rate,
        "usd_rub_rate_timestamp_utc": fx_timestamp,
        "active_initial_capital_rub": active_initial_rub,
        "inactive_capital_rub": inactive_capital_rub,
        "minimum_lot_blocked_capital_rub": minimum_lot_blocked_rub,
        "capital_not_blocked_by_crypto_minimums_rub": max(0.0, active_initial_rub - minimum_lot_blocked_rub),
        "fx_proxy_capital_rub": fx_proxy_capital_rub,
        "lowest_crypto_min_order_capital_rub": min(crypto_min_capital_requirements) if crypto_min_capital_requirements else 0.0,
        "active_equity_rub_estimate": total_equity_rub,
        "active_return_pct": ((total_equity_rub / active_initial_rub) - 1.0) * 100.0 if active_initial_rub else 0.0,
        "realized_pnl_rub_estimate": sum(float(row["realized_pnl_rub_estimate"]) for row in snapshots),
        "unrealized_pnl_rub_estimate": sum(float(row["unrealized_pnl_usd"]) * usd_rub_rate for row in snapshots),
        "fees_paid_usd": sum(float(row.get("fees_paid_usd", 0.0)) for row in snapshots),
        "funding_paid_usd": sum(float(row.get("funding_paid_usd", 0.0)) for row in snapshots),
        "liquidations": sum(int(row.get("liquidations", 0)) for row in snapshots),
        "rejected_min_size_total": sum(int(row.get("rejected_min_size", 0)) for row in snapshots),
        "accounts": len(snapshots),
        "open_positions": sum(float(row.get("quantity", 0.0)) > 0 for row in snapshots),
        "cumulative_trade_count": sum(int(row.get("trade_count", 0)) for row in snapshots),
        "closed_trades": sum(int(row.get("closed_trades", 0)) for row in snapshots),
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

    fractional_active_initial_rub = sum(row["initial_capital_rub"] for row in fractional_snapshots)
    fractional_active_equity_rub = sum(row["equity_rub_estimate"] for row in fractional_snapshots)
    fractional_inactive_capital_rub = max(0.0, total_capital_rub - fractional_active_initial_rub)
    fractional_target_metrics = _portfolio_target_metrics(
        fractional_active_equity_rub,
        fractional_inactive_capital_rub,
        total_capital_rub,
        target_equity_rub=target_equity_rub,
        duration_hours=72.0,
    )
    fractional_minimum_blocked_rub = sum(
        float(row["initial_capital_rub"])
        for row in fractional_snapshots
        if row["sleeve"] in ("crypto_spot", "crypto_futures_sim")
        and float(row["required_account_capital_rub_for_minimum_order"]) > float(row["initial_capital_rub"])
    )
    fractional_fx_proxy_capital_rub = sum(
        float(row["initial_capital_rub"])
        for row in fractional_snapshots
        if row["sleeve"] == "forex_spot_sim"
    )
    fractional_minimum_requirements = [
        float(row["required_account_capital_rub_for_minimum_order"])
        for row in fractional_snapshots
        if row["sleeve"] in ("crypto_spot", "crypto_futures_sim")
        and float(row["required_account_capital_rub_for_minimum_order"]) > 0
    ]
    fractional_summary = pd.DataFrame([{
        "timestamp_utc": now.isoformat(),
        "experiment_id": state["experiment_id"],
        "experiment_start_utc": experiment["start_utc"],
        "experiment_end_utc": experiment["end_utc"],
        "experiment_elapsed_hours": experiment["elapsed_hours"],
        "experiment_remaining_hours": experiment["remaining_hours"],
        "experiment_status": experiment["status"],
        "execution_mode": "fractional_shadow_non_executable",
        "execution_warning": "Fractional orders ignore venue minimums and cannot be placed at the venue.",
        "venue_minimums_ignored": True,
        "target_equity_rub": target_equity_rub,
        "total_initial_capital_rub": total_capital_rub,
        **fractional_target_metrics,
        "base_currency": "RUB",
        "usd_rub_rate": usd_rub_rate,
        "active_initial_capital_rub": fractional_active_initial_rub,
        "inactive_capital_rub": fractional_inactive_capital_rub,
        "minimum_lot_blocked_capital_rub": fractional_minimum_blocked_rub,
        "capital_not_blocked_by_crypto_minimums_rub": max(0.0, fractional_active_initial_rub - fractional_minimum_blocked_rub),
        "fx_proxy_capital_rub": fractional_fx_proxy_capital_rub,
        "lowest_crypto_min_order_capital_rub": min(fractional_minimum_requirements) if fractional_minimum_requirements else 0.0,
        "active_equity_rub_estimate": fractional_active_equity_rub,
        "active_return_pct": ((fractional_active_equity_rub / fractional_active_initial_rub) - 1.0) * 100.0 if fractional_active_initial_rub else 0.0,
        "realized_pnl_rub_estimate": sum(float(row["realized_pnl_rub_estimate"]) for row in fractional_snapshots),
        "unrealized_pnl_rub_estimate": sum(float(row["unrealized_pnl_usd"]) * usd_rub_rate for row in fractional_snapshots),
        "fees_paid_usd": sum(float(row.get("fees_paid_usd", 0.0)) for row in fractional_snapshots),
        "funding_paid_usd": sum(float(row.get("funding_paid_usd", 0.0)) for row in fractional_snapshots),
        "liquidations": sum(int(row.get("liquidations", 0)) for row in fractional_snapshots),
        "rejected_min_size_total": sum(int(row.get("rejected_min_size", 0)) for row in fractional_snapshots),
        "accounts": len(fractional_snapshots),
        "open_positions": sum(float(row.get("quantity", 0.0)) > 0 for row in fractional_snapshots),
        "cumulative_trade_count": sum(int(row.get("trade_count", 0)) for row in fractional_snapshots),
        "closed_trades": sum(int(row.get("closed_trades", 0)) for row in fractional_snapshots),
        "fills_this_run": sum(
            event.get("status") in ("buy", "sell", "open", "close", "liquidation")
            for event in fractional_events
        ),
        "real_orders": False,
    }])
    fractional_summary.to_csv(REPORTS / "paper_fractional_portfolio_summary.csv", index=False)
    _write_experiment_status_report(summary, fractional_summary)
    print(
        f"Paper engine: {len(snapshots)} accounts scanned; "
        f"{sum(event.get('status') in ('buy', 'sell', 'open', 'close', 'liquidation') for event in events)} fills/events; "
        "no real orders."
    )
