from datetime import datetime, timezone

import pandas as pd

from quantlab.data.download import _completed_bars


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
