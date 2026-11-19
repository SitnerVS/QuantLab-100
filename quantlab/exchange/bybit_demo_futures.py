"""Read-only Bybit Demo linear perpetual mark/funding data collector.

Output is deliberately isolated under data/bybit_demo/ until data-quality
and accounting validation are complete; it is not consumed by the paper engine.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantlab.exchange.bybit_demo import _require_success, build_demo_session

OUTPUT_DIR = Path("data/bybit_demo")
REPORT_PATH = Path("reports/bybit_demo_futures_data.json")
TIMEFRAME_MINUTES = {"1": 1, "3": 3, "5": 5, "15": 15, "30": 30, "60": 60, "120": 120, "240": 240, "D": 1440}
FIELDS = [
    "timestamp", "open", "high", "low", "close", "volume", "turnover",
    "funding_rate", "funding_settlement_utc", "min_order_size",
    "min_notional_usd", "qty_step", "tick_size", "max_leverage",
]


def _parse_candle(row, duration, now):
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        return None
    try:
        start_ms = int(row[0])
        start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        prices = [float(row[index]) for index in range(1, 5)]
        volume = float(row[5])
        turnover = float(row[6]) if len(row) > 6 else 0.0
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    open_price, high, low, close = prices
    if start + duration > now:
        return None
    if (open_price <= 0 or close <= 0 or high < max(open_price, close)
            or low > min(open_price, close) or high < low
            or volume < 0 or turnover < 0):
        return None
    return {
        "start_ms": start_ms,
        "timestamp": start.isoformat(),
        "open": open_price, "high": high, "low": low, "close": close,
        "volume": volume, "turnover": turnover,
        "close_ms": start_ms + int(duration.total_seconds() * 1000),
    }


def fetch_bybit_demo_futures_data(
    client=None,
    symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    interval="60",
    limit=720,
    funding_limit=200,
    now=None,
    output_dir=OUTPUT_DIR,
    report_path=REPORT_PATH,
    min_rows=60,
):
    """Collect closed linear perpetual mark candles, settlement funding and contract rules."""
    if interval not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported Bybit kline interval: {interval}")
    if not 1 <= int(limit) <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not 1 <= int(funding_limit) <= 200:
        raise ValueError("funding_limit must be between 1 and 200")
    session = client or build_demo_session()
    now = now or datetime.now(timezone.utc)
    duration = timedelta(minutes=TIMEFRAME_MINUTES[interval])
    now_ms = int(now.timestamp() * 1000)
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

        kline_response = _require_success(
            session.get_kline(
                category="linear", symbol=symbol, interval=interval, limit=int(limit),
            ),
            f"{symbol} mark klines",
        )
        candles = [
            candle for row in kline_response.get("list", [])
            if (candle := _parse_candle(row, duration, now)) is not None
        ]
        candles.sort(key=lambda item: item["start_ms"])
        deduped = {item["start_ms"]: item for item in candles}
        candles = list(deduped.values())
        if len(candles) < int(min_rows):
            raise RuntimeError(
                f"{symbol}: only {len(candles)} valid completed mark candles; "
                f"minimum required is {int(min_rows)}"
            )

        funding_response = _require_success(
            session.get_funding_rate_history(
                category="linear", symbol=symbol, limit=int(funding_limit),
            ),
            f"{symbol} funding history",
        )
        funding_rows = funding_response.get("list", [])
        funding_by_time = {}
        for item in funding_rows:
            try:
                timestamp_ms = int(item["fundingRateTimestamp"])
                rate = float(item["fundingRate"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if timestamp_ms <= now_ms:
                funding_by_time[timestamp_ms] = rate

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
                "candle boundaries; refusing to fabricate hourly funding values"
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
        "exchange": "Bybit",
        "environment": "DEMO",
        "market_type": "linear_perpetual",
        "price_basis": "mark",
        "funding_alignment": "settlement timestamp matched to completed candle close",
        "symbols": summaries,
        "orders_submitted": 0,
        "real_trading_enabled": False,
        "paper_engine_integration": False,
        "status": "FUTURES_DATA_RECEIVED",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
