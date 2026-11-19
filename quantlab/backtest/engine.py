import pandas as pd


def simulate(
    frame,
    signal_col,
    fee_rate=0.001,
    slippage_rate=0.0005,
    initial_cash=100.0,
    periods_per_year=252,
    spread_rate=0.0,
):
    """
    Long/flat close-to-close approximation.
    Signal from bar t-1 is applied to the return ending at bar t.
    Costs are charged on position changes. This is not a tick-level fill model.
    """
    data = frame.copy().reset_index(drop=True)
    required = {"close", signal_col}
    if not required.issubset(data.columns):
        raise ValueError(f"Missing columns: {sorted(required - set(data.columns))}")
    if initial_cash <= 0 or periods_per_year <= 0:
        raise ValueError("initial_cash and periods_per_year must be positive")
    if fee_rate < 0 or slippage_rate < 0 or spread_rate < 0:
        raise ValueError("fee_rate, slippage_rate and spread_rate cannot be negative")

    position = data[signal_col].fillna(0).shift(1).fillna(0).clip(0, 1)
    asset_returns = data["close"].astype(float).pct_change().fillna(0)
    turnover = position.diff().abs().fillna(position.abs())
    transaction_costs = turnover * (float(fee_rate) + float(slippage_rate) + float(spread_rate) / 2.0)

    data["position"] = position
    data["asset_return"] = asset_returns
    data["turnover"] = turnover
    data["transaction_cost"] = transaction_costs
    data["strategy_return"] = position * asset_returns - transaction_costs
    data["equity"] = float(initial_cash) * (1 + data["strategy_return"]).cumprod()

    peak = data["equity"].cummax()
    drawdown = data["equity"] / peak - 1
    trade_count = int((turnover > 0).sum())
    returns = data["strategy_return"]
    std = returns.std(ddof=1)
    sharpe = (
        float((returns.mean() / std) * (float(periods_per_year) ** 0.5))
        if std and pd.notna(std) else 0.0
    )
    gross_profit = float(returns[returns > 0].sum())
    gross_loss = float(-returns[returns < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
        None if gross_profit == 0 else float("inf")
    )
    buy_hold_return = float((data["close"].iloc[-1] / data["close"].iloc[0] - 1) * 100)

    metrics = {
        "total_return_pct": float((data["equity"].iloc[-1] / initial_cash - 1) * 100),
        "buy_hold_return_pct": buy_hold_return,
        "excess_return_pct": float((data["equity"].iloc[-1] / initial_cash - 1) * 100 - buy_hold_return),
        "max_drawdown_pct": float(drawdown.min() * 100),
        "trades": trade_count,
        "sharpe_annualized_rough": sharpe,
        "bar_profit_factor": profit_factor,
        "bar_win_rate_pct": float((returns > 0).mean() * 100),
        "observations": int(len(data)),
    }
    return data, metrics
