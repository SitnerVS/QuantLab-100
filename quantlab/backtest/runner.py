from pathlib import Path

import pandas as pd

from quantlab.backtest.engine import simulate
from quantlab.backtest.validation import walk_forward_evaluate
from quantlab.strategies import build_signals

RAW = Path("data/raw")
REPORTS = Path("reports")


def run_backtests(cfg):
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows = []
    walk_forward_rows = []

    for path in sorted(RAW.glob("*.csv")):
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
            is_crypto = path.name.startswith("crypto_")
            fee = float(cfg["costs"]["crypto_fee_rate"] if is_crypto else cfg["costs"]["forex_fee_rate"])
            periods_per_year = 24 * 365 if is_crypto else 252
            for strategy in ("ema_signal", "rsi_signal", "bb_signal", "donchian_signal"):
                _, metrics = simulate(
                    enriched,
                    strategy,
                    fee_rate=fee,
                    slippage_rate=float(cfg["costs"]["slippage_rate"]),
                    initial_cash=float(cfg["backtest"]["initial_cash"]),
                    periods_per_year=periods_per_year,
                )
                rows.append({"dataset": path.name, "strategy": strategy, **metrics})

                validation_cfg = cfg.get("validation", {})
                folds = walk_forward_evaluate(
                    enriched,
                    strategy,
                    train_bars=int(validation_cfg.get("train_bars", 180)),
                    test_bars=int(validation_cfg.get("test_bars", 60)),
                    fee_rate=fee,
                    slippage_rate=float(cfg["costs"]["slippage_rate"]),
                    initial_cash=float(cfg["backtest"]["initial_cash"]),
                    periods_per_year=periods_per_year,
                )
                for fold_metrics in folds:
                    walk_forward_rows.append({
                        "dataset": path.name,
                        "strategy": strategy,
                        **fold_metrics,
                    })
        except Exception as exc:
            print(f"[backtest] ERROR {path.name}: {exc}")

    pd.DataFrame(rows).to_csv(REPORTS / "backtest_summary.csv", index=False)
    pd.DataFrame(walk_forward_rows).to_csv(REPORTS / "walk_forward_summary.csv", index=False)
    report = pd.DataFrame(rows)
    print(report.to_string(index=False) if not report.empty else "No eligible datasets.")
    print(f"Walk-forward test windows: {len(walk_forward_rows)}")
