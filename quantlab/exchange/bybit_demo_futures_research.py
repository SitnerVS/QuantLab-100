"""Research-only backtests for isolated Bybit Demo linear futures data."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quantlab.backtest.validation import walk_forward_futures_evaluate
from quantlab.futures.engine import simulate_isolated_long
from quantlab.strategies import build_signals

STRATEGIES = (
    "ema_signal", "rsi_signal", "bb_signal", "donchian_signal",
    "sma_signal", "macd_signal", "roc_signal",
)
REQUIRED = {
    "timestamp", "open", "high", "low", "close", "volume",
    "funding_rate", "funding_settlement_utc", "min_order_size",
    "min_notional_usd", "qty_step", "tick_size", "max_leverage",
}


def run_bybit_demo_futures_backtests(
    cfg,
    data_dir="data/bybit_demo",
    report_dir="reports",
    strategies=STRATEGIES,
):
    data_dir, report_dir = Path(data_dir), Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    futures_cfg = cfg["futures"]
    initial_cash = float(cfg.get("backtest", {}).get("initial_cash", 100.0))
    min_observations = int(cfg.get("backtest", {}).get("min_observations", 60))
    validation_cfg = cfg.get("validation", {})
    train_bars = int(validation_cfg.get("train_bars", 180))
    test_bars = int(validation_cfg.get("test_bars", 60))
    paths = sorted(data_dir.glob("bybit_demo_linear_*_60.csv"))
    if not paths:
        raise RuntimeError("No isolated Bybit Demo futures datasets found.")

    summary_rows, walk_forward_rows, dataset_checks = [], [], []
    for path in paths:
        frame = pd.read_csv(path)
        frame.columns = [str(column).lower() for column in frame.columns]
        missing_columns = sorted(REQUIRED - set(frame.columns))
        if missing_columns:
            raise RuntimeError(f"{path.name}: missing columns: {missing_columns}")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        if frame["timestamp"].isna().any():
            raise RuntimeError(f"{path.name}: invalid candle timestamps")
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        if frame["timestamp"].duplicated().any():
            raise RuntimeError(f"{path.name}: duplicate candle timestamps")
        if len(frame) < min_observations:
            raise RuntimeError(
                f"{path.name}: {len(frame)} rows; at least {min_observations} required"
            )
        numeric = ["open", "high", "low", "close", "volume", "funding_rate",
                   "min_order_size", "min_notional_usd"]
        for column in numeric:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[numeric].isna().any().any():
            raise RuntimeError(f"{path.name}: missing or non-numeric market fields")
        if (frame["min_order_size"] <= 0).any() or (frame["min_notional_usd"] < 0).any():
            raise RuntimeError(f"{path.name}: invalid exchange order constraints")
        if (frame["high"] < frame[["open", "close"]].max(axis=1)).any():
            raise RuntimeError(f"{path.name}: invalid OHLC high values")
        if (frame["low"] > frame[["open", "close"]].min(axis=1)).any():
            raise RuntimeError(f"{path.name}: invalid OHLC low values")
        settlements = frame["funding_settlement_utc"].fillna("").astype(str).str.len().gt(0)
        if (frame.loc[~settlements, "funding_rate"] != 0).any():
            raise RuntimeError(f"{path.name}: funding rate exists without a matched settlement")
        if int(settlements.sum()) == 0:
            raise RuntimeError(f"{path.name}: no aligned funding settlements")
        settlement_times = pd.to_datetime(
            frame.loc[settlements, "funding_settlement_utc"], utc=True, errors="coerce"
        )
        expected_settlement_times = frame.loc[settlements, "timestamp"] + pd.Timedelta(hours=1)
        if settlement_times.isna().any() or not settlement_times.reset_index(drop=True).equals(
            expected_settlement_times.reset_index(drop=True)
        ):
            raise RuntimeError(f"{path.name}: funding settlement does not match candle close")

        enriched = build_signals(frame)
        symbol = path.name.removeprefix("bybit_demo_linear_").removesuffix("_60.csv")
        dataset_checks.append({
            "symbol": symbol,
            "rows": int(len(frame)),
            "funding_settlements": int(settlements.sum()),
            "first_bar_utc": frame["timestamp"].iloc[0].isoformat(),
            "last_bar_utc": frame["timestamp"].iloc[-1].isoformat(),
            "min_order_size": float(frame["min_order_size"].iloc[-1]),
            "min_notional_usd": float(frame["min_notional_usd"].iloc[-1]),
            "qty_step": float(frame["qty_step"].iloc[-1]),
            "tick_size": float(frame["tick_size"].iloc[-1]),
            "exchange_max_leverage": float(frame["max_leverage"].iloc[-1]),
        })

        for strategy in strategies:
            result, metrics = simulate_isolated_long(
                enriched,
                signal_col=strategy,
                funding_col="funding_rate",
                initial_cash=initial_cash,
                leverage=float(futures_cfg["leverage"]),
                max_margin_fraction=float(futures_cfg["max_margin_fraction"]),
                fee_rate=float(futures_cfg["fee_rate"]),
                slippage_rate=float(futures_cfg["slippage_rate"]),
                spread_rate=float(futures_cfg["spread_rate"]),
                maintenance_margin_rate=float(futures_cfg["maintenance_margin_rate"]),
                liquidation_fee_rate=float(futures_cfg["liquidation_fee_rate"]),
            )
            returns = result["equity"].pct_change().fillna(0.0)
            std = returns.std(ddof=1)
            metrics["sharpe_annualized_rough"] = (
                float(returns.mean() / std * (8760 ** 0.5))
                if pd.notna(std) and std > 0 else 0.0
            )
            metrics["final_equity_usdt"] = float(result["equity"].iloc[-1])
            metrics["buy_hold_return_pct"] = float(
                (frame["close"].iloc[-1] / frame["close"].iloc[0] - 1.0) * 100.0
            )
            metrics["excess_return_pct"] = (
                metrics["total_return_pct"] - metrics["buy_hold_return_pct"]
            )
            metrics["funding_settlements_in_data"] = int(settlements.sum())
            metrics["funding_charges_applied"] = int(
                (result["funding_payment"].abs() > 0).sum()
            )
            summary_rows.append({
                "dataset": path.name,
                "symbol": symbol,
                "strategy": strategy,
                "initial_cash_usdt": initial_cash,
                **metrics,
            })
            folds = walk_forward_futures_evaluate(
                enriched,
                strategy,
                futures_cfg,
                train_bars=train_bars,
                test_bars=test_bars,
                fee_rate=float(futures_cfg["fee_rate"]),
                slippage_rate=float(futures_cfg["slippage_rate"]),
                spread_rate=float(futures_cfg["spread_rate"]),
                initial_cash=initial_cash,
            )
            walk_forward_rows.extend({
                "dataset": path.name, "symbol": symbol, "strategy": strategy, **fold
            } for fold in folds)

    summary = pd.DataFrame(summary_rows)
    walk_forward = pd.DataFrame(walk_forward_rows)
    summary_path = report_dir / "bybit_demo_futures_backtest_summary.csv"
    walk_forward_path = report_dir / "bybit_demo_futures_walk_forward.csv"
    summary.to_csv(summary_path, index=False)
    walk_forward.to_csv(walk_forward_path, index=False)
    if not walk_forward.empty:
        ranking_frame = (
            walk_forward.groupby(["symbol", "strategy"], as_index=False)
            .agg(
                folds=("fold", "count"),
                median_test_return_pct=("test_return_pct", "median"),
                mean_test_return_pct=("test_return_pct", "mean"),
                positive_fold_pct=("test_return_pct", lambda values: float((values > 0).mean() * 100.0)),
                median_test_max_drawdown_pct=("test_max_drawdown_pct", "median"),
                median_test_sharpe_annualized=("test_sharpe_annualized", "median"),
                total_test_liquidations=("test_liquidations", "sum"),
            )
            .sort_values(["symbol", "median_test_return_pct"], ascending=[True, False])
        )
        walk_forward_ranking = ranking_frame.to_dict(orient="records")
    else:
        walk_forward_ranking = []

    strategy_results = summary[[
        "symbol", "strategy", "total_return_pct", "max_drawdown_pct",
        "closed_trades", "liquidations", "rejected_min_size",
        "rejected_min_notional", "funding_paid_quote", "fees_quote",
        "final_equity_usdt", "buy_hold_return_pct", "excess_return_pct",
    ]].to_dict(orient="records")

    report = {
        "status": "BACKTEST_COMPLETED_RESEARCH_ONLY",
        "exchange": "Bybit",
        "environment": "DEMO_MARKET_DATA",
        "market_type": "linear_perpetual",
        "price_basis": "mark",
        "initial_cash_usdt_per_strategy": initial_cash,
        "capital_note": "Research normalization only; not a statement of funded account balance.",
        "strategies_tested": list(strategies),
        "dataset_count": len(dataset_checks),
        "backtest_rows": len(summary_rows),
        "walk_forward_folds": len(walk_forward_rows),
        "datasets": dataset_checks,
        "strategy_results": strategy_results,
        "walk_forward_ranking": walk_forward_ranking,
        "outputs": [str(summary_path), str(walk_forward_path)],
        "demo_orders_submitted": 0,
        "real_orders_submitted": 0,
        "paper_engine_integration": False,
    }
    (report_dir / "bybit_demo_futures_backtest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report
