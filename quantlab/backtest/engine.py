import pandas as pd


def simulate(frame, signal_col, fee_rate=0.001, slippage_rate=0.0005, initial_cash=100.0):
    """
    Long/flat close-to-close approximation.
    A signal formed on bar t is applied to the return from t to t+1.
    Costs are charged on position changes. This is not a tick-level fill model.
    """
    data = frame.copy().reset_index(drop=True)
    required = {"close", signal_col}
    if not required.issubset(data.columns):
        raise ValueError(f"Missing columns: {sorted(required - set(data.columns))}")

    position = data[signal_col].fillna(0).shift(1).fillna(0).clip(0, 1)
    asset_returns = data["close"].astype(float).pct_change().fillna(0)
    turnover = position.diff().abs().fillna(position.abs())
    transaction_costs = turnover * (float(fee_rate) + float(slippage_rate))

    data["position"] = position
    data["asset_return"] = asset_returns
    data["turnover"] = turnover
    data["strategy_return"] = position * asset_returns - transaction_costs
    data["equity"] = float(initial_cash) * (1 + data["strategy_return"]).cumprod()

    peak = data["equity"].cummax()
    drawdown = data["equity"] / peak - 1
    trade_count = int((turnover > 0).sum())
    returns = data["strategy_return"]
    std = returns.std(ddof=1)
    sharpe = float((returns.mean() / std) * (len(returns) ** 0.5)) if std and pd.notna(std) else 0.0

    metrics = {
        "total_return_pct": float((data["equity"].iloc[-1] / initial_cash - 1) * 100),
        "max_drawdown_pct": float(drawdown.min() * 100),
        "trades": trade_count,
        "sharpe_rough": sharpe,
        "observations": int(len(data)),
    }
    return data, metrics
