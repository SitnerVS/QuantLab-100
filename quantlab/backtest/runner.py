from pathlib import Path
import zlib

import pandas as pd

from quantlab.backtest.engine import simulate
from quantlab.backtest.validation import (
    walk_forward_evaluate,
    summarize_walk_forward,
    walk_forward_futures_evaluate,
)
from quantlab.futures.engine import simulate_isolated_long
from quantlab.backtest.statistics import block_bootstrap_validation, holm_adjust
from quantlab.strategies import build_signals

RAW = Path("data/raw")
REPORTS = Path("reports")
STRATEGIES = (
    "ema_signal", "rsi_signal", "bb_signal", "donchian_signal",
    "sma_signal", "macd_signal", "roc_signal",
)


def run_backtests(cfg):
    REPORTS.mkdir(parents=True, exist_ok=True)
    spot_rows = []
    spot_walk_forward_rows = []
    futures_rows = []
    futures_walk_forward_rows = []
    statistical_rows = []

    quality_path = REPORTS / "data_quality.csv"
    quality = pd.read_csv(quality_path) if quality_path.exists() else pd.DataFrame()
    valid_names = set(
        quality.loc[quality["status"].isin(["OK", "STALE"]), "dataset"].astype(str)
    ) if not quality.empty else set()
    if not valid_names:
        raise RuntimeError("No datasets passed the data quality gate.")

    validation_cfg = cfg.get("validation", {})
    initial_cash = float(cfg["backtest"]["initial_cash"])

    for path in sorted(p for p in RAW.glob("*.csv") if p.name in valid_names):
        try:
            frame = pd.read_csv(path)
            frame.columns = [str(col).lower() for col in frame.columns]
            required = {"open", "high", "low", "close", "volume"}
            if not required.issubset(frame.columns):
                print(f"[backtest] SKIP {path.name}: missing OHLCV columns")
                continue
            if len(frame) < int(cfg["backtest"]["min_observations"]):
                print(f"[backtest] SKIP {path.name}: insufficient history")
                continue

            enriched = build_signals(frame)

            if path.name.startswith("futures_"):
                futures_cfg = cfg["futures"]
                fee = float(futures_cfg["fee_rate"])
                slippage = float(futures_cfg["slippage_rate"])
                spread = float(futures_cfg["spread_rate"])
                for strategy in STRATEGIES:
                    result, metrics = simulate_isolated_long(
                        enriched,
                        signal_col=strategy,
                        funding_col="funding_rate",
                        initial_cash=initial_cash,
                        leverage=float(futures_cfg["leverage"]),
                        max_margin_fraction=float(futures_cfg["max_margin_fraction"]),
                        fee_rate=fee,
                        slippage_rate=slippage,
                        spread_rate=spread,
                        maintenance_margin_rate=float(futures_cfg["maintenance_margin_rate"]),
                        liquidation_fee_rate=float(futures_cfg["liquidation_fee_rate"]),
                    )
                    returns = result["equity"].pct_change().fillna(0.0)
                    seed = zlib.crc32(f"{path.name}:{strategy}".encode("utf-8")) + 42
                    bootstrap = block_bootstrap_validation(
                        returns, block_size=24, n_bootstrap=500, seed=seed
                    )
                    metrics.update({
                        "bootstrap_ci_lower_pct": bootstrap["bootstrap_ci_lower_pct"],
                        "bootstrap_ci_upper_pct": bootstrap["bootstrap_ci_upper_pct"],
                        "block_bootstrap_p_value": bootstrap["block_bootstrap_p_value"],
                    })
                    statistical_rows.append({
                        "dataset": path.name,
                        "market_type": "futures",
                        "strategy": strategy,
                        "block_size": 24,
                        **bootstrap,
                    })
                    std = returns.std(ddof=1)
                    metrics["sharpe_annualized_rough"] = (
                        float(returns.mean() / std * (8760 ** 0.5))
                        if pd.notna(std) and std > 0 else 0.0
                    )
                    buy_hold = float((enriched["close"].iloc[-1] / enriched["close"].iloc[0] - 1.0) * 100.0)
                    metrics["buy_hold_return_pct"] = buy_hold
                    metrics["excess_return_pct"] = metrics["total_return_pct"] - buy_hold
                    futures_rows.append({"dataset": path.name, "strategy": strategy, **metrics})

                    folds = walk_forward_futures_evaluate(
                        enriched,
                        strategy,
                        futures_cfg,
                        train_bars=int(validation_cfg.get("train_bars", 180)),
                        test_bars=int(validation_cfg.get("test_bars", 60)),
                        fee_rate=fee,
                        slippage_rate=slippage,
                        spread_rate=spread,
                        initial_cash=initial_cash,
                    )
                    for fold_metrics in folds:
                        futures_walk_forward_rows.append({
                            "dataset": path.name,
                            "strategy": strategy,
                            **fold_metrics,
                        })
                continue

            is_crypto = path.name.startswith("crypto_")
            fee = float(cfg["costs"]["crypto_fee_rate"] if is_crypto else cfg["costs"]["forex_fee_rate"])
            periods_per_year = 24 * 365 if is_crypto else 252
            spread = float(cfg["costs"].get("crypto_spread_rate" if is_crypto else "forex_spread_rate", 0.0))
            slippage = float(cfg["costs"]["slippage_rate"])

            for strategy in STRATEGIES:
                result, metrics = simulate(
                    enriched,
                    strategy,
                    fee_rate=fee,
                    slippage_rate=slippage,
                    initial_cash=initial_cash,
                    periods_per_year=periods_per_year,
                    spread_rate=spread,
                )
                seed = zlib.crc32(f"{path.name}:{strategy}".encode("utf-8")) + 42
                block_size = 24 if is_crypto else 5
                bootstrap = block_bootstrap_validation(
                    result["strategy_return"], block_size=block_size,
                    n_bootstrap=500, seed=seed,
                )
                metrics.update({
                    "bootstrap_ci_lower_pct": bootstrap["bootstrap_ci_lower_pct"],
                    "bootstrap_ci_upper_pct": bootstrap["bootstrap_ci_upper_pct"],
                    "block_bootstrap_p_value": bootstrap["block_bootstrap_p_value"],
                })
                statistical_rows.append({
                    "dataset": path.name,
                    "market_type": "crypto_spot" if is_crypto else "forex_proxy",
                    "strategy": strategy,
                    "block_size": block_size,
                    **bootstrap,
                })
                spot_rows.append({"dataset": path.name, "strategy": strategy, **metrics})

                folds = walk_forward_evaluate(
                    enriched,
                    strategy,
                    train_bars=int(validation_cfg.get("train_bars", 180)),
                    test_bars=int(validation_cfg.get("test_bars", 60)),
                    fee_rate=fee,
                    slippage_rate=slippage,
                    initial_cash=initial_cash,
                    periods_per_year=periods_per_year,
                    spread_rate=spread,
                )
                for fold_metrics in folds:
                    spot_walk_forward_rows.append({
                        "dataset": path.name,
                        "strategy": strategy,
                        **fold_metrics,
                    })
        except Exception as exc:
            print(f"[backtest] ERROR {path.name}: {exc}")

    pd.DataFrame(spot_rows).to_csv(REPORTS / "backtest_summary.csv", index=False)
    pd.DataFrame(spot_walk_forward_rows).to_csv(REPORTS / "walk_forward_summary.csv", index=False)
    summarize_walk_forward(spot_walk_forward_rows).to_csv(REPORTS / "walk_forward_ranking.csv", index=False)

    pd.DataFrame(futures_rows).to_csv(REPORTS / "futures_backtest_summary.csv", index=False)
    pd.DataFrame(futures_walk_forward_rows).to_csv(REPORTS / "futures_walk_forward_summary.csv", index=False)
    statistical = pd.DataFrame(statistical_rows)
    if not statistical.empty:
        statistical["holm_adjusted_p_value"] = holm_adjust(
            statistical["block_bootstrap_p_value"].tolist()
        )
    statistical.to_csv(REPORTS / "statistical_validation.csv", index=False)
    summarize_walk_forward(futures_walk_forward_rows).to_csv(
        REPORTS / "futures_walk_forward_ranking.csv", index=False
    )

    print(f"Spot backtest rows: {len(spot_rows)}; spot walk-forward windows: {len(spot_walk_forward_rows)}")
    print(f"Futures backtest rows: {len(futures_rows)}; futures walk-forward windows: {len(futures_walk_forward_rows)}")
