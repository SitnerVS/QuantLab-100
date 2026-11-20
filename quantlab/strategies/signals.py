import pandas as pd


def _rsi(close, period=14):
    delta = close.diff()
    gains = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    losses = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    relative_strength = gains / losses.replace(0, float("nan"))
    return 100 - (100 / (1 + relative_strength))


def build_signals(frame):
    """Build causal long/flat signals using current and historical bars only."""
    data = frame.copy()
    close = data["close"].astype(float)

    data["ema_fast"] = close.ewm(span=12, adjust=False).mean()
    data["ema_slow"] = close.ewm(span=26, adjust=False).mean()
    data["rsi"] = _rsi(close)
    data["bb_mid"] = close.rolling(20).mean()
    data["bb_std"] = close.rolling(20).std()
    data["bb_lower"] = data["bb_mid"] - 2 * data["bb_std"]
    data["donchian_upper_prev"] = data["high"].rolling(20).max().shift(1)
    data["sma_fast"] = close.rolling(20).mean()
    data["sma_slow"] = close.rolling(50).mean()
    data["macd_line"] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    data["macd_signal_line"] = data["macd_line"].ewm(span=9, adjust=False).mean()
    data["roc_12"] = close.pct_change(12)

    data["ema_signal"] = (data["ema_fast"] > data["ema_slow"]).astype(int)
    data["rsi_signal"] = (data["rsi"] < 30).astype(int)
    data["bb_signal"] = (close < data["bb_lower"]).astype(int)
    data["donchian_signal"] = (close > data["donchian_upper_prev"]).astype(int)
    data["sma_signal"] = (data["sma_fast"] > data["sma_slow"]).astype(int)
    data["macd_signal"] = (data["macd_line"] > data["macd_signal_line"]).astype(int)
    data["roc_signal"] = (data["roc_12"] > 0).astype(int)
    return data



def build_direction_signals(enriched):
    """Build causal -1/0/+1 signals for isolated long/short futures research."""
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

    data["roc_direction"] = 0
    valid_roc = data["roc_12"].notna()
    data.loc[valid_roc, "roc_direction"] = data.loc[valid_roc, "roc_12"].gt(0).map(
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
