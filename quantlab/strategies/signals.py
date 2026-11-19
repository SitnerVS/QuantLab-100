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

    data["ema_signal"] = (data["ema_fast"] > data["ema_slow"]).astype(int)
    data["rsi_signal"] = (data["rsi"] < 30).astype(int)
    data["bb_signal"] = (close < data["bb_lower"]).astype(int)
    data["donchian_signal"] = (close > data["donchian_upper_prev"]).astype(int)
    return data
