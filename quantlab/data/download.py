from datetime import timedelta, timezone, datetime
from pathlib import Path
import time

import ccxt
import pandas as pd
import yfinance as yf

RAW = Path("data/raw")
INTERVAL_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
    "1wk": 10080,
}


def _completed_bars(frame, timestamp_column, timeframe):
    """Remove the still-forming last candle and normalize chronological order."""
    minutes = INTERVAL_MINUTES.get(timeframe)
    if minutes is None:
        raise ValueError(f"Unsupported timeframe for closed-bar filtering: {timeframe}")
    result = frame.copy()
    parsed = pd.to_datetime(result[timestamp_column], utc=True, errors="coerce")
    result = result.loc[parsed.notna()].copy()
    result["_timestamp_utc"] = parsed.loc[parsed.notna()]
    now = datetime.now(timezone.utc)
    duration = timedelta(minutes=minutes)
    result = result.loc[result["_timestamp_utc"] + duration <= now]
    result = result.sort_values("_timestamp_utc").drop_duplicates("_timestamp_utc", keep="last")
    result[timestamp_column] = result["_timestamp_utc"]
    return result.drop(columns=["_timestamp_utc"])


def download_crypto(cfg):
    section = cfg["data"]["crypto"]
    exchange_name = section.get("exchange", "kraken")
    exchange_cls = getattr(ccxt, exchange_name)
    exchange = exchange_cls({"enableRateLimit": True})
    RAW.mkdir(parents=True, exist_ok=True)

    for symbol in section["symbols"]:
        safe_symbol = symbol.replace("/", "_")
        try:
            rows = exchange.fetch_ohlcv(
                symbol,
                timeframe=section["timeframe"],
                limit=int(section["limit"]),
            )
            frame = pd.DataFrame(
                rows,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
            frame = _completed_bars(frame, "timestamp", section["timeframe"])
            if frame.empty:
                raise RuntimeError("source returned no completed OHLCV candles")
            frame.to_csv(
                RAW / f"crypto_{safe_symbol}_{section['timeframe']}.csv",
                index=False,
            )
            print(f"[crypto:{exchange_name}] {symbol}: {len(frame)} completed rows")
            time.sleep(exchange.rateLimit / 1000)
        except Exception as exc:
            print(f"[crypto:{exchange_name}] ERROR {symbol}: {exc}")


def download_forex(cfg):
    section = cfg["data"]["forex"]
    RAW.mkdir(parents=True, exist_ok=True)

    for symbol in section["symbols"]:
        try:
            frame = yf.download(
                symbol,
                period=section["period"],
                interval=section["interval"],
                auto_adjust=False,
                progress=False,
            )
            if frame.empty:
                raise RuntimeError("source returned no rows")
            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)
            frame = frame.reset_index()
            frame.columns = [str(col).lower().replace(" ", "_") for col in frame.columns]
            time_col = next((c for c in ("date", "datetime", "timestamp") if c in frame.columns), None)
            if time_col is None:
                raise RuntimeError("source response has no date column")
            frame = _completed_bars(frame, time_col, section["interval"])
            if frame.empty:
                raise RuntimeError("source returned no completed OHLCV candles")
            frame.to_csv(RAW / f"forex_{symbol}_{section['interval']}.csv", index=False)
            print(f"[forex proxy] {symbol}: {len(frame)} completed rows")
        except Exception as exc:
            print(f"[forex proxy] ERROR {symbol}: {exc}")


def download_all(cfg):
    download_crypto(cfg)
    download_forex(cfg)
