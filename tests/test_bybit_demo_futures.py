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

    def get_mark_price_kline(self, **kwargs):
        assert kwargs["category"] == "linear"
        assert kwargs["symbol"] == "BTCUSDT"
        assert kwargs["interval"] == "60"
        assert kwargs["limit"] == 1000
        assert "start" in kwargs and "end" in kwargs
        # The official mark-price endpoint returns OHLC only (no volume/turnover).
        return {"retCode": 0, "result": {"list": [
            ["1767232800000", "110", "112", "109", "111"],
            ["1767229200000", "100", "111", "99", "110"],
            ["1767225600000", "95", "101", "94", "100"],
        ]}}

    def get_funding_rate_history(self, **kwargs):
        assert kwargs["category"] == "linear"
        assert kwargs["symbol"] == "BTCUSDT"
        assert kwargs["limit"] == 200
        assert "startTime" in kwargs and "endTime" in kwargs
        return {"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingRateTimestamp": "1767229200000"},
        ]}}


def _collect(client, tmp_path, **kwargs):
    return fetch_bybit_demo_futures_data(
        client=client, symbols=("BTCUSDT",), interval="60",
        history_days=1, now=datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc),
        output_dir=tmp_path / "data", report_path=tmp_path / "report.json",
        min_rows=1, **kwargs,
    )


def test_collects_true_mark_candles_funding_and_contract_rules(tmp_path):
    report = _collect(FakeFuturesClient(), tmp_path)
    with (tmp_path / "data/bybit_demo_linear_BTCUSDT_60.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert float(rows[0]["volume"]) == 0
    assert float(rows[0]["turnover"]) == 0
    assert float(rows[0]["funding_rate"]) == pytest.approx(0.0001)
    assert rows[0]["funding_settlement_utc"] == "2026-01-01T01:00:00+00:00"
    assert float(rows[1]["funding_rate"]) == 0
    assert float(rows[0]["min_order_size"]) == pytest.approx(0.001)
    assert report["price_basis"] == "mark"
    assert report["environment"] == "MAINNET_PUBLIC_MARKET_DATA"
    assert report["market_data_endpoint"] == "api.bytick.com"
    assert report["history_days_requested"] == 1
    assert report["status"] == "FUTURES_DATA_RECEIVED"
    assert report["orders_submitted"] == 0
    assert report["paper_engine_integration"] is False


def test_paginates_mark_candles_and_funding_history(tmp_path):
    class PagingClient(FakeFuturesClient):
        def __init__(self):
            self.kline_calls = 0
            self.funding_calls = 0

        def get_mark_price_kline(self, **kwargs):
            self.kline_calls += 1
            if self.kline_calls == 1:
                rows = [
                    ["1767232800000", "110", "112", "109", "111"],
                    ["1767229200000", "100", "111", "99", "110"],
                ]
            else:
                rows = [["1767225600000", "95", "101", "94", "100"]]
            return {"retCode": 0, "result": {"list": rows}}

        def get_funding_rate_history(self, **kwargs):
            self.funding_calls += 1
            rows = (
                [{"fundingRate": "0.0001", "fundingRateTimestamp": "1767229200000"}]
                if self.funding_calls == 1 else []
            )
            return {"retCode": 0, "result": {"list": rows}}

    client = PagingClient()
    _collect(client, tmp_path, kline_page_limit=2, funding_page_limit=1)
    assert client.kline_calls == 2
    assert client.funding_calls == 2


def test_rejects_unaligned_funding_timestamp(tmp_path):
    class UnalignedClient(FakeFuturesClient):
        def get_funding_rate_history(self, **kwargs):
            return {"retCode": 0, "result": {"list": [
                {"fundingRate": "0.0001", "fundingRateTimestamp": "1767230000000"},
            ]}}

    with pytest.raises(RuntimeError, match="do not align"):
        _collect(UnalignedClient(), tmp_path)


def test_rejects_missing_instrument_minimum(tmp_path):
    class InvalidInstrumentClient(FakeFuturesClient):
        def get_instruments_info(self, **kwargs):
            return {"retCode": 0, "result": {"list": [{
                "lotSizeFilter": {}, "priceFilter": {}, "leverageFilter": {},
            }]}}

    with pytest.raises(RuntimeError, match="minimum order quantity"):
        _collect(InvalidInstrumentClient(), tmp_path)
