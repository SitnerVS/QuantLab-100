import pandas as pd

from quantlab.backtest.validation import walk_forward_evaluate, summarize_walk_forward


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


def test_walk_forward_ranking_uses_test_folds_only():
    rows = [
        {"dataset": "BTC", "strategy": "ema", "fold": 1, "test_return_pct": 2.0,
         "test_max_drawdown_pct": -1.0, "test_sharpe_annualized": 1.0},
        {"dataset": "BTC", "strategy": "ema", "fold": 2, "test_return_pct": -1.0,
         "test_max_drawdown_pct": -2.0, "test_sharpe_annualized": -0.5},
    ]
    result = summarize_walk_forward(rows).iloc[0]
    assert result["folds"] == 2
    assert result["mean_test_return_pct"] == 0.5
    assert result["positive_fold_pct"] == 50.0
