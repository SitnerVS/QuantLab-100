"""Read-only Bybit Demo linear perpetual mark/funding data collector."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantlab.exchange.bybit_demo import _require_success, build_public_market_session

OUTPUT_DIR = Path("data/bybit_demo")
REPORT_PATH = Path("reports/bybit_demo_futures_data.json")
TIMEFRAME_MINUTES = {"1": 1, "3": 3, "5": 5, "15": 15, "30": 30, "60": 60, "120": 120, "240": 240, "D": 1440}
FIELDS = [
    "timestamp", "open", "high", "low", "close", "volume", "turnover",
    "funding_rate", "funding_settlement_utc", "min_order_size",
    "min_notional_usd", "qty_step", "tick_size", "max_leverage",
]


def _parse_candle(row, duration, now):
    if not isinstance(row, (list, tuple)) or len(row) < 5:
        return None
    try:
        start_ms = int(row[0])
        start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        open_price, high, low, close = [float(row[index]) for index in range(1, 5)]
        # Bybit mark-price klines contain OHLC only; trade volume is not provided.
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if start + duration > now:
        return None
    if (open_price <= 0 or close <= 0 or high < max(open_price, close)
            or low > min(open_price, close) or high < low):
        return None
    return {
        "start_ms": start_ms,
        "timestamp": start.isoformat(),
        "open": open_price, "high": high, "low": low, "close": close,
        "volume": 0.0, "turnover": 0.0,
        "close_ms": start_ms + int(duration.total_seconds() * 1000),
    }


def _fetch_mark_rows(session, symbol, interval, start_ms, end_ms, page_limit):
    collected = {}
    cursor_end = end_ms
    for _ in range(100):
        response = _require_success(
            session.get_mark_price_kline(
                category="linear", symbol=symbol, interval=interval,
                start=start_ms, end=cursor_end, limit=int(page_limit),
            ),
            f"{symbol} mark-price klines",
        )
        rows = response.get("list", [])
        if not rows:
            break
        page_times = []
        for row in rows:
            try:
                stamp = int(row[0])
            except (TypeError, ValueError, IndexError):
                continue
            if start_ms <= stamp <= end_ms:
                collected[stamp] = row
                page_times.append(stamp)
        if not page_times or len(rows) < int(page_limit):
            break
        oldest = min(page_times)
        if oldest <= start_ms:
            break
        if oldest >= cursor_end:
            raise RuntimeError(f"{symbol}: mark-price pagination did not move backwards")
        cursor_end = oldest - 1
    else:
        raise RuntimeError(f"{symbol}: mark-price pagination exceeded 100 pages")
    return [collected[key] for key in sorted(collected)]


def _fetch_funding_rows(session, symbol, start_ms, end_ms, page_limit):
    collected = {}
    cursor_end = end_ms
    for _ in range(100):
        response = _require_success(
            session.get_funding_rate_history(
                category="linear", symbol=symbol,
                startTime=start_ms, endTime=cursor_end, limit=int(page_limit),
            ),
            f"{symbol} funding history",
        )
        rows = response.get("list", [])
        if not rows:
            break
        page_times = []
        for item in rows:
            try:
                stamp = int(item["fundingRateTimestamp"])
                rate = float(item["fundingRate"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if start_ms <= stamp <= end_ms:
                collected[stamp] = rate
                page_times.append(stamp)
        if not page_times or len(rows) < int(page_limit):
            break
        oldest = min(page_times)
        if oldest <= start_ms:
            break
        if oldest >= cursor_end:
            raise RuntimeError(f"{symbol}: funding pagination did not move backwards")
        cursor_end = oldest - 1
    else:
        raise RuntimeError(f"{symbol}: funding pagination exceeded 100 pages")
    return collected


def fetch_bybit_demo_futures_data(
    client=None,
    symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    interval="60",
    history_days=180,
    kline_page_limit=1000,
    funding_page_limit=200,
    now=None,
    output_dir=OUTPUT_DIR,
    report_path=REPORT_PATH,
    min_rows=60,
):
    """Collect closed mark-price candles, settlement funding and contract rules."""
    if interval not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported Bybit kline interval: {interval}")
    if int(history_days) < 1 or int(history_days) > 3650:
        raise ValueError("history_days must be between 1 and 3650")
    if not 1 <= int(kline_page_limit) <= 1000:
        raise ValueError("kline_page_limit must be between 1 and 1000")
    if not 1 <= int(funding_page_limit) <= 200:
        raise ValueError("funding_page_limit must be between 1 and 200")
    session = client or build_public_market_session()
    now = now or datetime.now(timezone.utc)
    duration = timedelta(minutes=TIMEFRAME_MINUTES[interval])
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(days=int(history_days))).timestamp() * 1000)
    output_dir, report_path = Path(output_dir), Path(report_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    for symbol in symbols:
        instrument_response = _require_success(
            session.get_instruments_info(category="linear", symbol=symbol),
            f"{symbol} instrument info",
        )
        instruments = instrument_response.get("list", [])
        if not instruments:
            raise RuntimeError(f"Bybit Demo returned no instrument metadata for {symbol}")
        instrument = instruments[0]
        lot = instrument.get("lotSizeFilter") or {}
        price_filter = instrument.get("priceFilter") or {}
        leverage_filter = instrument.get("leverageFilter") or {}
        min_order_size = float(lot.get("minOrderQty") or 0)
        if min_order_size <= 0:
            raise RuntimeError(f"{symbol}: minimum order quantity is missing or invalid")
        min_notional = float(lot.get("minNotionalValue") or 0)
        qty_step = float(lot.get("qtyStep") or 0)
        tick_size = float(price_filter.get("tickSize") or 0)
        max_leverage = float(leverage_filter.get("maxLeverage") or 0)

        raw_rows = _fetch_mark_rows(
            session, symbol, interval, start_ms, end_ms, int(kline_page_limit)
        )
        candles = [
            candle for row in raw_rows
            if (candle := _parse_candle(row, duration, now)) is not None
        ]
        if len(candles) < int(min_rows):
            raise RuntimeError(
                f"{symbol}: only {len(candles)} valid completed mark candles; "
                f"minimum required is {int(min_rows)}"
            )

        funding_by_time = _fetch_funding_rows(
            session, symbol, start_ms, end_ms, int(funding_page_limit)
        )
        close_times = {item["close_ms"] for item in candles}
        first_close, last_close = min(close_times), max(close_times)
        funding_in_window = {
            timestamp: rate for timestamp, rate in funding_by_time.items()
            if first_close <= timestamp <= last_close
        }
        unmatched = sorted(set(funding_in_window) - close_times)
        if unmatched:
            raise RuntimeError(
                f"{symbol}: {len(unmatched)} funding settlements do not align to closed "
                "mark-candle boundaries; refusing to fabricate hourly funding values"
            )
        if not funding_in_window:
            raise RuntimeError(f"{symbol}: no funding settlements align with the mark-candle window")

        for candle in candles:
            rate = funding_by_time.get(candle["close_ms"], 0.0)
            settlement = (
                datetime.fromtimestamp(candle["close_ms"] / 1000, tz=timezone.utc).isoformat()
                if candle["close_ms"] in funding_by_time else ""
            )
            candle.update({
                "funding_rate": rate,
                "funding_settlement_utc": settlement,
                "min_order_size": min_order_size,
                "min_notional_usd": min_notional,
                "qty_step": qty_step,
                "tick_size": tick_size,
                "max_leverage": max_leverage,
            })

        path = output_dir / f"bybit_demo_linear_{symbol}_{interval}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for candle in candles:
                writer.writerow({field: candle[field] for field in FIELDS})

        summaries.append({
            "symbol": symbol,
            "category": "linear",
            "contract_type": instrument.get("contractType"),
            "interval": interval,
            "history_days_requested": int(history_days),
            "rows": len(candles),
            "first_bar_utc": candles[0]["timestamp"],
            "last_bar_utc": candles[-1]["timestamp"],
            "funding_settlements_matched": len(funding_in_window),
            "funding_rate_nonzero_rows": sum(1 for item in candles if item["funding_rate"] != 0),
            "min_order_size": min_order_size,
            "min_notional_usd": min_notional,
            "qty_step": qty_step,
            "tick_size": tick_size,
            "max_leverage": max_leverage,
            "file": str(path),
        })

    report = {
        "checked_at_utc": now.isoformat(),
        "history_start_utc": datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat(),
        "history_days_requested": int(history_days),
        "exchange": "Bybit",
        "environment": "MAINNET_PUBLIC_MARKET_DATA",
        "market_type": "linear_perpetual",
        "market_data_endpoint": "api.bytick.com",
        "source_note": "Unauthenticated mainnet public market data; Bybit documents Demo public market data as identical to mainnet public market data.",
        "price_basis": "mark",
        "volume_note": "Mark-price kline endpoint does not return traded volume; volume and turnover are zero placeholders.",
        "funding_alignment": "settlement timestamp matched to completed mark-candle close",
        "symbols": summaries,
        "orders_submitted": 0,
        "real_trading_enabled": False,
        "paper_engine_integration": False,
        "status": "FUTURES_DATA_RECEIVED",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "
", encoding="utf-8")
    return report
