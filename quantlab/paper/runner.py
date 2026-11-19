from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd

from quantlab.strategies import build_signals

RAW = Path("data/raw")
REPORTS = Path("reports")
STATE = Path("data/processed/paper_state.json")


def run_paper(cfg):
    REPORTS.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)

    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        state = {
            "virtual_cash": cfg["capital"]["portfolios"],
            "last_signal": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    events = []
    for path in sorted(RAW.glob("*.csv")):
        try:
            frame = pd.read_csv(path)
            frame.columns = [str(col).lower() for col in frame.columns]
            required = {"open", "high", "low", "close", "volume"}
            if not required.issubset(frame.columns) or len(frame) < 60:
                continue

            latest = build_signals(frame).iloc[-1]
            key = path.stem
            signal = int(latest["ema_signal"])
            events.append({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "dataset": key,
                "strategy": "ema_signal",
                "signal": signal,
                "previous_signal": state["last_signal"].get(key),
                "last_close": float(latest["close"]),
                "mode": "paper_signal_only",
            })
            state["last_signal"][key] = signal
        except Exception as exc:
            print(f"[paper] ERROR {path.name}: {exc}")

    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(events).to_csv(REPORTS / "paper_signals_latest.csv", index=False)
    print(f"Paper scan complete: {len(events)} signals. No orders or portfolio PnL simulation.")
