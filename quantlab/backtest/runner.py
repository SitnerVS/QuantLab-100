from pathlib import Path

import pandas as pd

from quantlab.backtest.engine import simulate
from quantlab.strategies import build_signals

RAW = Path("data/raw")
REPORTS = Path("reports")


def run_backtests(cfg):
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows = []

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
            fee = float(cfg["costs"]["crypto_fee_rate"] if path.name.startswith("crypto_")
                        else cfg["costs"]["forex_fee_rate"])
            for strategy in ("ema_signal", "rsi_signal", "bb_signal", "donchian_signal"):
                _, metrics = simulate(
                    enriched,
                    strategy,
                    fee_rate=fee,
                    slippage_rate=float(cfg["costs"]["slippage_rate"]),
                    initial_cash=float(cfg["backtest"]["initial_cash"]),
                )
                rows.append({"dataset": path.name, "strategy": strategy, **metrics})
        except Exception as exc:
            print(f"[backtest] ERROR {path.name}: {exc}")

    report = pd.DataFrame(rows)
    report.to_csv(REPORTS / "backtest_summary.csv", index=False)
    print(report.to_string(index=False) if not report.empty else "No eligible datasets.")
