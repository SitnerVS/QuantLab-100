from pathlib import Path
import time

import ccxt
import pandas as pd
import yfinance as yf

RAW = Path("data/raw")


def download_crypto(cfg):
    section = cfg["data"]["crypto"]
    exchange_cls = getattr(ccxt, section.get("exchange", "binance"))
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
            frame.to_csv(
                RAW / f"crypto_{safe_symbol}_{section['timeframe']}.csv",
                index=False,
            )
            print(f"[crypto] {symbol}: {len(frame)} rows")
            time.sleep(exchange.rateLimit / 1000)
        except Exception as exc:
            print(f"[crypto] ERROR {symbol}: {exc}")


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
            frame.to_csv(RAW / f"forex_{symbol}_{section['interval']}.csv", index=False)
            print(f"[forex proxy] {symbol}: {len(frame)} rows")
        except Exception as exc:
            print(f"[forex proxy] ERROR {symbol}: {exc}")


def download_all(cfg):
    download_crypto(cfg)
    download_forex(cfg)
