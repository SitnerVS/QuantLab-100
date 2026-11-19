from quantlab.data.download import _retry


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
