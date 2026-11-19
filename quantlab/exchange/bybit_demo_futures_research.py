"""Research-only long-only and long/short Bybit Demo futures backtests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quantlab.futures.engine import simulate_isolated_long
from quantlab.futures.long_short import simulate_isolated_long_short
from quantlab.strategies import build_signals

STRATEGIES = (
    "ema_signal", "rsi_signal", "bb_signal", "donchian_signal",
    "sma_signal", "macd_signal", "roc_signal",
)
DIRECTION_COLUMNS = {
    "ema_signal": "ema_direction",
    "rsi_signal": "rsi_direction",
    "bb_signal": "bb_direction",
    "donchian_signal": "donchian_direction",
    "sma_signal": "sma_direction",
    "macd_signal": "macd_direction",
    "roc_signal": "roc_direction",
}
REQUIRED = {
    "timestamp", "open", "high", "low", "close", "volume",
    "funding_rate", "funding_settlement_utc", "min_order_size",
    "min_notional_usd", "qty_step", "tick_size", "max_leverage",
}


def _build_direction_signals(enriched):
    data = enriched.copy()
    close = data["close"].astype(float)

    def binary_direction(left, right):
        direction = pd.Series(0, index=data.index, dtype=int)
        valid = left.notna() & right.notna()
        direction.loc[valid] = left.loc[valid].gt(right.loc[valid]).map(
            {True: 1, False: -1}
        )
        return direction

    data["ema_direction"] = binary_direction(data["ema_fast"], data["ema_slow"])
    data["sma_direction"] = binary_direction(data["sma_fast"], data["sma_slow"])
    data["macd_direction"] = binary_direction(
        data["macd_line"], data["macd_signal_line"]
    )

    roc = data["roc_12"]
    data["roc_direction"] = pd.Series(0, index=data.index, dtype=int)
    valid_roc = roc.notna()
    data.loc[valid_roc, "roc_direction"] = roc.loc[valid_roc].gt(0).map(
        {True: 1, False: -1}
    )

    data["rsi_direction"] = 0
    data.loc[data["rsi"] < 30, "rsi_direction"] = 1
    data.loc[data["rsi"] > 70, "rsi_direction"] = -1

    data["bb_upper"] = data["bb_mid"] + 2 * data["bb_std"]
    data["bb_direction"] = 0
    data.loc[close < data["bb_lower"], "bb_direction"] = 1
    data.loc[close > data["bb_upper"], "bb_direction"] = -1

    data["donchian_lower_prev"] = data["low"].rolling(20).min().shift(1)
    data["donchian_direction"] = 0
    data.loc[close > data["donchian_upper_prev"], "donchian_direction"] = 1
    data.loc[close < data["donchian_lower_prev"], "donchian_direction"] = -1
    return data


def _walk_forward_rows(result, path, symbol, strategy, train_bars, test_bars):
    rows = []
    period_returns = result["equity"].pct_change().fillna(0.0)
    fold_number = 0
    for test_start in range(train_bars, len(result), test_bars):
        test_end = min(test_start + test_bars, len(result))
        returns_window = period_returns.iloc[test_start:test_end].astype(float)
        if returns_window.empty:
            continue
        fold_number += 1
        start_equity = float(result["equity"].iloc[test_start - 1])
        end_equity = float(result["equity"].iloc[test_end - 1])
        if start_equity > 0:
            normalized = start_equity * (1.0 + returns_window).cumprod()
            fold_return = (end_equity / start_equity - 1.0) * 100.0
            curve = pd.concat(
                [pd.Series([start_equity]), normalized.reset_index(drop=True)],
                ignore_index=True,
            )
            drawdown = curve / curve.cummax() - 1.0
        else:
            fold_return = -100.0
            drawdown = pd.Series([-1.0])
        std_window = returns_window.std(ddof=1)
        sharpe = (
            float(returns_window.mean() / std_window * (8760 ** 0.5))
            if pd.notna(std_window) and std_window > 0 else 0.0
        )
        rows.append({
            "dataset": path.name,
            "symbol": symbol,
            "strategy": strategy,
            "fold": fold_number,
            "train_observations": int(test_start),
            "test_observations": int(test_end - test_start),
            "test_start_index": int(test_start),
            "test_end_index_exclusive": int(test_end),
            "test_return_pct": float(fold_return),
            "test_max_drawdown_pct": float(drawdown.min() * 100.0),
            "test_sharpe_annualized": sharpe,
            "test_liquidations": int(result["liquidated"].iloc[test_start:test_end].sum()),
            "test_funding_paid_quote": float(
                result["funding_payment"].iloc[test_start:test_end].sum()
            ),
        })
    return rows


def _rank_walk_forward(rows):
    frame = pd.DataFrame(rows)
    if frame.empty:
        return []
    ranking = (
        frame.groupby(["symbol", "strategy"], as_index=False)
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
    return ranking.to_dict(orient="records")


def _enrich_metrics(metrics, result, frame, settlements, initial_cash):
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
    metrics["excess_return_pct"] = metrics["total_return_pct"] - metrics["buy_hold_return_pct"]
    metrics["funding_settlements_in_data"] = int(settlements.sum())
    metrics["funding_charges_applied"] = int(
        (result["funding_payment"].abs() > 0).sum()
    )
    metrics["initial_cash_usdt"] = float(initial_cash)
    return metrics


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
    validation_cfg = cfg.get(
        "bybit_demo_futures_validation", cfg.get("validation", {})
    )
    train_bars = int(validation_cfg.get("train_bars", 180))
    test_bars = int(validation_cfg.get("test_bars", 60))
    paths = sorted(data_dir.glob("bybit_demo_linear_*_60.csv"))
    if not paths:
        raise RuntimeError("No isolated Bybit Demo futures datasets found.")

    summary_rows, walk_forward_rows = [], []
    long_short_summary_rows, long_short_walk_forward_rows = [], []
    dataset_checks = []
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
        directional = _build_direction_signals(enriched)
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
            metrics = _enrich_metrics(metrics, result, frame, settlements, initial_cash)
            summary_rows.append({
                "dataset": path.name, "symbol": symbol, "strategy": strategy, **metrics
            })
            walk_forward_rows.extend(
                _walk_forward_rows(result, path, symbol, strategy, train_bars, test_bars)
            )

            direction_column = DIRECTION_COLUMNS[strategy]
            ls_result, ls_metrics = simulate_isolated_long_short(
                directional,
                signal_col=direction_column,
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
            ls_metrics = _enrich_metrics(
                ls_metrics, ls_result, frame, settlements, initial_cash
            )
            long_short_summary_rows.append({
                "dataset": path.name,
                "symbol": symbol,
                "strategy": strategy,
                "direction_column": direction_column,
                **ls_metrics,
            })
            long_short_walk_forward_rows.extend(
                _walk_forward_rows(
                    ls_result, path, symbol, strategy, train_bars, test_bars
                )
            )

    summary = pd.DataFrame(summary_rows)
    walk_forward = pd.DataFrame(walk_forward_rows)
    long_short_summary = pd.DataFrame(long_short_summary_rows)
    long_short_walk_forward = pd.DataFrame(long_short_walk_forward_rows)
    summary_path = report_dir / "bybit_demo_futures_backtest_summary.csv"
    walk_forward_path = report_dir / "bybit_demo_futures_walk_forward.csv"
    long_short_summary_path = report_dir / "bybit_demo_futures_long_short_summary.csv"
    long_short_walk_forward_path = report_dir / "bybit_demo_futures_long_short_walk_forward.csv"
    summary.to_csv(summary_path, index=False)
    walk_forward.to_csv(walk_forward_path, index=False)
    long_short_summary.to_csv(long_short_summary_path, index=False)
    long_short_walk_forward.to_csv(long_short_walk_forward_path, index=False)

    strategy_results = summary[[
        "symbol", "strategy", "total_return_pct", "max_drawdown_pct",
        "closed_trades", "liquidations", "rejected_min_size",
        "rejected_min_notional", "funding_paid_quote", "fees_quote",
        "final_equity_usdt", "buy_hold_return_pct", "excess_return_pct",
    ]].to_dict(orient="records")
    long_short_strategy_results = long_short_summary[[
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
        "trading_modes": ["long_only", "long_short"],
        "dataset_count": len(dataset_checks),
        "backtest_rows": len(summary_rows),
        "walk_forward_folds": len(walk_forward_rows),
        "long_short_backtest_rows": len(long_short_summary_rows),
        "long_short_walk_forward_folds": len(long_short_walk_forward_rows),
        "datasets": dataset_checks,
        "strategy_results": strategy_results,
        "walk_forward_ranking": _rank_walk_forward(walk_forward_rows),
        "long_short_strategy_results": long_short_strategy_results,
        "long_short_walk_forward_ranking": _rank_walk_forward(long_short_walk_forward_rows),
        "outputs": [
            str(summary_path), str(walk_forward_path),
            str(long_short_summary_path), str(long_short_walk_forward_path),
        ],
        "demo_orders_submitted": 0,
        "real_orders_submitted": 0,
        "paper_engine_integration": False,
    }
    (report_dir / "bybit_demo_futures_backtest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report
