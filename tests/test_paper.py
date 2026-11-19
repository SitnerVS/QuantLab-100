import pandas as pd
import pytest

from quantlab.paper.engine import apply_paper_signal, new_account, rub_to_usd
from quantlab.paper.runner import _dataset_sleeve, _paper_signal_for_latest, _experiment_window


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
