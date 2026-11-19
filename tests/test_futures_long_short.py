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
