"""Read-only Bybit Demo linear market-data collection."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from quantlab.exchange.bybit_demo import _require_success, build_demo_session

RAW_DIR = Path("data/raw")
REPORT_PATH = Path("reports/bybit_demo_market_data.json")
TIMEFRAME_MINUTES = {"1": 1, "3": 3, "5": 5, "15": 15, "30": 30, "60": 60, "120": 120, "240": 240, "D": 1440}


def fetch_demo_market_data(
    client=None,
    symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    interval="60",
    limit=200,
    now=None,
    raw_dir=RAW_DIR,
    report_path=REPORT_PATH,
):
    """Download completed linear candles from Bybit Demo; never submits orders."""
    if interval not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported Bybit kline interval: {interval}")
    if not 1 <= int(limit) <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    session = client or build_demo_session()
    now = now or datetime.now(timezone.utc)
    duration = timedelta(minutes=TIMEFRAME_MINUTES[interval])
    raw_dir = Path(raw_dir)
    report_path = Path(report_path)
    raw_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    for symbol in symbols:
        response = _require_success(
            session.get_kline(category="linear", symbol=symbol, interval=interval, limit=int(limit)),
            f"{symbol} market klines",
        )
        rows = response.get("list", [])
        if not rows:
            raise RuntimeError(f"Bybit Demo returned no kline rows for {symbol}")
        frame = pd.DataFrame(
            rows,
            columns=["start_ms", "open", "high", "low", "close", "volume", "turnover"],
        )
        frame["timestamp"] = pd.to_datetime(pd.to_numeric(frame.pop("start_ms"), errors="coerce"), unit="ms", utc=True)
        for column in ("open", "high", "low", "close", "volume", "turnover"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
        frame = frame.loc[frame["timestamp"] + duration <= now].copy()
        valid = (
            frame["open"].gt(0) & frame["high"].ge(frame[["open", "close"]].max(axis=1))
            & frame["low"].le(frame[["open", "close"]].min(axis=1))
            & frame["high"].ge(frame["low"]) & frame["volume"].ge(0)
        )
        frame = frame.loc[valid].sort_values("timestamp").drop_duplicates("timestamp", keep="last")
        if frame.empty:
            raise RuntimeError(f"Bybit Demo returned no valid completed candles for {symbol}")
        frame = frame[["timestamp", "open", "high", "low", "close", "volume", "turnover"]]
        path = raw_dir / f"bybit_demo_linear_{symbol}_{interval}.csv"
        frame.to_csv(path, index=False)
        summaries.append({
            "symbol": symbol, "category": "linear", "interval": interval,
            "rows": int(len(frame)), "first_bar_utc": frame["timestamp"].iloc[0].isoformat(),
            "last_bar_utc": frame["timestamp"].iloc[-1].isoformat(),
            "file": str(path), "invalid_or_incomplete_rows_excluded": int(len(rows) - len(frame)),
        })

    report = {
        "checked_at_utc": now.isoformat(), "exchange": "Bybit", "environment": "DEMO",
        "market_data": summaries, "orders_submitted": 0, "real_trading_enabled": False,
        "status": "DATA_RECEIVED",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
