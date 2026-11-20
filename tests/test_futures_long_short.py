import pandas as pd
import pytest

from quantlab.futures.long_short import (
    apply_long_short_signal,
    new_long_short_account,
    simulate_isolated_long_short,
)


def test_short_position_closes_with_profit_when_mark_price_falls():
    frame = pd.DataFrame({
        "close": [100, 100, 90, 90],
        "direction_signal": [-1, -1, 0, 0],
        "funding_rate": [0.0, 0.0, 0.0, 0.0],
    })
    result, metrics = simulate_isolated_long_short(
        frame, initial_cash=100, leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    assert result["event"].tolist() == ["hold", "open", "hold", "close"]
    assert result.iloc[-1]["equity"] == pytest.approx(110.0)
    assert metrics["closed_trades"] == 1
    assert metrics["total_return_pct"] == pytest.approx(10.0)


def test_positive_funding_is_received_by_open_short():
    frame = pd.DataFrame({
        "close": [100, 100, 100, 100],
        "direction_signal": [-1, -1, -1, -1],
        "funding_rate": [0.0, 0.0, 0.01, 0.0],
    })
    result, metrics = simulate_isolated_long_short(
        frame, initial_cash=100, leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    assert metrics["funding_paid_quote"] == pytest.approx(-1.0)
    assert result["equity"].iloc[-1] == pytest.approx(101.0)
    assert result["position"].iloc[-1] == -1


def test_signal_reversal_closes_long_and_opens_short():
    account = new_long_short_account(100)
    account, opened = apply_long_short_signal(
        account, 1, 100, 0, "bar-1",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    assert opened["opened_direction"] == 1
    account, reversed_event = apply_long_short_signal(
        account, -1, 110, 0, "bar-2",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    assert reversed_event["status"] == "reverse"
    assert reversed_event["closed_direction"] == 1
    assert reversed_event["opened_direction"] == -1
    assert account["position"]["direction"] == -1


def test_long_short_simulator_respects_minimum_quantity():
    frame = pd.DataFrame({
        "close": [100, 100],
        "direction_signal": [-1, -1],
        "funding_rate": [0.0, 0.0],
        "min_order_size": [1.0, 1.0],
        "min_notional_usd": [5.0, 5.0],
    })
    result, metrics = simulate_isolated_long_short(
        frame, initial_cash=10, leverage=2, max_margin_fraction=0.25,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.05, liquidation_fee_rate=0,
    )
    assert result.iloc[-1]["event"] == "below_minimum_size"
    assert metrics["rejected_min_size"] == 1
    assert result.iloc[-1]["position"] == 0



def test_negative_funding_is_paid_by_open_short_and_received_by_long():
    short = new_long_short_account(100)
    short, _ = apply_long_short_signal(
        short, -1, 100, 0, "short-open",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    short, short_event = apply_long_short_signal(
        short, -1, 100, -0.01, "short-funding",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    assert short_event["funding_payment"] == pytest.approx(1.0)
    assert short["position"]["margin_balance"] == pytest.approx(49.0)

    long = new_long_short_account(100)
    long, _ = apply_long_short_signal(
        long, 1, 100, 0, "long-open",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    long, long_event = apply_long_short_signal(
        long, 1, 100, -0.01, "long-funding",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    assert long_event["funding_payment"] == pytest.approx(-1.0)
    assert long["position"]["margin_balance"] == pytest.approx(51.0)


def test_positive_funding_is_paid_by_open_long():
    account = new_long_short_account(100)
    account, _ = apply_long_short_signal(
        account, 1, 100, 0, "open",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    account, event = apply_long_short_signal(
        account, 1, 100, 0.01, "settlement",
        leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
    )
    assert event["funding_payment"] == pytest.approx(1.0)
    assert account["position"]["margin_balance"] == pytest.approx(49.0)


def test_long_position_uses_intrabar_stop_loss():
    frame = pd.DataFrame({
        "open": [100, 100, 100],
        "high": [100, 103, 104],
        "low": [100, 99, 97],
        "close": [100, 101, 99],
        "direction_signal": [1, 1, 1],
        "funding_rate": [0.0, 0.0, 0.0],
    })
    result, metrics = simulate_isolated_long_short(
        frame, initial_cash=100, leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
        stop_loss_pct=0.02,
    )
    assert result["event"].tolist() == ["hold", "open", "stop_loss"]
    assert result.iloc[-1]["stop_loss_triggered"] is True
    assert result.iloc[-1]["position"] == 0
    assert result.iloc[-1]["equity"] == pytest.approx(98.0)
    assert metrics["stop_losses"] == 1


def test_short_position_uses_intrabar_stop_loss():
    frame = pd.DataFrame({
        "open": [100, 100, 100],
        "high": [100, 101, 103],
        "low": [100, 99, 98],
        "close": [100, 100, 101],
        "direction_signal": [-1, -1, -1],
        "funding_rate": [0.0, 0.0, 0.0],
    })
    result, metrics = simulate_isolated_long_short(
        frame, initial_cash=100, leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
        stop_loss_pct=0.02,
    )
    assert result.iloc[-1]["event"] == "stop_loss"
    assert result.iloc[-1]["equity"] == pytest.approx(98.0)
    assert metrics["stop_losses"] == 1


def test_account_drawdown_kill_switch_closes_and_prevents_new_positions():
    frame = pd.DataFrame({
        "open": [100, 100, 94, 94],
        "high": [100, 101, 95, 95],
        "low": [100, 99, 93, 93],
        "close": [100, 100, 94, 94],
        "direction_signal": [1, 1, 1, 1],
        "funding_rate": [0.0, 0.0, 0.0, 0.0],
    })
    result, metrics = simulate_isolated_long_short(
        frame, initial_cash=100, leverage=2, max_margin_fraction=0.5,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        maintenance_margin_rate=0.01, liquidation_fee_rate=0,
        max_drawdown_pct=0.05,
    )
    assert result.iloc[2]["event"] == "max_drawdown_kill_switch"
    assert result.iloc[2]["drawdown_kill_switch"] is True
    assert result.iloc[2]["halted"] is True
    assert result.iloc[2]["position"] == 0
    assert result.iloc[3]["position"] == 0
    assert metrics["drawdown_kill_switch"] is True


def test_risk_thresholds_must_be_between_zero_and_one():
    account = new_long_short_account(100)
    with pytest.raises(ValueError, match="stop_loss_pct"):
        apply_long_short_signal(
            account, 0, 100, 0, "bad-stop", stop_loss_pct=1.0,
        )
    with pytest.raises(ValueError, match="max_drawdown_pct"):
        apply_long_short_signal(
            account, 0, 100, 0, "bad-dd", max_drawdown_pct=0.0,
        )
