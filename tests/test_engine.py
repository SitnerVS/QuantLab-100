import pandas as pd

from quantlab.backtest.engine import simulate


def test_simulate_produces_equity_and_metrics():
    frame = pd.DataFrame({
        "close": [100, 100, 110, 120, 115],
        "signal": [1, 1, 1, 1, 0],
    })
    result, metrics = simulate(frame, "signal", fee_rate=0, slippage_rate=0, initial_cash=100)
    assert len(result) == 5
    assert metrics["observations"] == 5
    assert result["equity"].iloc[-1] > 100


def test_signal_is_lagged_one_bar():
    frame = pd.DataFrame({"close": [100, 110, 100], "signal": [1, 0, 0]})
    result, _ = simulate(frame, "signal", fee_rate=0, slippage_rate=0, initial_cash=100)
    assert result.loc[0, "position"] == 0
    assert result.loc[1, "position"] == 1
