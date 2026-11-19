import csv
from datetime import datetime, timezone

import pytest

from quantlab.exchange.bybit_demo_futures import fetch_bybit_demo_futures_data


class FakeFuturesClient:
    def get_instruments_info(self, **kwargs):
        assert kwargs == {"category": "linear", "symbol": "BTCUSDT"}
        return {"retCode": 0, "result": {"list": [{
            "contractType": "LinearPerpetual",
            "lotSizeFilter": {"minOrderQty": "0.001", "minNotionalValue": "5", "qtyStep": "0.001"},
            "priceFilter": {"tickSize": "0.1"},
            "leverageFilter": {"maxLeverage": "100"},
        }]}}

    def get_kline(self, **kwargs):
        assert kwargs == {"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": 3}
        return {"retCode": 0, "result": {"list": [
            ["1767232800000", "110", "112", "109", "111", "12", "1332"],
            ["1767229200000", "100", "111", "99", "110", "10", "1050"],
            ["1767225600000", "95", "101", "94", "100", "8", "780"],
        ]}}

    def get_funding_rate_history(self, **kwargs):
        assert kwargs == {"category": "linear", "symbol": "BTCUSDT", "limit": 200}
        return {"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingRateTimestamp": "1767229200000"},
        ]}}


def test_collects_mark_candles_funding_and_contract_rules(tmp_path):
    now = datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc)
    report = fetch_bybit_demo_futures_data(
        client=FakeFuturesClient(), symbols=("BTCUSDT",), interval="60",
        limit=3, now=now, output_dir=tmp_path / "data",
        report_path=tmp_path / "report.json", min_rows=1,
    )
    with (tmp_path / "data/bybit_demo_linear_BTCUSDT_60.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    # Settlement at 01:00 UTC is aligned to the 00:00-01:00 candle close.
    assert float(rows[0]["funding_rate"]) == pytest.approx(0.0001)
    assert rows[0]["funding_settlement_utc"] == "2026-01-01T01:00:00+00:00"
    assert float(rows[1]["funding_rate"]) == 0
    assert float(rows[0]["min_order_size"]) == pytest.approx(0.001)
    assert report["status"] == "FUTURES_DATA_RECEIVED"
    assert report["orders_submitted"] == 0
    assert report["paper_engine_integration"] is False


def test_rejects_unaligned_funding_timestamp(tmp_path):
    class UnalignedClient(FakeFuturesClient):
        def get_funding_rate_history(self, **kwargs):
            return {"retCode": 0, "result": {"list": [
                {"fundingRate": "0.0001", "fundingRateTimestamp": "1767230000000"},
            ]}}

    with pytest.raises(RuntimeError, match="do not align"):
        fetch_bybit_demo_futures_data(
            client=UnalignedClient(), symbols=("BTCUSDT",), limit=3,
            now=datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc),
            output_dir=tmp_path / "data", report_path=tmp_path / "report.json",
            min_rows=1,
        )


def test_rejects_missing_instrument_minimum(tmp_path):
    class InvalidInstrumentClient(FakeFuturesClient):
        def get_instruments_info(self, **kwargs):
            return {"retCode": 0, "result": {"list": [{
                "lotSizeFilter": {}, "priceFilter": {}, "leverageFilter": {},
            }]}}

    with pytest.raises(RuntimeError, match="minimum order quantity"):
        fetch_bybit_demo_futures_data(
            client=InvalidInstrumentClient(), symbols=("BTCUSDT",), limit=3,
            now=datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc),
            output_dir=tmp_path / "data", report_path=tmp_path / "report.json",
            min_rows=1,
        )
