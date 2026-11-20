import pandas as pd

from quantlab.backtest.engine import simulate


def walk_forward_evaluate(
    frame,
    signal_col,
    train_bars=180,
    test_bars=60,
    fee_rate=0.001,
    slippage_rate=0.0005,
    initial_cash=100.0,
    periods_per_year=252,
    spread_rate=0.0,
):
    """Evaluate a fixed causal signal over rolling chronological test windows.

    No parameters are fitted on the test windows. Signals are calculated
    causally on the full ordered series, and each test return uses the signal
    from the preceding bar. The train window is a warm-up/history window only.
    """
    if train_bars < 2 or test_bars < 1:
        raise ValueError("train_bars must be >= 2 and test_bars must be >= 1")
    if len(frame) <= train_bars:
        return []

    full, _ = simulate(
        frame,
        signal_col,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        initial_cash=initial_cash,
        periods_per_year=periods_per_year,
        spread_rate=spread_rate,
    )
    rows = []
    fold = 0
    for test_start in range(train_bars, len(full), test_bars):
        test_end = min(test_start + test_bars, len(full))
        returns = full["strategy_return"].iloc[test_start:test_end].astype(float)
        if returns.empty:
            continue
        fold += 1
        start_equity = float(full["equity"].iloc[test_start - 1])
        equity = start_equity * (1.0 + returns).cumprod()
        equity_with_start = pd.concat(
            [pd.Series([start_equity]), equity.reset_index(drop=True)],
            ignore_index=True,
        )
        drawdown = equity_with_start / equity_with_start.cummax() - 1.0
        gains = float(returns[returns > 0].sum())
        losses = float(-returns[returns < 0].sum())
        std = returns.std(ddof=1)
        sharpe = (
            float(returns.mean() / std * (periods_per_year ** 0.5))
            if pd.notna(std) and std > 0 else 0.0
        )
        pf = gains / losses if losses > 0 else (None if gains == 0 else float("inf"))
        rows.append({
            "fold": fold,
            "train_observations": int(test_start),
            "test_observations": int(test_end - test_start),
            "test_start_index": int(test_start),
            "test_end_index_exclusive": int(test_end),
            "test_return_pct": float((equity.iloc[-1] / start_equity - 1.0) * 100.0),
            "test_max_drawdown_pct": float(drawdown.min() * 100.0),
            "test_sharpe_annualized": sharpe,
            "test_profit_factor_bar": pf,
            "test_win_rate_pct": float((returns > 0).mean() * 100.0),
        })
    return rows


def summarize_walk_forward(rows):
    """Aggregate fold results without selecting on in-sample performance."""
    if not rows:
        return pd.DataFrame(columns=[
            "dataset", "strategy", "folds", "mean_test_return_pct",
            "median_test_return_pct", "positive_fold_pct",
            "median_test_max_drawdown_pct", "median_test_sharpe_annualized",
        ])
    frame = pd.DataFrame(rows)
    summary = (
        frame.groupby(["dataset", "strategy"], as_index=False)
        .agg(
            folds=("fold", "count"),
            mean_test_return_pct=("test_return_pct", "mean"),
            median_test_return_pct=("test_return_pct", "median"),
            positive_fold_pct=("test_return_pct", lambda values: float((values > 0).mean() * 100)),
            median_test_max_drawdown_pct=("test_max_drawdown_pct", "median"),
            median_test_sharpe_annualized=("test_sharpe_annualized", "median"),
        )
    )
    return summary.sort_values(
        ["dataset", "median_test_return_pct"],
        ascending=[True, False],
    ).reset_index(drop=True)


def walk_forward_futures_evaluate(
    frame,
    signal_col,
    futures_cfg,
    train_bars=180,
    test_bars=60,
    fee_rate=0.0006,
    slippage_rate=0.0005,
    spread_rate=0.0,
    initial_cash=100.0,
):
    """Chronological OOS folds for the isolated-margin simulator."""
    from quantlab.futures.engine import simulate_isolated_long

    if train_bars < 2 or test_bars < 1:
        raise ValueError("train_bars must be >= 2 and test_bars must be >= 1")
    if len(frame) <= train_bars:
        return []

    result, _ = simulate_isolated_long(
        frame,
        signal_col=signal_col,
        funding_col="funding_rate",
        initial_cash=initial_cash,
        leverage=float(futures_cfg["leverage"]),
        max_margin_fraction=float(futures_cfg["max_margin_fraction"]),
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        spread_rate=spread_rate,
        maintenance_margin_rate=float(futures_cfg["maintenance_margin_rate"]),
        liquidation_fee_rate=float(futures_cfg["liquidation_fee_rate"]),
    )
    period_returns = result["equity"].pct_change().fillna(0.0)
    rows = []
    fold = 0
    for test_start in range(train_bars, len(result), test_bars):
        test_end = min(test_start + test_bars, len(result))
        returns = period_returns.iloc[test_start:test_end].astype(float)
        if returns.empty:
            continue
        fold += 1
        start_equity = float(result["equity"].iloc[test_start - 1])
        end_equity = float(result["equity"].iloc[test_end - 1])
        if start_equity > 0:
            normalized = start_equity * (1.0 + returns).cumprod()
            fold_return = (end_equity / start_equity - 1.0) * 100.0
            curve = pd.concat(
                [pd.Series([start_equity]), normalized.reset_index(drop=True)],
                ignore_index=True,
            )
            drawdown = curve / curve.cummax() - 1.0
        else:
            fold_return = -100.0
            drawdown = pd.Series([-1.0])
        std = returns.std(ddof=1)
        sharpe = float(returns.mean() / std * (8760 ** 0.5)) if pd.notna(std) and std > 0 else 0.0
        rows.append({
            "fold": fold,
            "train_observations": int(test_start),
            "test_observations": int(test_end - test_start),
            "test_start_index": int(test_start),
            "test_end_index_exclusive": int(test_end),
            "test_return_pct": float(fold_return),
            "test_max_drawdown_pct": float(drawdown.min() * 100.0),
            "test_sharpe_annualized": sharpe,
            "test_liquidations": int(result["liquidated"].iloc[test_start:test_end].sum()),
            "test_funding_paid_quote": float(result["funding_payment"].iloc[test_start:test_end].sum()),
        })
    return rows



def walk_forward_futures_long_short_evaluate(
    frame,
    signal_col,
    futures_cfg,
    train_bars=180,
    test_bars=60,
    fee_rate=0.0006,
    slippage_rate=0.0005,
    spread_rate=0.0,
    initial_cash=100.0,
    stop_loss_pct=None,
    max_drawdown_pct=None,
):
    """Evaluate independent chronological OOS folds with a fresh paper account.

    Indicator values are calculated causally on the full series. Each test fold
    starts with fresh capital and no inherited position, so a kill switch in one
    fold cannot silently disable all later folds.
    """
    from quantlab.futures.long_short import simulate_isolated_long_short

    if train_bars < 2 or test_bars < 1:
        raise ValueError("train_bars must be >= 2 and test_bars must be >= 1")
    if len(frame) <= train_bars:
        return []

    rows = []
    fold = 0
    for test_start in range(train_bars, len(frame), test_bars):
        test_end = min(test_start + test_bars, len(frame))
        # The preceding bar supplies the first valid lagged signal.
        fold_frame = frame.iloc[test_start - 1:test_end].reset_index(drop=True)
        result, _ = simulate_isolated_long_short(
            fold_frame,
            signal_col=signal_col,
            funding_col="funding_rate",
            initial_cash=initial_cash,
            leverage=float(futures_cfg["leverage"]),
            max_margin_fraction=float(futures_cfg["max_margin_fraction"]),
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            spread_rate=spread_rate,
            maintenance_margin_rate=float(futures_cfg["maintenance_margin_rate"]),
            liquidation_fee_rate=float(futures_cfg["liquidation_fee_rate"]),
            stop_loss_pct=stop_loss_pct,
            max_drawdown_pct=max_drawdown_pct,
        )
        test_result = result.iloc[1:].reset_index(drop=True)
        if test_result.empty:
            continue
        fold += 1
        equity = test_result["equity"].astype(float)
        curve = pd.concat(
            [pd.Series([float(initial_cash)]), equity.reset_index(drop=True)],
            ignore_index=True,
        )
        drawdown = curve / curve.cummax() - 1.0
        returns = equity.pct_change().fillna(
            equity.iloc[0] / float(initial_cash) - 1.0
        )
        std = returns.std(ddof=1)
        sharpe = (
            float(returns.mean() / std * (8760 ** 0.5))
            if pd.notna(std) and std > 0 else 0.0
        )
        rows.append({
            "fold": fold,
            "train_observations": int(test_start),
            "test_observations": int(len(test_result)),
            "test_start_index": int(test_start),
            "test_end_index_exclusive": int(test_end),
            "test_return_pct": float((equity.iloc[-1] / float(initial_cash) - 1.0) * 100.0),
            "test_max_drawdown_pct": float(drawdown.min() * 100.0),
            "test_sharpe_annualized": sharpe,
            "test_liquidations": int(test_result["liquidated"].sum()),
            "test_stop_losses": int(test_result["stop_loss_triggered"].sum()),
            "test_kill_switches": int(test_result["drawdown_kill_switch"].sum()),
            "test_funding_paid_quote": float(test_result["funding_payment"].sum()),
        })
    return rows
