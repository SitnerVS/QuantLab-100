import pandas as pd
import pytest

from quantlab.paper.engine import apply_paper_signal, new_account, rub_to_usd
from quantlab.paper.runner import (
    _dataset_sleeve, _paper_signal_for_latest, _experiment_window,
    _portfolio_target_metrics, _run_fractional_shadow,
    _write_experiment_status_report, _unprocessed_signal_rows,
    _process_account_bars,
)


def test_buy_and_sell_updates_cash_and_realized_pnl():
    account = new_account(25)
    account, buy = apply_paper_signal(
        account, 1, 100, "2026-01-01T00:00:00+00:00",
        fee_rate=0, slippage_rate=0, spread_rate=0,
    )
    assert buy["status"] == "buy"
    assert account["cash"] == pytest.approx(0)
    assert account["quantity"] == pytest.approx(0.25)

    account, sell = apply_paper_signal(
        account, 0, 110, "2026-01-01T01:00:00+00:00",
        fee_rate=0, slippage_rate=0, spread_rate=0,
    )
    assert sell["status"] == "sell"
    assert account["cash"] == pytest.approx(27.5)
    assert account["realized_pnl"] == pytest.approx(2.5)
    assert account["quantity"] == 0


def test_duplicate_bar_is_idempotent():
    account = new_account(25)
    account, _ = apply_paper_signal(account, 1, 100, "bar-1", 0, 0, 0)
    cash = account["cash"]
    quantity = account["quantity"]
    account, event = apply_paper_signal(account, 1, 105, "bar-1", 0, 0, 0)
    assert event["status"] == "duplicate_bar"
    assert account["cash"] == cash
    assert account["quantity"] == quantity
    assert len(account["ledger"]) == 1


def test_costs_reduce_entry_and_exit_proceeds():
    account = new_account(25)
    account, _ = apply_paper_signal(account, 1, 100, "bar-1", 0.001, 0.001, 0.002)
    account, event = apply_paper_signal(account, 0, 100, "bar-2", 0.001, 0.001, 0.002)
    assert event["status"] == "sell"
    assert account["cash"] < 25
    assert account["realized_pnl"] < 0


def test_entry_fee_is_included_in_realized_pnl():
    account = new_account(25)
    account, _ = apply_paper_signal(account, 1, 100, "bar-1", 0.01, 0, 0)
    account, sell = apply_paper_signal(account, 0, 100, "bar-2", 0.01, 0, 0)
    assert sell["status"] == "sell"
    assert account["realized_pnl"] == pytest.approx(-0.495049504950496)
    assert account["fees_paid"] == pytest.approx(0.495049504950496)
    assert account["fees_paid"] == pytest.approx(0.495049504950496)


def test_rub_capital_is_converted_to_usd_quote_currency():
    assert rub_to_usd(25, 100) == pytest.approx(0.25)


def test_rub_conversion_rejects_invalid_rate():
    with pytest.raises(ValueError):
        rub_to_usd(25, 0)


def test_crypto_and_fx_datasets_map_to_separate_sleeves():
    assert _dataset_sleeve("crypto_BTC_USD_1h.csv") == "crypto_spot"
    assert _dataset_sleeve("futures_PF_XBTUSD_1h.csv") == "crypto_futures_sim"
    assert _dataset_sleeve("forex_EURUSD=X_1d.csv") == "forex_spot_sim"
    assert _dataset_sleeve("forex_GBPUSD=X_1d.csv") == "forex_spot_sim"
    assert _dataset_sleeve("forex_JPY=X_1d.csv") is None
    assert _dataset_sleeve("forex_RUB=X_1d.csv") is None


def test_position_fraction_keeps_unallocated_cash():
    account = new_account(100)
    account, event = apply_paper_signal(
        account, 1, 100, "bar-1",
        fee_rate=0, slippage_rate=0, spread_rate=0,
        max_position_fraction=0.25,
    )
    assert event["status"] == "buy"
    assert account["quantity"] == pytest.approx(0.25)
    assert account["cash"] == pytest.approx(75.0)


def test_paper_runner_uses_previous_completed_bar_signal():
    frame = pd.DataFrame({"ema_signal": [0, 1, 0]})
    assert _paper_signal_for_latest(frame) == 1
    assert _paper_signal_for_latest(frame.iloc[:1]) is None


def test_72_hour_experiment_window_is_deterministic():
    start = "2026-01-01T00:00:00+00:00"
    now = pd.Timestamp("2026-01-02T12:00:00Z").to_pydatetime()
    window = _experiment_window(start, now)
    assert window["status"] == "RUNNING"
    assert window["elapsed_hours"] == pytest.approx(36)
    assert window["remaining_hours"] == pytest.approx(36)
    assert window["end_utc"].startswith("2026-01-04T00:00:00")


def test_72_hour_experiment_window_marks_completion():
    start = "2026-01-01T00:00:00+00:00"
    now = pd.Timestamp("2026-01-04T01:00:00Z").to_pydatetime()
    window = _experiment_window(start, now)
    assert window["status"] == "COMPLETED"
    assert window["remaining_hours"] == 0


def test_spot_paper_account_rejects_below_minimum_notional():
    account = new_account(100)
    account, event = apply_paper_signal(
        account, 1, 100, "bar-min",
        fee_rate=0, slippage_rate=0, spread_rate=0,
        max_position_fraction=0.25,
        min_order_size=0.0001,
        min_notional=50,
    )
    assert event["status"] == "below_minimum_size"
    assert account["quantity"] == 0
    assert account["cash"] == pytest.approx(100)
    assert account["rejected_min_size"] == 1


def test_spot_account_rejects_non_finite_cost_assumptions():
    account = new_account(25)
    with pytest.raises(ValueError, match="finite and non-negative"):
        apply_paper_signal(
            account, 1, 100, "bar-nan",
            fee_rate=float("nan"), slippage_rate=0, spread_rate=0,
        )



def test_spot_account_rejects_non_finite_cost_assumptions():
    account = new_account(25)
    with pytest.raises(ValueError, match="finite and non-negative"):
        apply_paper_signal(
            account, 1, 100, "bar-nan",
            fee_rate=float("nan"), slippage_rate=0, spread_rate=0,
        )


def test_portfolio_target_progress_includes_inactive_cash():
    metrics = _portfolio_target_metrics(
        active_equity_rub=75,
        inactive_capital_rub=25,
        total_capital_rub=100,
        target_equity_rub=10000,
        duration_hours=72,
    )
    assert metrics["total_equity_rub_estimate"] == pytest.approx(100)
    assert metrics["total_return_pct"] == pytest.approx(0)
    assert metrics["target_progress_pct"] == pytest.approx(1)
    assert metrics["target_required_hourly_return_pct"] > 0


def test_fractional_shadow_can_trade_below_venue_minimums(tmp_path):
    path = tmp_path / "crypto_BTC_USD_1h.csv"
    times = pd.date_range("2026-01-01", periods=80, freq="h", tz="UTC")
    close = [100.0 + i for i in range(80)]
    frame = pd.DataFrame({
        "timestamp": times,
        "open": [value - 0.2 for value in close],
        "high": [value + 0.5 for value in close],
        "low": [value - 0.5 for value in close],
        "close": close,
        "volume": [1000.0] * 80,
        "min_order_size": [0.1] * 80,
        "min_notional_usd": [100.0] * 80,
    })
    frame.to_csv(path, index=False)
    cfg = {
        "data": {
            "crypto": {"timeframe": "1h"},
            "forex": {"interval": "1d"},
            "futures": {"timeframe": "1h"},
        },
        "capital": {"portfolios": {"crypto_spot": 25.0}},
        "paper": {"max_position_fraction": 0.25},
        "costs": {
            "crypto_fee_rate": 0.0,
            "forex_fee_rate": 0.0,
            "slippage_rate": 0.0,
            "crypto_spread_rate": 0.0,
            "forex_spread_rate": 0.0,
        },
    }
    accounts = {}
    events, snapshots = _run_fractional_shadow(
        cfg,
        [path],
        {"crypto_spot": 1},
        accounts,
        {"status": "RUNNING"},
        usd_rub_rate=80.0,
        now=pd.Timestamp("2026-01-05T00:00:00Z").to_pydatetime(),
    )
    assert events[0]["status"] == "buy"
    assert snapshots[0]["venue_minimums_ignored"] is True
    assert snapshots[0]["minimum_order_quantity"] == 0.1
    assert snapshots[0]["required_account_capital_rub_for_minimum_order"] > 25
    assert accounts[path.stem]["quantity"] > 0



def test_experiment_status_report_marks_fractional_view_non_executable(tmp_path, monkeypatch):
    import quantlab.paper.runner as paper_runner

    monkeypatch.setattr(paper_runner, "REPORTS", tmp_path)
    pd.DataFrame([{
        "dataset": "forex_RUB=X_1d.csv",
        "strategy": "bb_signal",
        "folds": 6,
        "median_test_return_pct": 1.9,
        "positive_fold_pct": 66.7,
    }]).to_csv(tmp_path / "walk_forward_ranking.csv", index=False)
    pd.DataFrame([{
        "dataset": "futures_PF_SOLUSD_1h.csv",
        "strategy": "rsi_signal",
        "folds": 9,
        "median_test_return_pct": 0.4,
        "positive_fold_pct": 55.6,
    }]).to_csv(tmp_path / "futures_walk_forward_ranking.csv", index=False)
    pd.DataFrame([{"holm_adjusted_p_value": 1.0}]).to_csv(
        tmp_path / "statistical_validation.csv", index=False
    )
    venue = pd.DataFrame([{
        "timestamp_utc": "2026-11-19T13:00:00Z",
        "experiment_id": "test",
        "experiment_status": "RUNNING",
        "experiment_start_utc": "2026-11-19T12:00:00Z",
        "experiment_end_utc": "2026-11-22T12:00:00Z",
        "experiment_elapsed_hours": 1,
        "experiment_remaining_hours": 71,
        "target_equity_rub": 10000,
        "total_initial_capital_rub": 100,
        "total_equity_rub_estimate": 100,
        "total_return_pct": 0,
        "target_progress_pct": 1,
        "target_required_hourly_return_pct": 6.605,
        "active_initial_capital_rub": 75,
        "inactive_capital_rub": 25,
        "minimum_lot_blocked_capital_rub": 50,
        "lowest_crypto_min_order_capital_rub": 122.71,
        "fills_this_run": 0,
        "rejected_orders_this_run": 6,
        "open_positions": 0,
        "closed_trades": 0,
    }])
    fractional = pd.DataFrame([{
        "total_equity_rub_estimate": 99.9,
        "total_return_pct": -0.1,
        "active_return_pct": -0.13,
        "fills_this_run": 6,
        "fees_paid_usd": 0.01,
        "funding_paid_usd": 0.001,
        "liquidations": 0,
        "open_positions": 6,
        "closed_trades": 0,
    }])
    _write_experiment_status_report(venue, fractional)
    report = (tmp_path / "experiment_status.md").read_text(encoding="utf-8")
    assert "NON-EXECUTABLE" in report
    assert "cannot be placed at the exchange" in report
    assert "bb_signal" in report
    assert "Holm-adjusted p-value" in report
    assert "open positions: 6" in report
    assert "budget shortfall: 22.71 RUB" in report



def test_paper_cursor_processes_all_missed_completed_bars_in_order():
    times = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    enriched = pd.DataFrame({
        "timestamp": times,
        "ema_signal": [0, 1, 0, 1, 1],
    })
    pending = _unprocessed_signal_rows(enriched, times[1].isoformat())
    assert pending == [(2, 1), (3, 0), (4, 1)]


def test_new_paper_account_starts_from_latest_bar_without_replaying_history():
    times = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    enriched = pd.DataFrame({
        "timestamp": times,
        "ema_signal": [0, 1, 0, 1, 1],
    })
    assert _unprocessed_signal_rows(enriched, None) == [(4, 1)]


def test_paper_cursor_does_not_reprocess_already_seen_bars():
    times = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    enriched = pd.DataFrame({
        "timestamp": times,
        "ema_signal": [0, 1, 0, 1, 1],
    })
    assert _unprocessed_signal_rows(enriched, times[-1].isoformat()) == []



def test_account_replays_missed_bars_in_chronological_order():
    times = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    enriched = pd.DataFrame({
        "timestamp": times,
        "close": [100.0, 110.0, 105.0, 120.0, 125.0],
        "ema_signal": [0, 1, 0, 1, 1],
        "min_order_size": [0.0] * 5,
        "min_notional_usd": [0.0] * 5,
    })
    account = new_account(100.0)
    account["initial_capital_rub"] = 100.0
    account["last_bar"] = times[1].isoformat()
    cfg = {
        "costs": {
            "crypto_fee_rate": 0.0,
            "forex_fee_rate": 0.0,
            "slippage_rate": 0.0,
            "crypto_spread_rate": 0.0,
            "forex_spread_rate": 0.0,
        },
        "paper": {"max_position_fraction": 1.0},
    }
    updated, events, snapshot = _process_account_bars(
        cfg,
        account,
        enriched,
        "crypto_spot",
        "crypto_TEST_1h",
        usd_rub_rate=1.0,
        experiment={"status": "RUNNING"},
        ignore_venue_minimums=False,
    )
    assert [event["status"] for event in events] == ["buy", "sell", "buy"]
    assert [event["backfilled"] for event in events] == [True, True, False]
    assert updated["last_bar"] == times[-1].isoformat()
    assert updated["trade_count"] == 3
    assert snapshot["quantity"] > 0

