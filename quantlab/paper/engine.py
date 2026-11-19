from datetime import datetime, timezone


def apply_paper_signal(
    account,
    signal,
    close,
    timestamp,
    fee_rate=0.001,
    slippage_rate=0.0005,
    spread_rate=0.0,
    max_position_fraction=1.0,
    min_order_size=0.0,
    min_notional=0.0,
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
    max_position_fraction = float(max_position_fraction)
    if not 0 < max_position_fraction <= 1:
        raise ValueError("max_position_fraction must be in (0, 1]")

    account = dict(account)
    account.setdefault("cash", 0.0)
    account.setdefault("quantity", 0.0)
    account.setdefault("realized_pnl", 0.0)
    account.setdefault("trade_count", 0)
    account.setdefault("rejected_min_size", 0)
    account.setdefault("position_entry_price", None)
    account.setdefault("position_entry_cost", None)
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
        allocated_cash = cash * max_position_fraction
        quantity = allocated_cash / (fill * (1.0 + fee))
        notional = quantity * fill
        if quantity < float(min_order_size) or notional < float(min_notional):
            account["rejected_min_size"] = int(account.get("rejected_min_size", 0)) + 1
            event.update({
                "status": "below_minimum_size",
                "attempted_quantity": quantity,
                "minimum_quantity": float(min_order_size),
                "attempted_notional": notional,
                "minimum_notional": float(min_notional),
            })
        else:
            commission = notional * fee
            cash -= notional + commission
            account["cash"] = max(0.0, cash)
            account["quantity"] = quantity
            account["position_entry_price"] = fill
            account["position_entry_cost"] = notional + commission
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
        cost_basis = float(account["position_entry_cost"] or (quantity * entry))
        realized = proceeds - commission - cost_basis
        account["cash"] = cash + proceeds - commission
        account["quantity"] = 0.0
        account["position_entry_price"] = None
        account["position_entry_cost"] = None
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
        "position_entry_cost": None,
        "realized_pnl": 0.0,
        "trade_count": 0,
        "last_bar": None,
        "ledger": [],
    }


def rub_to_usd(amount_rub, rub_per_usd):
    """Convert RUB to USD using a RUB-per-USD reference rate."""
    amount_rub = float(amount_rub)
    rub_per_usd = float(rub_per_usd)
    if amount_rub < 0 or rub_per_usd <= 0:
        raise ValueError("amount_rub must be non-negative and rub_per_usd positive")
    return amount_rub / rub_per_usd
