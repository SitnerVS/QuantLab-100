from datetime import datetime, timezone

import pandas as pd

from quantlab.exchange.bybit_demo_futures_research import run_bybit_demo_futures_backtests


def test_research_backtests_isolated_bybit_datasets_without_live_orders(tmp_path):
    data_dir = tmp_path / "data"
    report_dir = tmp_path / "reports"
    data_dir.mkdir()
    periods = 90
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=periods, freq="h")
    close = [100 + index * 0.15 + (index % 7) * 0.1 for index in range(periods)]
    funding = [0.0001 if (index + 1) % 8 == 0 else 0.0 for index in range(periods)]
    settlements = [
        (timestamps[index] + pd.Timedelta(hours=1)).isoformat() if funding[index] else ""
        for index in range(periods)
    ]
    pd.DataFrame({
        "timestamp": timestamps,
        "open": close,
        "high": [value + 1 for value in close],
        "low": [value - 1 for value in close],
        "close": close,
        "volume": [10.0] * periods,
        "turnover": [1000.0] * periods,
        "funding_rate": funding,
        "funding_settlement_utc": settlements,
        "min_order_size": [0.001] * periods,
        "min_notional_usd": [5.0] * periods,
        "qty_step": [0.001] * periods,
        "tick_size": [0.1] * periods,
        "max_leverage": [100.0] * periods,
    }).to_csv(data_dir / "bybit_demo_linear_BTCUSDT_60.csv", index=False)

    cfg = {
        "backtest": {"initial_cash": 1000.0, "min_observations": 60},
        "futures": {
            "leverage": 2.0, "max_margin_fraction": 0.25, "fee_rate": 0.0006,
            "slippage_rate": 0.0005, "spread_rate": 0.0002,
            "maintenance_margin_rate": 0.05, "liquidation_fee_rate": 0.025,
        },
        "validation": {"train_bars": 30, "test_bars": 20},
    }
    report = run_bybit_demo_futures_backtests(
        cfg, data_dir=data_dir, report_dir=report_dir, strategies=("ema_signal",)
    )
    assert report["status"] == "BACKTEST_COMPLETED_RESEARCH_ONLY"
    assert report["backtest_rows"] == 1
    assert report["long_short_backtest_rows"] == 1
    assert report["long_short_walk_forward_folds"] >= 1
    assert report["demo_orders_submitted"] == 0
    assert report["real_orders_submitted"] == 0
    assert report["paper_engine_integration"] is False
    assert len(report["strategy_results"]) == 1
    assert len(report["walk_forward_ranking"]) >= 1
    assert (report_dir / "bybit_demo_futures_backtest_summary.csv").exists()
    assert (report_dir / "bybit_demo_futures_walk_forward.csv").exists()
    assert (report_dir / "bybit_demo_futures_long_short_summary.csv").exists()
    assert (report_dir / "bybit_demo_futures_long_short_walk_forward.csv").exists()
