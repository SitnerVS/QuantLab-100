import pandas as pd
import pytest

from quantlab.exchange.bybit_market_data import fetch_demo_market_data


class FakeMarketClient:
    def get_kline(self, **kwargs):
        assert kwargs == {"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": 3}
        # Bybit returns newest first; the final candle is still forming at the fixed test time.
        return {"retCode": 0, "result": {"list": [
            ["1767232800000", "110", "112", "109", "111", "12", "1332"],
            ["1767229200000", "100", "111", "99", "110", "10", "1050"],
            ["1767225600000", "95", "101", "94", "100", "8", "780"],
        ]}}


def test_downloads_only_completed_valid_candles_and_writes_report(tmp_path):
    now = pd.Timestamp("2026-01-01T02:30:00Z").to_pydatetime()
    report = fetch_demo_market_data(
        client=FakeMarketClient(), symbols=("BTCUSDT",), interval="60", limit=3,
        now=now, raw_dir=tmp_path / "raw", report_path=tmp_path / "report.json",
    )
    frame = pd.read_csv(tmp_path / "raw/bybit_demo_linear_BTCUSDT_60.csv")
    assert len(frame) == 2
    assert frame["close"].tolist() == [100, 110]
    assert report["status"] == "DATA_RECEIVED"
    assert report["orders_submitted"] == 0
    assert report["real_trading_enabled"] is False
    assert (tmp_path / "report.json").exists()


def test_rejects_unsupported_interval():
    with pytest.raises(ValueError, match="Unsupported"):
        fetch_demo_market_data(client=FakeMarketClient(), interval="7")


def test_api_error_fails_closed(tmp_path):
    class BrokenClient:
        def get_kline(self, **kwargs):
            return {"retCode": 10003, "retMsg": "invalid key"}

    with pytest.raises(RuntimeError, match="retCode=10003"):
        fetch_demo_market_data(
            client=BrokenClient(), symbols=("BTCUSDT",),
            raw_dir=tmp_path / "raw", report_path=tmp_path / "report.json",
        )
