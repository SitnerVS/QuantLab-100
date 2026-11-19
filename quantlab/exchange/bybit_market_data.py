"""Read-only Bybit Demo linear market-data collection (standard library only)."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantlab.exchange.bybit_demo import _require_success, build_demo_session

RAW_DIR = Path("data/raw")
REPORT_PATH = Path("reports/bybit_demo_market_data.json")
TIMEFRAME_MINUTES = {"1": 1, "3": 3, "5": 5, "15": 15, "30": 30, "60": 60, "120": 120, "240": 240, "D": 1440}
CSV_FIELDS = ["timestamp", "open", "high", "low", "close", "volume", "turnover"]


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
    raw_dir, report_path = Path(raw_dir), Path(report_path)
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
        candles = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            try:
                start = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
                values = [float(row[index]) for index in range(1, 6)]
                open_price, high, low, close, volume = values
                turnover = float(row[6]) if len(row) > 6 else 0.0
            except (TypeError, ValueError, OverflowError, OSError):
                continue
            if start + duration > now:
                continue
            if (open_price <= 0 or close <= 0 or high < max(open_price, close)
                    or low > min(open_price, close) or high < low or volume < 0):
                continue
            candles.append({
                "timestamp": start.isoformat(), "open": open_price, "high": high,
                "low": low, "close": close, "volume": volume, "turnover": turnover,
                "_sort": start,
            })
        candles.sort(key=lambda item: item["_sort"])
        deduplicated = {}
        for candle in candles:
            deduplicated[candle["timestamp"]] = candle
        candles = list(deduplicated.values())
        if not candles:
            raise RuntimeError(f"Bybit Demo returned no valid completed candles for {symbol}")
        path = raw_dir / f"bybit_demo_linear_{symbol}_{interval}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for candle in candles:
                writer.writerow({key: candle[key] for key in CSV_FIELDS})
        summaries.append({
            "symbol": symbol, "category": "linear", "interval": interval,
            "rows": len(candles), "first_bar_utc": candles[0]["timestamp"],
            "last_bar_utc": candles[-1]["timestamp"], "file": str(path),
            "invalid_or_incomplete_rows_excluded": len(rows) - len(candles),
        })

    report = {
        "checked_at_utc": now.isoformat(), "exchange": "Bybit", "environment": "DEMO",
        "market_data": summaries, "orders_submitted": 0, "real_trading_enabled": False,
        "status": "DATA_RECEIVED",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
