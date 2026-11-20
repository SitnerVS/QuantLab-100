import pandas as pd

import quantlab.continuous as continuous


class StopAfterFirstWait:
    def __init__(self):
        self.stopped = False
        self.delays = []

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        self.delays.append(seconds)
        self.stopped = True
        return True


def test_continuous_supervisor_runs_paper_only_after_fresh_data(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(continuous, "download_all", lambda cfg: calls.append("download"))
    monkeypatch.setattr(
        continuous,
        "run_data_quality",
        lambda cfg: pd.DataFrame([{"market_type": "crypto", "status": "OK"}]),
    )
    monkeypatch.setattr(continuous, "run_paper", lambda cfg: calls.append("paper"))
    stopper = StopAfterFirstWait()
    heartbeat = tmp_path / "heartbeat.json"

    result = continuous.run_continuous(
        {}, interval_seconds=1, stop_event=stopper, heartbeat_path=heartbeat
    )

    assert calls == ["download", "paper"]
    assert result["status"] == "STOPPED"
    saved = __import__("json").loads(heartbeat.read_text(encoding="utf-8"))
    assert saved["status"] == "OK"
    assert saved["exchange_orders_enabled"] is False
    assert saved["next_cycle_in_seconds"] == 1
    assert stopper.delays == [1]


def test_continuous_supervisor_fails_closed_when_all_trading_data_is_stale(
    tmp_path, monkeypatch
):
    paper_calls = []
    monkeypatch.setattr(continuous, "download_all", lambda cfg: None)
    monkeypatch.setattr(
        continuous,
        "run_data_quality",
        lambda cfg: pd.DataFrame([{"market_type": "futures", "status": "STALE"}]),
    )
    monkeypatch.setattr(continuous, "run_paper", lambda cfg: paper_calls.append("paper"))
    stopper = StopAfterFirstWait()
    heartbeat = tmp_path / "heartbeat.json"

    result = continuous.run_continuous(
        {}, interval_seconds=1, stop_event=stopper,
        heartbeat_path=heartbeat, max_retry_seconds=1,
    )

    assert paper_calls == []
    assert result["status"] == "STOPPED"
    assert result["consecutive_failures"] == 1
    saved = __import__("json").loads(heartbeat.read_text(encoding="utf-8"))
    assert saved["status"] == "ERROR"
    assert "No fresh crypto/futures" in saved["last_error"]
    assert saved["exchange_orders_enabled"] is False
