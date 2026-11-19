from datetime import datetime, timezone

import pandas as pd

from quantlab.data.download import _completed_bars, _filter_valid_ohlc


def test_completed_bars_excludes_current_incomplete_candle():
    frame = pd.DataFrame({
        "timestamp": [
            "2026-01-01T00:00:00Z",
            "2026-01-01T01:00:00Z",
            "2026-01-01T02:00:00Z",
        ],
        "close": [100, 101, 102],
    })
    now = datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc)
    result = _completed_bars(frame, "timestamp", "1h", now=now)
    assert result["close"].tolist() == [100, 101]


def test_completed_bars_sorts_and_deduplicates_timestamps():
    frame = pd.DataFrame({
        "timestamp": [
            "2026-01-01T01:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026-01-01T01:00:00Z",
        ],
        "close": [101, 100, 102],
    })
    now = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
    result = _completed_bars(frame, "timestamp", "1h", now=now)
    assert result["close"].tolist() == [100, 102]


def test_invalid_ohlc_rows_are_removed_and_fx_volume_is_zero_filled():
    frame = pd.DataFrame({
        "open": [1.0, 1.0],
        "high": [1.2, 0.9],
        "low": [0.8, 0.8],
        "close": [1.1, 1.1],
        "volume": [float("nan"), float("nan")],
    })
    result, dropped = _filter_valid_ohlc(frame, require_volume=False)
    assert dropped == 1
    assert len(result) == 1
    assert result["volume"].iloc[0] == 0.0


def test_crypto_ohlc_filter_requires_nonnegative_volume():
    frame = pd.DataFrame({
        "open": [100.0, 100.0],
        "high": [102.0, 102.0],
        "low": [99.0, 99.0],
        "close": [101.0, 101.0],
        "volume": [1.0, -1.0],
    })
    result, dropped = _filter_valid_ohlc(frame, require_volume=True)
    assert dropped == 1
    assert len(result) == 1
