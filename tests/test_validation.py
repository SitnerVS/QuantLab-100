import pandas as pd

from quantlab.backtest.validation import walk_forward_evaluate, summarize_walk_forward, walk_forward_futures_evaluate


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


def test_futures_walk_forward_uses_margin_and_funding_engine():
    frame = pd.DataFrame({
        "close": [100.0] * 8,
        "signal": [1] * 8,
        "funding_rate": [0.0] * 8,
    })
    cfg = {
        "leverage": 2.0,
        "max_margin_fraction": 0.25,
        "maintenance_margin_rate": 0.01,
        "liquidation_fee_rate": 0.005,
    }
    rows = walk_forward_futures_evaluate(
        frame,
        "signal",
        cfg,
        train_bars=3,
        test_bars=2,
        fee_rate=0,
        slippage_rate=0,
        spread_rate=0,
    )
    assert len(rows) == 3
    assert rows[0]["test_observations"] == 2
    assert rows[0]["test_liquidations"] == 0
