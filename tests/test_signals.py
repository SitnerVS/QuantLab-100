import pandas as pd

from quantlab.strategies import build_signals


SIGNAL_COLUMNS = [
    "ema_signal",
    "rsi_signal",
    "bb_signal",
    "donchian_signal",
    "sma_signal",
    "macd_signal",
    "roc_signal",
]


def _sample_frame(rows=120):
    close = pd.Series([100 + i * 0.15 + ((i % 9) - 4) * 0.4 for i in range(rows)])
    return pd.DataFrame({
        "open": close - 0.1,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 1000.0,
    })


def test_all_strategy_families_produce_binary_signals():
    result = build_signals(_sample_frame())
    assert set(SIGNAL_COLUMNS).issubset(result.columns)
    for column in SIGNAL_COLUMNS:
        assert set(result[column].dropna().unique()).issubset({0, 1})


def test_signal_calculation_is_causal_and_does_not_use_future_bars():
    frame = _sample_frame(120)
    full = build_signals(frame)
    truncated = build_signals(frame.iloc[:80])
    pd.testing.assert_frame_equal(
        full.loc[:79, SIGNAL_COLUMNS].reset_index(drop=True),
        truncated[SIGNAL_COLUMNS].reset_index(drop=True),
    )


def test_sma_macd_and_momentum_detect_persistent_uptrend():
    frame = _sample_frame(120)
    frame["close"] = [100 + i for i in range(120)]
    frame["open"] = frame["close"] - 0.2
    frame["high"] = frame["close"] + 0.5
    frame["low"] = frame["close"] - 0.5
    result = build_signals(frame)
    assert result.iloc[-1]["sma_signal"] == 1
    assert result.iloc[-1]["macd_signal"] == 1
    assert result.iloc[-1]["roc_signal"] == 1
