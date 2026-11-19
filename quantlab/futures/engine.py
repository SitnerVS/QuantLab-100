from copy import deepcopy
import math

import pandas as pd


def new_futures_account(initial_cash):
    initial_cash = float(initial_cash)
    if initial_cash < 0:
        raise ValueError("initial_cash cannot be negative")
    return {
        "initial_cash": initial_cash,
        "wallet": initial_cash,
        "position": None,
        "realized_pnl": 0.0,
        "funding_paid": 0.0,
        "fees_paid": 0.0,
        "closed_trades": 0,
        "liquidations": 0,
        "rejected_min_size": 0,
        "rejected_min_notional": 0,
        "last_bar": None,
        "ledger": [],
    }


def apply_isolated_futures_signal(
    account,
    signal,
    mark_price,
    funding_rate,
    timestamp,
    leverage=2.0,
    max_margin_fraction=0.25,
    fee_rate=0.0006,
    slippage_rate=0.0005,
    spread_rate=0.0,
    maintenance_margin_rate=0.05,
    liquidation_fee_rate=0.025,
    min_order_size=0.0,
    min_notional_usd=0.0,
):
    """Apply one completed-bar signal to a persistent isolated-margin account.

    Positive funding rates are paid by longs; negative rates are received.
    Funding is applied before the signal transition at each settlement bar.
    Mark and fill references use the completed candle close, not tick data.
    """
    account = deepcopy(account)
    if account.get("last_bar") == timestamp:
        return account, {"timestamp": timestamp, "status": "duplicate_bar"}

    mark_price = float(mark_price)
    funding_rate = 0.0 if funding_rate is None or pd.isna(funding_rate) else float(funding_rate)
    if not math.isfinite(mark_price) or mark_price <= 0:
        raise ValueError("mark_price must be finite and positive")
    if not math.isfinite(funding_rate):
        raise ValueError("funding_rate must be finite")
    if float(leverage) < 1:
        raise ValueError("leverage must be >= 1")
    if not 0 < float(max_margin_fraction) <= 1:
        raise ValueError("max_margin_fraction must be in (0, 1]")
    if not math.isfinite(float(min_order_size)) or float(min_order_size) < 0:
        raise ValueError("min_order_size must be finite and non-negative")
    if not math.isfinite(float(min_notional_usd)) or float(min_notional_usd) < 0:
        raise ValueError("min_notional_usd must be finite and non-negative")
    cost_rates = [fee_rate, slippage_rate, spread_rate, maintenance_margin_rate, liquidation_fee_rate]
    if any(not math.isfinite(float(rate)) or float(rate) < 0 for rate in cost_rates):
        raise ValueError("cost and margin rates must be finite and non-negative")

    signal = int(bool(signal))
    wallet = float(account["wallet"])
    position = account.get("position")
    event = {
        "timestamp": timestamp,
        "signal": signal,
        "status": "hold",
        "funding_payment": 0.0,
        "fee": 0.0,
        "liquidated": False,
    }
    impact = float(slippage_rate) + float(spread_rate) / 2.0
    funding_payment = 0.0
    liquidated = False

    if position is not None:
        current_notional = float(position["quantity"]) * mark_price
        funding_payment = current_notional * funding_rate
        position["margin_balance"] = float(position["margin_balance"]) - funding_payment
        position["funding_paid"] = float(position.get("funding_paid", 0.0)) + funding_payment
        account["funding_paid"] = float(account["funding_paid"]) + funding_payment
        unrealized = float(position["quantity"]) * (mark_price - float(position["entry_price"]))
        maintenance = current_notional * float(maintenance_margin_rate)
        isolated_equity = float(position["margin_balance"]) + unrealized

        if isolated_equity <= maintenance:
            liquidation_fee = min(
                max(0.0, isolated_equity),
                current_notional * float(liquidation_fee_rate),
            )
            recovered = max(0.0, isolated_equity - liquidation_fee)
            wallet += recovered
            account["realized_pnl"] = float(account["realized_pnl"]) + recovered - float(position["margin_allocated"])
            account["fees_paid"] = float(account["fees_paid"]) + liquidation_fee
            position = None
            account["liquidations"] = int(account["liquidations"]) + 1
            liquidated = True
            event["status"] = "liquidation"
            event["fee"] += liquidation_fee

    if position is not None and signal == 0:
        fill = mark_price * (1.0 - impact)
        gross_pnl = float(position["quantity"]) * (fill - float(position["entry_price"]))
        close_notional = float(position["quantity"]) * fill
        close_fee = close_notional * float(fee_rate)
        released = max(0.0, float(position["margin_balance"]) + gross_pnl - close_fee)
        wallet += released
        account["realized_pnl"] = float(account["realized_pnl"]) + released - float(position["margin_allocated"])
        account["fees_paid"] = float(account["fees_paid"]) + close_fee
        account["closed_trades"] = int(account["closed_trades"]) + 1
        event.update({"status": "close", "fill_price": fill, "quantity": float(position["quantity"])})
        event["fee"] += close_fee
        position = None

    elif position is None and signal == 1 and not liquidated and wallet > 0:
        margin_allocated = wallet * float(max_margin_fraction)
        fill = mark_price * (1.0 + impact)
        notional = margin_allocated * float(leverage)
        quantity = notional / fill
        if quantity < float(min_order_size) or notional < float(min_notional_usd):
            if quantity < float(min_order_size):
                account["rejected_min_size"] = int(account.get("rejected_min_size", 0)) + 1
                rejection_status = "below_minimum_size"
            else:
                account["rejected_min_notional"] = int(account.get("rejected_min_notional", 0)) + 1
                rejection_status = "below_minimum_notional"
            event.update({
                "status": rejection_status,
                "attempted_quantity": quantity,
                "minimum_quantity": float(min_order_size),
                "attempted_notional_usd": notional,
                "minimum_notional_usd": float(min_notional_usd),
            })
        else:
            open_fee = notional * float(fee_rate)
            wallet -= margin_allocated
            position = {
                "quantity": quantity,
                "entry_price": fill,
                "margin_allocated": margin_allocated,
                "margin_balance": margin_allocated - open_fee,
                "funding_paid": 0.0,
            }
            account["fees_paid"] = float(account["fees_paid"]) + open_fee
            event.update({"status": "open", "fill_price": fill, "quantity": quantity})
            event["fee"] += open_fee

    unrealized = (
        float(position["quantity"]) * (mark_price - float(position["entry_price"]))
        if position is not None else 0.0
    )
    margin_balance = float(position["margin_balance"]) if position is not None else 0.0
    equity = wallet + margin_balance + unrealized
    account["wallet"] = wallet
    account["position"] = position
    account["last_bar"] = timestamp
    event.update({
        "funding_payment": funding_payment,
        "liquidated": liquidated,
        "wallet": wallet,
        "margin_balance": margin_balance,
        "unrealized_pnl": unrealized,
        "equity": equity,
        "realized_pnl": float(account["realized_pnl"]),
    })
    account["ledger"].append(event)
    if len(account["ledger"]) > 2000:
        account["ledger"] = account["ledger"][-2000:]
    return account, event


def simulate_isolated_long(
    frame,
    signal_col="signal",
    funding_col="funding_rate",
    initial_cash=100.0,
    leverage=2.0,
    max_margin_fraction=0.25,
    fee_rate=0.0006,
    slippage_rate=0.0005,
    spread_rate=0.0,
    maintenance_margin_rate=0.05,
    liquidation_fee_rate=0.025,
):
    """Run the persistent isolated-margin step engine across historical bars."""
    required = {"close", signal_col, funding_col}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing futures columns: {sorted(required - set(frame.columns))}")
    if frame.empty:
        raise ValueError("futures frame cannot be empty")

    data = frame.copy().reset_index(drop=True)
    signals = data[signal_col].fillna(0).shift(1).fillna(0).clip(0, 1)
    account = new_futures_account(initial_cash)
    rows = []

    for index, row in data.iterrows():
        time_col = next((col for col in ("timestamp", "datetime", "date") if col in data.columns), None)
        timestamp = str(row[time_col]) if time_col else str(index)
        account, event = apply_isolated_futures_signal(
            account,
            signals.iloc[index],
            row["close"],
            row[funding_col],
            timestamp,
            leverage=leverage,
            max_margin_fraction=max_margin_fraction,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            spread_rate=spread_rate,
            maintenance_margin_rate=maintenance_margin_rate,
            liquidation_fee_rate=liquidation_fee_rate,
            min_order_size=float(row.get("min_order_size", 0.0)),
            min_notional_usd=float(row.get("min_notional_usd", 0.0)),
        )
        rows.append({
            "position": int(account["position"] is not None),
            "wallet": float(account["wallet"]),
            "margin_balance": (
                float(account["position"]["margin_balance"])
                if account["position"] is not None else 0.0
            ),
            "unrealized_pnl": float(event.get("unrealized_pnl", 0.0)),
            "funding_payment": float(event.get("funding_payment", 0.0)),
            "equity": float(event.get("equity", account["wallet"])),
            "event": event.get("status", "hold"),
            "liquidated": bool(event.get("liquidated", False)),
        })

    result = pd.concat([data, pd.DataFrame(rows)], axis=1)
    result["drawdown"] = result["equity"] / result["equity"].cummax() - 1.0
    metrics = {
        "total_return_pct": float((result["equity"].iloc[-1] / float(initial_cash) - 1.0) * 100.0),
        "max_drawdown_pct": float(result["drawdown"].min() * 100.0),
        "closed_trades": int(account["closed_trades"]),
        "liquidations": int(account["liquidations"]),
        "rejected_min_size": int(account.get("rejected_min_size", 0)),
        "rejected_min_notional": int(account.get("rejected_min_notional", 0)),
        "funding_paid_quote": float(account["funding_paid"]),
        "fees_quote": float(account["fees_paid"]),
        "observations": int(len(result)),
    }
    return result, metrics
