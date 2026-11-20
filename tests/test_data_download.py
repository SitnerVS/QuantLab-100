from datetime import datetime, timezone

from quantlab.data.download import _retry, _fetch_ohlcv_history


def test_retry_recovers_after_transient_failure(monkeypatch):
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("temporary network failure")
        return "ok"

    monkeypatch.setattr("quantlab.data.download.time.sleep", lambda _: None)
    assert _retry("unit-test", operation, attempts=3, base_delay=0) == "ok"
    assert calls["count"] == 3


def test_retry_raises_after_exhausting_attempts(monkeypatch):
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise RuntimeError("still unavailable")

    monkeypatch.setattr("quantlab.data.download.time.sleep", lambda _: None)
    try:
        _retry("unit-test", operation, attempts=2, base_delay=0)
    except RuntimeError as exc:
        assert str(exc) == "still unavailable"
    else:
        raise AssertionError("expected the final network error to be raised")
    assert calls["count"] == 2



def test_futures_ohlcv_history_paginates_without_duplicate_bars():
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    base = int(now.timestamp() * 1000) - 5 * 60 * 1000
    source = [
        [base + index * 60_000, 100 + index, 101 + index, 99 + index, 100 + index, 10]
        for index in range(5)
    ]

    class FakeExchange:
        rateLimit = 0

        def __init__(self):
            self.calls = []

        def fetch_ohlcv(self, symbol, timeframe, since, limit, params):
            self.calls.append((since, limit, params))
            return [row for row in source if row[0] >= since][:limit]

    exchange = FakeExchange()
    rows = _fetch_ohlcv_history(
        exchange, "PF_XBTUSD", "1m",
        target_bars=5, page_limit=2,
        params={"price": "mark"}, now=now,
    )
    assert len(rows) == 5
    assert [row[0] for row in rows] == sorted(row[0] for row in rows)
    assert len({row[0] for row in rows}) == 5
    assert len(exchange.calls) == 3
    assert all(call[2] == {"price": "mark"} for call in exchange.calls)


def test_futures_ohlcv_history_stops_when_exchange_returns_no_rows():
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    class EmptyExchange:
        rateLimit = 0

        def fetch_ohlcv(self, *args, **kwargs):
            return []

    try:
        _fetch_ohlcv_history(
            EmptyExchange(), "PF_XBTUSD", "1h",
            target_bars=10, page_limit=5, now=now,
        )
    except RuntimeError as exc:
        assert "returned no rows" in str(exc)
    else:
        raise AssertionError("expected an empty-history error")
