"""Research-only isolated-margin long/short futures simulator."""
from __future__ import annotations

from copy import deepcopy
import math

import pandas as pd


def new_long_short_account(initial_cash):
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
        "stop_losses": 0,
        "peak_equity": initial_cash,
        "halted": False,
        "rejected_min_size": 0,
        "rejected_min_notional": 0,
        "last_bar": None,
        "ledger": [],
    }


def apply_long_short_signal(
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
    stop_loss_pct=None,
    max_drawdown_pct=None,
    open_price=None,
    high_price=None,
    low_price=None,
):
    """Apply a -1/0/+1 signal with signed funding and isolated margin."""
    account = deepcopy(account)
    signal = int(signal)
    if signal not in (-1, 0, 1):
        raise ValueError("signal must be -1, 0 or 1")
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
    for name, value in (
        ("min_order_size", min_order_size),
        ("min_notional_usd", min_notional_usd),
        ("fee_rate", fee_rate),
        ("slippage_rate", slippage_rate),
        ("spread_rate", spread_rate),
        ("maintenance_margin_rate", maintenance_margin_rate),
        ("liquidation_fee_rate", liquidation_fee_rate),
    ):
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"{name} must be finite and non-negative")

    for name, value in (("stop_loss_pct", stop_loss_pct), ("max_drawdown_pct", max_drawdown_pct)):
        if value is not None and (
            not math.isfinite(float(value)) or not 0 < float(value) < 1
        ):
            raise ValueError(f"{name} must be in (0, 1) when provided")

    if account.get("last_bar") == timestamp:
        return account, {"timestamp": timestamp, "status": "duplicate_bar"}

    wallet = float(account["wallet"])
    position = account.get("position")
    event = {
        "timestamp": timestamp,
        "signal": signal,
        "status": "hold",
        "funding_payment": 0.0,
        "fee": 0.0,
        "liquidated": False,
        "closed_direction": 0,
        "opened_direction": 0,
        "stop_loss_triggered": False,
        "drawdown_kill_switch": False,
    }
    impact = float(slippage_rate) + float(spread_rate) / 2.0
    open_price = mark_price if open_price is None else float(open_price)
    high_price = mark_price if high_price is None else float(high_price)
    low_price = mark_price if low_price is None else float(low_price)
    if any(not math.isfinite(value) or value <= 0 for value in (open_price, high_price, low_price)):
        raise ValueError("OHLC prices must be finite and positive")
    if high_price < low_price:
        raise ValueError("high_price cannot be below low_price")
    risk_exit = False
    funding_payment = 0.0
    liquidated = False

    if position is not None:
        direction = int(position["direction"])
        notional = float(position["quantity"]) * mark_price
        funding_payment = direction * notional * funding_rate
        position["margin_balance"] = float(position["margin_balance"]) - funding_payment
        position["funding_paid"] = float(position.get("funding_paid", 0.0)) + funding_payment
        account["funding_paid"] = float(account["funding_paid"]) + funding_payment
        unrealized = direction * float(position["quantity"]) * (
            mark_price - float(position["entry_price"])
        )
        maintenance = notional * float(maintenance_margin_rate)
        isolated_equity = float(position["margin_balance"]) + unrealized
        if isolated_equity <= maintenance:
            liquidation_fee = min(
                max(0.0, isolated_equity),
                notional * float(liquidation_fee_rate),
            )
            recovered = max(0.0, isolated_equity - liquidation_fee)
            wallet += recovered
            account["realized_pnl"] += recovered - float(position["margin_allocated"])
            account["fees_paid"] += liquidation_fee
            position = None
            account["liquidations"] += 1
            liquidated = True
            event["status"] = "liquidation"
            event["fee"] += liquidation_fee
            event["closed_direction"] = direction

    if position is not None and stop_loss_pct is not None:
        direction = int(position["direction"])
        stop_price = float(position["entry_price"]) * (
            1.0 - direction * float(stop_loss_pct)
        )
        stop_hit = (
            low_price <= stop_price if direction == 1
            else high_price >= stop_price
        )
        if stop_hit:
            # A gap through the stop fills at the bar open; otherwise at stop.
            raw_exit = (
                min(stop_price, open_price) if direction == 1
                else max(stop_price, open_price)
            )
            fill = raw_exit * (1.0 - impact * direction)
            gross_pnl = direction * float(position["quantity"]) * (
                fill - float(position["entry_price"])
            )
            close_notional = float(position["quantity"]) * fill
            close_fee = close_notional * float(fee_rate)
            released = max(
                0.0,
                float(position["margin_balance"]) + gross_pnl - close_fee,
            )
            wallet += released
            account["realized_pnl"] += released - float(position["margin_allocated"])
            account["fees_paid"] += close_fee
            account["closed_trades"] += 1
            account["stop_losses"] = int(account.get("stop_losses", 0)) + 1
            event["fee"] += close_fee
            event.update({
                "status": "stop_loss",
                "close_price": fill,
                "closed_direction": direction,
                "stop_loss_triggered": True,
            })
            position = None
            risk_exit = True

    # Account-level kill switch uses equity marked at the completed bar close.
    peak_equity = float(account.get("peak_equity", account["initial_cash"]))
    # Evaluate account drawdown at the adverse intrabar extreme, not only
    # at candle close, so a wick cannot breach the risk limit unnoticed.
    risk_mark_price = mark_price
    if position is not None:
        risk_mark_price = (
            low_price if int(position["direction"]) == 1 else high_price
        )
    current_unrealized = (
        int(position["direction"]) * float(position["quantity"])
        * (risk_mark_price - float(position["entry_price"]))
        if position is not None else 0.0
    )
    current_margin = float(position["margin_balance"]) if position is not None else 0.0
    current_equity = wallet + current_margin + current_unrealized
    if (
        max_drawdown_pct is not None
        and not account.get("halted", False)
        and current_equity <= peak_equity * (1.0 - float(max_drawdown_pct))
    ):
        if position is not None:
            direction = int(position["direction"])
            fill = risk_mark_price * (1.0 - impact * direction)
            gross_pnl = direction * float(position["quantity"]) * (
                fill - float(position["entry_price"])
            )
            close_notional = float(position["quantity"]) * fill
            close_fee = close_notional * float(fee_rate)
            released = max(
                0.0,
                float(position["margin_balance"]) + gross_pnl - close_fee,
            )
            wallet += released
            account["realized_pnl"] += released - float(position["margin_allocated"])
            account["fees_paid"] += close_fee
            account["closed_trades"] += 1
            event["fee"] += close_fee
            event["closed_direction"] = direction
            event["close_price"] = fill
            position = None
        account["halted"] = True
        event["status"] = "max_drawdown_kill_switch"
        event["drawdown_kill_switch"] = True
        risk_exit = True

    if position is not None and signal != int(position["direction"]):
        direction = int(position["direction"])
        fill = mark_price * (1.0 - impact * direction)
        gross_pnl = direction * float(position["quantity"]) * (
            fill - float(position["entry_price"])
        )
        close_notional = float(position["quantity"]) * fill
        close_fee = close_notional * float(fee_rate)
        released = max(
            0.0,
            float(position["margin_balance"]) + gross_pnl - close_fee,
        )
        wallet += released
        account["realized_pnl"] += released - float(position["margin_allocated"])
        account["fees_paid"] += close_fee
        account["closed_trades"] += 1
        event["fee"] += close_fee
        event["closed_direction"] = direction
        event["status"] = "close" if signal == 0 else "reverse"
        position = None

    if (
        position is None and signal != 0 and not liquidated
        and not risk_exit and not account.get("halted", False) and wallet > 0
    ):
        margin_allocated = wallet * float(max_margin_fraction)
        fill = mark_price * (1.0 + impact * signal)
        notional = margin_allocated * float(leverage)
        quantity = notional / fill
        if quantity < float(min_order_size) or notional < float(min_notional_usd):
            if quantity < float(min_order_size):
                account["rejected_min_size"] += 1
                event["status"] = "below_minimum_size"
            else:
                account["rejected_min_notional"] += 1
                event["status"] = "below_minimum_notional"
            event.update({
                "attempted_quantity": quantity,
                "minimum_quantity": float(min_order_size),
                "attempted_notional_usd": notional,
                "minimum_notional_usd": float(min_notional_usd),
            })
        else:
            open_fee = notional * float(fee_rate)
            wallet -= margin_allocated
            position = {
                "direction": signal,
                "quantity": quantity,
                "entry_price": fill,
                "margin_allocated": margin_allocated,
                "margin_balance": margin_allocated - open_fee,
                "funding_paid": 0.0,
            }
            account["fees_paid"] += open_fee
            event["fee"] += open_fee
            event["opened_direction"] = signal
            if event["status"] != "reverse":
                event["status"] = "open"

    unrealized = (
        int(position["direction"]) * float(position["quantity"])
        * (mark_price - float(position["entry_price"]))
        if position is not None else 0.0
    )
    margin_balance = float(position["margin_balance"]) if position is not None else 0.0
    equity = wallet + margin_balance + unrealized
    account["wallet"] = wallet
    account["position"] = position
    account["last_bar"] = timestamp
    equity_peak = max(float(account.get("peak_equity", account["initial_cash"])), equity)
    account["peak_equity"] = equity_peak
    drawdown = equity / equity_peak - 1.0 if equity_peak > 0 else 0.0
    event.update({
        "direction": int(position["direction"]) if position is not None else 0,
        "funding_payment": funding_payment,
        "liquidated": liquidated,
        "wallet": wallet,
        "margin_balance": margin_balance,
        "unrealized_pnl": unrealized,
        "equity": equity,
        "realized_pnl": float(account["realized_pnl"]),
        "drawdown": drawdown,
        "halted": bool(account.get("halted", False)),
    })
    account["ledger"].append(event)
    if len(account["ledger"]) > 2000:
        account["ledger"] = account["ledger"][-2000:]
    return account, event


def simulate_isolated_long_short(
    frame,
    signal_col="direction_signal",
    funding_col="funding_rate",
    initial_cash=100.0,
    leverage=2.0,
    max_margin_fraction=0.25,
    fee_rate=0.0006,
    slippage_rate=0.0005,
    spread_rate=0.0,
    maintenance_margin_rate=0.05,
    liquidation_fee_rate=0.025,
    stop_loss_pct=None,
    max_drawdown_pct=None,
):
    required = {"close", signal_col, funding_col}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing futures columns: {sorted(required - set(frame.columns))}")
    if frame.empty:
        raise ValueError("futures frame cannot be empty")

    data = frame.copy().reset_index(drop=True)
    signals = data[signal_col].fillna(0).astype(int).shift(1).fillna(0).clip(-1, 1)
    account = new_long_short_account(initial_cash)
    rows = []
    for index, row in data.iterrows():
        # No full ledger is needed for a one-shot historical simulation.
        account["ledger"] = []
        time_col = next((col for col in ("timestamp", "datetime", "date") if col in data.columns), None)
        timestamp = str(row[time_col]) if time_col else str(index)
        account, event = apply_long_short_signal(
            account,
            int(signals.iloc[index]),
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
            stop_loss_pct=stop_loss_pct,
            max_drawdown_pct=max_drawdown_pct,
            open_price=row.get("open", row["close"]),
            high_price=row.get("high", row["close"]),
            low_price=row.get("low", row["close"]),
        )
        rows.append({
            "position": int(account["position"]["direction"]) if account["position"] else 0,
            "wallet": float(account["wallet"]),
            "margin_balance": (
                float(account["position"]["margin_balance"])
                if account["position"] else 0.0
            ),
            "unrealized_pnl": float(event.get("unrealized_pnl", 0.0)),
            "funding_payment": float(event.get("funding_payment", 0.0)),
            "equity": float(event.get("equity", account["wallet"])),
            "event": event.get("status", "hold"),
            "liquidated": bool(event.get("liquidated", False)),
            "stop_loss_triggered": bool(event.get("stop_loss_triggered", False)),
            "drawdown_kill_switch": bool(event.get("drawdown_kill_switch", False)),
            "halted": bool(event.get("halted", False)),
            "drawdown": float(event.get("drawdown", 0.0)),
        })

    result = pd.concat([data, pd.DataFrame(rows)], axis=1)
    result["drawdown"] = result["equity"] / result["equity"].cummax() - 1.0
    metrics = {
        "total_return_pct": float((result["equity"].iloc[-1] / float(initial_cash) - 1.0) * 100.0),
        "max_drawdown_pct": float(result["drawdown"].min() * 100.0),
        "closed_trades": int(account["closed_trades"]),
        "liquidations": int(account["liquidations"]),
        "stop_losses": int(account.get("stop_losses", 0)),
        "drawdown_kill_switch": bool(account.get("halted", False)),
        "rejected_min_size": int(account["rejected_min_size"]),
        "rejected_min_notional": int(account["rejected_min_notional"]),
        "funding_paid_quote": float(account["funding_paid"]),
        "fees_quote": float(account["fees_paid"]),
        "observations": int(len(result)),
    }
    return result, metrics
