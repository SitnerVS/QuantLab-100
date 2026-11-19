"""Fail-closed Bybit Demo Trading connectivity checks."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
REPORT_PATH = Path("reports/bybit_demo_connection.json")
def build_demo_session(api_key: str | None = None, api_secret: str | None = None):
    key = api_key or os.getenv("BYBIT_DEMO_API_KEY")
    secret = api_secret or os.getenv("BYBIT_DEMO_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Missing BYBIT_DEMO_API_KEY or BYBIT_DEMO_API_SECRET GitHub Actions secret.")
    from pybit.unified_trading import HTTP
    return HTTP(testnet=False, demo=True, api_key=key, api_secret=secret)
def _require_success(response: dict[str, Any], endpoint: str) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError(f"Bybit {endpoint}: unexpected response type.")
    code = response.get("retCode")
    if code != 0:
        message = str(response.get("retMsg", "unknown API error"))[:200]
        raise RuntimeError(f"Bybit Demo {endpoint} failed (retCode={code}): {message}")
    result = response.get("result")
    return result if isinstance(result, dict) else {}
def check_demo_connection(client=None) -> dict[str, Any]:
    """Authenticate against Demo, read wallet and linear positions; place no orders."""
    session = client or build_demo_session()
    wallet = _require_success(session.get_wallet_balance(accountType="UNIFIED"), "wallet balance")
    positions = _require_success(session.get_positions(category="linear", settleCoin="USDT"), "positions")
    wallet_accounts, position_rows = wallet.get("list", []), positions.get("list", [])
    active_positions = [row for row in position_rows if float(row.get("size", 0) or 0) != 0]
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "exchange": "Bybit",
        "environment": "DEMO", "authenticated": True, "wallet_account_count": len(wallet_accounts),
        "linear_position_rows": len(position_rows), "active_linear_positions": len(active_positions),
        "orders_submitted": 0, "real_trading_enabled": False, "status": "CONNECTED"}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
