from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
REPORTS = Path("reports")
OHLCV = ["open", "high", "low", "close", "volume"]


def _expected_datasets(cfg):
    expected = []
    crypto = cfg["data"]["crypto"]
    for symbol in crypto["symbols"]:
        safe = symbol.replace("/", "_")
        expected.append((
            f"crypto_{safe}_{crypto['timeframe']}.csv",
            crypto["timeframe"],
            "crypto",
        ))
    forex = cfg["data"]["forex"]
    for symbol in forex["symbols"]:
        expected.append((
            f"forex_{symbol}_{forex['interval']}.csv",
            forex["interval"],
            "forex",
        ))
    return expected


def analyze_dataset(path, timeframe, market_type, now=None):
    now = now or datetime.now(timezone.utc)
    if not path.exists():
        return {
            "dataset": path.name,
            "market_type": market_type,
            "status": "MISSING",
            "rows": 0,
            "duplicate_timestamps": None,
            "missing_ohlcv_rows": None,
            "invalid_ohlc_rows": None,
            "max_gap_hours": None,
            "last_bar_age_hours": None,
            "first_bar_utc": None,
            "last_bar_utc": None,
        }

    frame = pd.read_csv(path)
    frame.columns = [str(col).lower() for col in frame.columns]
    time_col = next((c for c in ("timestamp", "datetime", "date") if c in frame.columns), None)
    if time_col is None or not set(OHLCV).issubset(frame.columns):
        return {
            "dataset": path.name,
            "market_type": market_type,
            "status": "INVALID_SCHEMA",
            "rows": int(len(frame)),
            "duplicate_timestamps": None,
            "missing_ohlcv_rows": None,
            "invalid_ohlc_rows": None,
            "max_gap_hours": None,
            "last_bar_age_hours": None,
            "first_bar_utc": None,
            "last_bar_utc": None,
        }

    parsed = pd.to_datetime(frame[time_col], utc=True, errors="coerce")
    valid_times = parsed.dropna().sort_values()
    duplicates = int(parsed.duplicated().sum())
    missing = int(frame[OHLCV].isna().any(axis=1).sum())
    numeric = frame[OHLCV].apply(pd.to_numeric, errors="coerce")
    invalid = (
        (numeric["high"] < numeric[["open", "close"]].max(axis=1))
        | (numeric["low"] > numeric[["open", "close"]].min(axis=1))
        | (numeric["high"] < numeric["low"])
        | (numeric["close"] <= 0)
        | (numeric["volume"] < 0)
    )
    invalid_rows = int(invalid.fillna(True).sum())

    gaps = valid_times.diff().dropna().dt.total_seconds() / 3600
    max_gap = float(gaps.max()) if not gaps.empty else 0.0
    last_time = valid_times.iloc[-1] if not valid_times.empty else None
    age_hours = (now - last_time.to_pydatetime()).total_seconds() / 3600 if last_time is not None else None

    status = "OK"
    if len(frame) < 60 or valid_times.empty:
        status = "INSUFFICIENT_DATA"
    elif missing or invalid_rows or duplicates:
        status = "WARN"
    elif age_hours is not None:
        stale_after = 4 * 24 if market_type == "forex" else 3 * 24
        if age_hours < -1:
            status = "FUTURE_DATA"
        elif age_hours > stale_after:
            status = "STALE"

    return {
        "dataset": path.name,
        "market_type": market_type,
        "status": status,
        "rows": int(len(frame)),
        "duplicate_timestamps": duplicates,
        "missing_ohlcv_rows": missing,
        "invalid_ohlc_rows": invalid_rows,
        "max_gap_hours": max_gap,
        "last_bar_age_hours": age_hours,
        "first_bar_utc": valid_times.iloc[0].isoformat() if not valid_times.empty else None,
        "last_bar_utc": last_time.isoformat() if last_time is not None else None,
    }


def run_data_quality(cfg):
    REPORTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    rows = [
        analyze_dataset(RAW / filename, timeframe, market_type, now=now)
        for filename, timeframe, market_type in _expected_datasets(cfg)
    ]
    report = pd.DataFrame(rows)
    report.to_csv(REPORTS / "data_quality.csv", index=False)
    usable = int(report["status"].isin(["OK", "WARN", "STALE"]).sum())
    print(report[["dataset", "status", "rows", "duplicate_timestamps", "missing_ohlcv_rows"]].to_string(index=False))
    print(f"Data quality: {usable}/{len(report)} expected datasets available.")
    if usable == 0:
        raise RuntimeError("No usable market datasets; research halted.")
    return report
