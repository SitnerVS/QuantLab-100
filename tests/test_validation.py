import pandas as pd

from quantlab.backtest.validation import walk_forward_evaluate, summarize_walk_forward, walk_forward_futures_evaluate, walk_forward_futures_long_short_evaluate


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



def test_long_short_futures_walk_forward_applies_risk_controls():
    frame = pd.DataFrame({
        "open": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "high": [100.0, 101.0, 103.0, 104.0, 103.0, 101.0, 100.0, 99.0],
        "low": [100.0, 99.0, 98.0, 99.0, 98.0, 97.0, 98.0, 98.0],
        "close": [100.0, 100.0, 101.0, 102.0, 100.0, 99.0, 99.0, 99.0],
        "direction": [1, 1, 1, 1, -1, -1, -1, -1],
        "funding_rate": [0.0] * 8,
        "min_order_size": [0.0] * 8,
        "min_notional_usd": [0.0] * 8,
    })
    cfg = {
        "leverage": 2.0,
        "max_margin_fraction": 0.25,
        "maintenance_margin_rate": 0.01,
        "liquidation_fee_rate": 0.0,
    }
    rows = walk_forward_futures_long_short_evaluate(
        frame, "direction", cfg, train_bars=3, test_bars=2,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        stop_loss_pct=0.02, max_drawdown_pct=0.10,
    )
    assert len(rows) == 3
    assert all("test_stop_losses" in row for row in rows)
    assert all("test_kill_switches" in row for row in rows)



def test_long_short_walk_forward_kill_switch_resets_between_folds():
    frame = pd.DataFrame({
        "open": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "high": [100.0, 101.0, 101.0, 101.0, 101.0, 101.0, 101.0],
        "low": [100.0, 99.0, 99.0, 99.0, 80.0, 99.0, 99.0],
        "close": [100.0, 100.0, 100.0, 100.0, 80.0, 100.0, 100.0],
        "direction": [1, 1, 1, 1, 1, 1, 1],
        "funding_rate": [0.0] * 7,
        "min_order_size": [0.0] * 7,
        "min_notional_usd": [0.0] * 7,
    })
    cfg = {
        "leverage": 2.0,
        "max_margin_fraction": 0.5,
        "maintenance_margin_rate": 0.01,
        "liquidation_fee_rate": 0.0,
    }
    rows = walk_forward_futures_long_short_evaluate(
        frame, "direction", cfg, train_bars=3, test_bars=2,
        fee_rate=0, slippage_rate=0, spread_rate=0,
        max_drawdown_pct=0.05,
    )
    assert len(rows) == 2
    assert rows[0]["test_kill_switches"] == 1
    assert rows[1]["test_kill_switches"] == 0
    assert rows[1]["test_observations"] == 2
