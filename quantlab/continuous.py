"""Unattended, restart-safe polling supervisor for paper trading only.

This is an hourly REST-polling process, not a tick-level WebSocket trader.
It never submits exchange orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

from quantlab.data.download import download_all
from quantlab.data.quality import run_data_quality
from quantlab.paper.persistence import write_json_atomic
from quantlab.paper.runner import run_paper

HEARTBEAT = Path("reports/continuous_heartbeat.json")


def run_continuous(
    cfg: dict,
    interval_seconds: int | None = None,
    *,
    stop_event=None,
    heartbeat_path: str | Path = HEARTBEAT,
    max_retry_seconds: int = 300,
):
    """Poll market data, validate freshness and run paper engine until stopped.

    Failed cycles use bounded exponential backoff and do not advance the
    successful-cycle timestamp. The paper engine's durable cursor replays
    missed completed candles on the next successful cycle.
    """
    section = cfg.get("continuous", {})
    interval = int(interval_seconds or section.get("interval_seconds", 3600))
    max_retry = int(max_retry_seconds or section.get("max_retry_seconds", 300))
    if interval < 1 or max_retry < 1:
        raise ValueError("interval_seconds and max_retry_seconds must be positive")

    heartbeat_file = Path(heartbeat_path)
    failures = 0
    last_success = None
    last_error = None

    while stop_event is None or not stop_event.is_set():
        started = datetime.now(timezone.utc)
        status = "ERROR"
        error = None
        try:
            download_all(cfg)
            quality = run_data_quality(cfg)
            fresh_trading_data = quality.loc[
                quality["market_type"].isin(["crypto", "futures"])
                & quality["status"].eq("OK")
            ]
            if fresh_trading_data.empty:
                raise RuntimeError("No fresh crypto/futures datasets passed data-quality checks")
            run_paper(cfg)
            status = "OK"
            failures = 0
            last_success = datetime.now(timezone.utc).isoformat()
            last_error = None
            delay = interval
        except Exception as exc:
            failures += 1
            error = f"{type(exc).__name__}: {exc}"
            last_error = error
            delay = min(max_retry, 15 * (2 ** min(failures - 1, 10)))
            print(f"[continuous] cycle failed ({failures}); retrying in {delay}s: {error}")

        completed = datetime.now(timezone.utc)
        heartbeat = {
            "mode": "CONTINUOUS_PAPER_POLLING",
            "status": status,
            "cycle_started_utc": started.isoformat(),
            "cycle_completed_utc": completed.isoformat(),
            "last_success_utc": last_success,
            "consecutive_failures": failures,
            "last_error": last_error,
            "next_cycle_in_seconds": delay,
            "exchange_orders_enabled": False,
            "execution_note": "Hourly REST polling with paper fills only; no live or Demo orders.",
        }
        write_json_atomic(heartbeat_file, heartbeat)
        print(
            f"[continuous] status={status}; next cycle in {delay}s; "
            f"last_success={last_success or 'none'}"
        )

        if stop_event is not None:
            if stop_event.wait(delay):
                break
        else:
            time.sleep(delay)

    return {
        "status": "STOPPED",
        "last_success_utc": last_success,
        "consecutive_failures": failures,
        "last_error": last_error,
    }
