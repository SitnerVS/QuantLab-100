from datetime import datetime, timezone


def apply_paper_signal(
    account,
    signal,
    close,
    timestamp,
    fee_rate=0.001,
    slippage_rate=0.0005,
    spread_rate=0.0,
):
    """Apply one completed-bar long/flat signal to a cash-only virtual account.

    The close is used as a proxy execution reference. Fees, half-spread and
    slippage are applied conservatively. This is not an order-book fill model.
    """
    signal = int(bool(signal))
    close = float(close)
    if close <= 0:
        raise ValueError("close must be positive")
    if min(float(fee_rate), float(slippage_rate), float(spread_rate)) < 0:
        raise ValueError("cost rates cannot be negative")

    account = dict(account)
    account.setdefault("cash", 0.0)
    account.setdefault("quantity", 0.0)
    account.setdefault("realized_pnl", 0.0)
    account.setdefault("trade_count", 0)
    account.setdefault("position_entry_price", None)
    account.setdefault("last_bar", None)
    account.setdefault("ledger", [])

    if account["last_bar"] == timestamp:
        return account, {"status": "duplicate_bar"}

    cash = float(account["cash"])
    quantity = float(account["quantity"])
    fee = float(fee_rate)
    impact = float(slippage_rate) + float(spread_rate) / 2.0
    event = {"timestamp": timestamp, "signal": signal, "status": "hold"}

    if signal and quantity <= 0 and cash > 0:
        fill = close * (1.0 + impact)
        quantity = cash / (fill * (1.0 + fee))
        notional = quantity * fill
        commission = notional * fee
        cash -= notional + commission
        account["cash"] = max(0.0, cash)
        account["quantity"] = quantity
        account["position_entry_price"] = fill
        event.update({
            "status": "buy",
            "fill_price": fill,
            "quantity": quantity,
            "fee": commission,
        })
        account["trade_count"] += 1

    elif not signal and quantity > 0:
        fill = close * (1.0 - impact)
        proceeds = quantity * fill
        commission = proceeds * fee
        entry = float(account["position_entry_price"] or fill)
        cost_basis = quantity * entry
        realized = proceeds - commission - cost_basis
        account["cash"] = cash + proceeds - commission
        account["quantity"] = 0.0
        account["position_entry_price"] = None
        account["realized_pnl"] = float(account["realized_pnl"]) + realized
        event.update({
            "status": "sell",
            "fill_price": fill,
            "quantity": quantity,
            "fee": commission,
            "realized_pnl": realized,
        })
        account["trade_count"] += 1

    account["last_bar"] = timestamp
    equity = float(account["cash"]) + float(account["quantity"]) * close
    event["cash"] = float(account["cash"])
    event["equity"] = equity
    event["unrealized_pnl"] = (
        float(account["quantity"]) * (close - float(account["position_entry_price"]))
        if account["quantity"] > 0 and account["position_entry_price"] is not None
        else 0.0
    )
    account["ledger"].append(event)
    return account, event


def new_account(initial_cash):
    initial_cash = float(initial_cash)
    if initial_cash < 0:
        raise ValueError("initial_cash cannot be negative")
    return {
        "initial_cash": initial_cash,
        "cash": initial_cash,
        "quantity": 0.0,
        "position_entry_price": None,
        "realized_pnl": 0.0,
        "trade_count": 0,
        "last_bar": None,
        "ledger": [],
    }
