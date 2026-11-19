import pandas as pd
import pytest

from quantlab.futures.engine import simulate_isolated_long


def test_isolated_futures_long_closes_with_profit():
    frame = pd.DataFrame({
        "close": [100, 100, 110, 110],
        "signal": [1, 1, 0, 0],
        "funding_rate": [0.0, 0.0, 0.0, 0.0],
    })
    result, metrics = simulate_isolated_long(
        frame,
        initial_cash=100,
        leverage=2,
        max_margin_fraction=0.5,
        fee_rate=0,
        slippage_rate=0,
        spread_rate=0,
        maintenance_margin_rate=0.01,
        liquidation_fee_rate=0,
    )
    assert result["event"].tolist() == ["hold", "open", "hold", "close"]
    assert metrics["closed_trades"] == 1
    assert metrics["total_return_pct"] == pytest.approx(10.0)


def test_isolated_futures_liquidation_caps_loss_to_allocated_margin():
    frame = pd.DataFrame({
        "close": [100, 100, 80],
        "signal": [1, 1, 1],
        "funding_rate": [0.0, 0.0, 0.0],
    })
    result, metrics = simulate_isolated_long(
        frame,
        initial_cash=100,
        leverage=10,
        max_margin_fraction=0.5,
        fee_rate=0,
        slippage_rate=0,
        spread_rate=0,
        maintenance_margin_rate=0.05,
        liquidation_fee_rate=0,
    )
    assert result.iloc[-1]["event"] == "liquidation"
    assert metrics["liquidations"] == 1
    assert result.iloc[-1]["equity"] >= 50.0


def test_futures_engine_requires_observed_funding_column():
    frame = pd.DataFrame({"close": [100, 101], "signal": [1, 1]})
    with pytest.raises(ValueError, match="funding_rate"):
        simulate_isolated_long(frame)


def test_positive_funding_is_charged_to_open_long():
    frame = pd.DataFrame({
        "close": [100, 100, 100, 100, 100],
        "signal": [1, 1, 1, 0, 0],
        "funding_rate": [0.0, 0.0, 0.01, 0.0, 0.0],
    })
    result, metrics = simulate_isolated_long(
        frame,
        initial_cash=100,
        leverage=2,
        max_margin_fraction=0.5,
        fee_rate=0,
        slippage_rate=0,
        spread_rate=0,
        maintenance_margin_rate=0.01,
        liquidation_fee_rate=0,
    )
    assert metrics["funding_paid_quote"] == pytest.approx(1.0)
    assert result["equity"].iloc[-1] == pytest.approx(99.0)
