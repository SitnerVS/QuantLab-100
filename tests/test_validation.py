import pandas as pd

from quantlab.backtest.validation import walk_forward_evaluate


def test_walk_forward_windows_are_chronological_and_non_overlapping():
    frame = pd.DataFrame({
        "close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
        "signal": [1] * 10,
    })
    rows = walk_forward_evaluate(
        frame,
        "signal",
        train_bars=4,
        test_bars=3,
        fee_rate=0,
        slippage_rate=0,
        periods_per_year=252,
    )
    assert len(rows) == 2
    assert rows[0]["test_start_index"] == 4
    assert rows[0]["test_end_index_exclusive"] == 7
    assert rows[1]["test_start_index"] == 7
    assert rows[1]["test_end_index_exclusive"] == 10
    assert all(row["test_observations"] == 3 for row in rows)


def test_walk_forward_returns_empty_when_history_is_too_short():
    frame = pd.DataFrame({"close": [100, 101, 102], "signal": [1, 1, 1]})
    assert walk_forward_evaluate(frame, "signal", train_bars=4, test_bars=2) == []
