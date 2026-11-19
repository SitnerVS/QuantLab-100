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


def _retry(label, operation, attempts=3, base_delay=1.0):
    """Retry transient public-data requests with bounded exponential backoff."""
    if int(attempts) < 1 or float(base_delay) < 0:
        raise ValueError("attempts must be positive and base_delay non-negative")
    for attempt in range(1, int(attempts) + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt >= int(attempts):
                raise
            delay = float(base_delay) * (2 ** (attempt - 1))
            print(f"[data] {label} failed ({attempt}/{attempts}): {exc}; retrying in {delay:.1f}s")
            time.sleep(delay)


def _completed_bars(frame, timestamp_column, timeframe, now=None):
    """Remove the still-forming last candle and normalize chronological order."""
    minutes = INTERVAL_MINUTES.get(timeframe)
    if minutes is None:
        raise ValueError(f"Unsupported timeframe for closed-bar filtering: {timeframe}")
    result = frame.copy()
    parsed = pd.to_datetime(result[timestamp_column], utc=True, errors="coerce")
    result = result.loc[parsed.notna()].copy()
    result["_timestamp_utc"] = parsed.loc[parsed.notna()]
    now = now or datetime.now(timezone.utc)
    duration = timedelta(minutes=minutes)
    result = result.loc[result["_timestamp_utc"] + duration <= now]
    result = result.sort_values("_timestamp_utc").drop_duplicates("_timestamp_utc", keep="last")
    result[timestamp_column] = result["_timestamp_utc"]
    return result.drop(columns=["_timestamp_utc"])


def _filter_valid_ohlc(frame, require_volume=False):
    result = frame.copy()
    price_cols = ["open", "high", "low", "close"]
    prices = result[price_cols].apply(pd.to_numeric, errors="coerce")
    valid = prices.notna().all(axis=1)
    valid &= prices["open"].gt(0) & prices["close"].gt(0)
    valid &= prices["high"].ge(prices[["open", "close"]].max(axis=1))
    valid &= prices["low"].le(prices[["open", "close"]].min(axis=1))
    valid &= prices["high"].ge(prices["low"])

    if require_volume:
        if "volume" not in result.columns:
            raise ValueError("volume column is required for crypto OHLCV")
        volume = pd.to_numeric(result["volume"], errors="coerce")
        valid &= volume.notna() & volume.ge(0)
    else:
        if "volume" not in result.columns:
            result["volume"] = 0.0
        else:
            result["volume"] = pd.to_numeric(result["volume"], errors="coerce").fillna(0.0)

    dropped = int((~valid).sum())
    result = result.loc[valid].copy()
    for column in price_cols:
        result[column] = prices.loc[valid, column]
    return result, dropped


def download_crypto(cfg):
    section = cfg["data"]["crypto"]
    exchange_name = section.get("exchange", "kraken")
    exchange_cls = getattr(ccxt, exchange_name)
    exchange = exchange_cls({"enableRateLimit": True})
    _retry(f"{exchange_name} load markets", exchange.load_markets)
    RAW.mkdir(parents=True, exist_ok=True)

    for symbol in section["symbols"]:
        safe_symbol = symbol.replace("/", "_")
        try:
            market = exchange.market(symbol)
            limits = market.get("limits") or {}
            info = market.get("info") or {}
            amount_limits = limits.get("amount") or {}
            cost_limits = limits.get("cost") or {}
            min_order_size = amount_limits.get("min") or info.get("ordermin")
            min_notional = cost_limits.get("min") or info.get("costmin") or 0.0
            if min_order_size is None or float(min_order_size) <= 0:
                raise RuntimeError(f"minimum order quantity is unavailable for {symbol}")
            rows = _retry(
                f"{symbol} OHLCV",
                lambda: exchange.fetch_ohlcv(
                    symbol,
                    timeframe=section["timeframe"],
                    limit=int(section["limit"]),
                ),
            )
            frame = pd.DataFrame(
                rows,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
            frame = _completed_bars(frame, "timestamp", section["timeframe"])
            frame, dropped = _filter_valid_ohlc(frame, require_volume=True)
            frame["min_order_size"] = float(min_order_size)
            frame["min_notional_usd"] = float(min_notional)
            if frame.empty:
                raise RuntimeError("source returned no completed OHLCV candles")
            frame.to_csv(
                RAW / f"crypto_{safe_symbol}_{section['timeframe']}.csv",
                index=False,
            )
            print(f"[crypto:{exchange_name}] {symbol}: {len(frame)} valid completed rows; filtered {dropped} invalid rows")
            time.sleep(exchange.rateLimit / 1000)
        except Exception as exc:
            print(f"[crypto:{exchange_name}] ERROR {symbol}: {exc}")


def download_forex(cfg):
    section = cfg["data"]["forex"]
    RAW.mkdir(parents=True, exist_ok=True)

    for symbol in section["symbols"]:
        try:
            frame = _retry(
                f"{symbol} Yahoo Finance",
                lambda: yf.download(
                    symbol,
                    period=section["period"],
                    interval=section["interval"],
                    auto_adjust=False,
                    progress=False,
                ),
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
            frame, dropped = _filter_valid_ohlc(frame, require_volume=False)
            if frame.empty:
                raise RuntimeError("source returned no completed OHLCV candles")
            frame.to_csv(RAW / f"forex_{symbol}_{section['interval']}.csv", index=False)
            print(f"[forex proxy] {symbol}: {len(frame)} valid completed rows; filtered {dropped} invalid rows")
        except Exception as exc:
            print(f"[forex proxy] ERROR {symbol}: {exc}")


def download_futures(cfg):
    section = cfg["data"].get("futures", {})
    symbols = section.get("symbols", [])
    if not symbols:
        print("[futures] No contracts configured; skipping.")
        return

    exchange = ccxt.krakenfutures({"enableRateLimit": True})
    markets = _retry("Kraken Futures load markets", exchange.load_markets)
    RAW.mkdir(parents=True, exist_ok=True)

    for instrument in symbols:
        try:
            market = next((item for item in markets.values() if item.get("id") == instrument), None)
            if market is None or not market.get("swap") or not market.get("linear"):
                raise RuntimeError(f"{instrument} is not an available linear perpetual contract")
            symbol = market["symbol"]
            minimum = section.get("min_order_sizes", {}).get(instrument)
            if minimum is None:
                minimum = market.get("limits", {}).get("amount", {}).get("min")
            if minimum is None or float(minimum) <= 0:
                raise RuntimeError(f"minimum contract quantity is unavailable for {instrument}")
            candles = _retry(
                f"{instrument} mark OHLCV",
                lambda: exchange.fetch_ohlcv(
                    symbol,
                    timeframe=section.get("timeframe", "1h"),
                    limit=int(section.get("limit", 720)),
                    params={"price": "mark"},
                ),
            )
            frame = pd.DataFrame(
                candles,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
            frame = _completed_bars(frame, "timestamp", section.get("timeframe", "1h"))

            response = _retry(
                f"{instrument} historical funding",
                lambda: exchange.publicGetHistoricalfundingrates({"symbol": instrument}),
            )
            rates = response.get("rates", [])
            if response.get("result") != "success" or not rates:
                raise RuntimeError("historical funding endpoint returned no rates")
            funding = pd.DataFrame(rates)
            funding["timestamp"] = pd.to_datetime(funding["timestamp"], utc=True, errors="coerce")
            funding["funding_rate"] = pd.to_numeric(
                funding["relativeFundingRate"], errors="coerce"
            )
            funding = funding[["timestamp", "funding_rate"]].dropna()
            funding = funding.sort_values("timestamp").drop_duplicates("timestamp", keep="last")

            frame = frame.merge(funding, on="timestamp", how="left")
            missing_funding = int(frame["funding_rate"].isna().sum())
            frame = frame.dropna(subset=["funding_rate"])
            frame, dropped = _filter_valid_ohlc(frame, require_volume=True)
            frame["min_order_size"] = float(minimum)
            if frame.empty or len(frame) < 60:
                raise RuntimeError(
                    f"insufficient aligned mark/funding history; missing funding candles={missing_funding}"
                )
            frame.to_csv(
                RAW / f"futures_{instrument}_{section.get('timeframe', '1h')}.csv",
                index=False,
            )
            print(
                f"[futures:kraken] {instrument}: {len(frame)} aligned mark/funding rows; "
                f"missing funding candles={missing_funding}; invalid OHLC rows filtered={dropped}"
            )
            time.sleep(exchange.rateLimit / 1000)
        except Exception as exc:
            print(f"[futures:kraken] ERROR {instrument}: {exc}")


def download_all(cfg):
    download_crypto(cfg)
    download_forex(cfg)
    download_futures(cfg)
