import pytest
from quantlab.exchange.bybit_demo import _require_success, build_demo_session, check_demo_connection
class FakeClient:
    def get_wallet_balance(self, **kwargs):
        assert kwargs == {"accountType": "UNIFIED"}
        return {"retCode": 0, "result": {"list": [{"accountType": "UNIFIED"}]}}
    def get_positions(self, **kwargs):
        assert kwargs == {"category": "linear", "settleCoin": "USDT"}
        return {"retCode": 0, "result": {"list": [{"symbol": "BTCUSDT", "size": "0"}]}}
def test_demo_check_reads_account_without_submitting_orders(tmp_path, monkeypatch):
    monkeypatch.setattr("quantlab.exchange.bybit_demo.REPORT_PATH", tmp_path / "demo.json")
    report = check_demo_connection(FakeClient())
    assert report["environment"] == "DEMO" and report["authenticated"] is True
    assert report["orders_submitted"] == 0 and report["real_trading_enabled"] is False
    assert report["active_linear_positions"] == 0
def test_missing_credentials_fail_closed(monkeypatch):
    monkeypatch.delenv("BYBIT_DEMO_API_KEY", raising=False)
    monkeypatch.delenv("BYBIT_DEMO_API_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="Missing"):
        build_demo_session()
def test_api_errors_are_reported():
    with pytest.raises(RuntimeError, match="retCode=10003"):
        _require_success({"retCode": 10003, "retMsg": "invalid key"}, "wallet balance")
