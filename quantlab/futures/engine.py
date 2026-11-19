import pandas as pd


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
    maintenance_margin_rate=0.005,
    liquidation_fee_rate=0.005,
):
    """Isolated-margin long/flat simulator requiring observed per-bar funding.

    The close is used as a mark/execution proxy. Positive funding rates are
    paid by longs; negative rates are received. A missing funding series is a
    hard error: this engine never silently invents funding costs.
    """
    required = {"close", signal_col, funding_col}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing futures columns: {sorted(required - set(frame.columns))}")
    if frame.empty:
        raise ValueError("futures frame cannot be empty")
    if initial_cash <= 0 or leverage < 1:
        raise ValueError("initial_cash must be positive and leverage >= 1")
    if not 0 < max_margin_fraction <= 1:
        raise ValueError("max_margin_fraction must be in (0, 1]")
    rates = [fee_rate, slippage_rate, spread_rate, maintenance_margin_rate, liquidation_fee_rate]
    if any(float(value) < 0 for value in rates):
        raise ValueError("fees, slippage, spread and margin rates cannot be negative")

    data = frame.copy().reset_index(drop=True)
    signals = data[signal_col].fillna(0).shift(1).fillna(0).clip(0, 1)
    wallet = float(initial_cash)
    position = None
    rows = []
    total_funding = 0.0
    total_fees = 0.0
    realized_pnl = 0.0
    closed_trades = 0
    liquidations = 0
    impact = float(slippage_rate) + float(spread_rate) / 2.0

    for index, row in data.iterrows():
        mark = float(row["close"])
        if mark <= 0:
            raise ValueError("close/mark prices must be positive")
        signal = int(bool(signals.iloc[index]))
        funding_value = row[funding_col]
        funding_rate = 0.0 if pd.isna(funding_value) else float(funding_value)
        event = "hold"
        funding_payment = 0.0
        liquidated = False

        if position is not None:
            current_notional = position["quantity"] * mark
            funding_payment = current_notional * funding_rate
            position["margin_balance"] -= funding_payment
            position["funding_paid"] += funding_payment
            total_funding += funding_payment
            unrealized = position["quantity"] * (mark - position["entry_price"])
            maintenance = current_notional * float(maintenance_margin_rate)
            isolated_equity = position["margin_balance"] + unrealized

            if isolated_equity <= maintenance:
                liquidation_fee = min(
                    max(0.0, isolated_equity),
                    current_notional * float(liquidation_fee_rate),
                )
                recovered = max(0.0, isolated_equity - liquidation_fee)
                wallet += recovered
                realized_pnl += recovered - position["margin_allocated"]
                total_fees += liquidation_fee
                position = None
                liquidations += 1
                liquidated = True
                event = "liquidation"

        if position is not None and signal == 0:
            fill = mark * (1.0 - impact)
            proceeds_pnl = position["quantity"] * (fill - position["entry_price"])
            close_notional = position["quantity"] * fill
            close_fee = close_notional * float(fee_rate)
            released = max(0.0, position["margin_balance"] + proceeds_pnl - close_fee)
            wallet += released
            realized_pnl += released - position["margin_allocated"]
            total_fees += close_fee
            position = None
            closed_trades += 1
            event = "close"

        elif position is None and signal == 1 and not liquidated and wallet > 0:
            margin_allocated = wallet * float(max_margin_fraction)
            fill = mark * (1.0 + impact)
            notional = margin_allocated * float(leverage)
            quantity = notional / fill
            open_fee = notional * float(fee_rate)
            wallet -= margin_allocated
            position = {
                "quantity": quantity,
                "entry_price": fill,
                "margin_allocated": margin_allocated,
                "margin_balance": margin_allocated - open_fee,
                "funding_paid": 0.0,
            }
            total_fees += open_fee
            event = "open"

        unrealized = (
            position["quantity"] * (mark - position["entry_price"])
            if position is not None else 0.0
        )
        margin_balance = position["margin_balance"] if position is not None else 0.0
        equity = wallet + margin_balance + unrealized
        rows.append({
            "position": int(position is not None),
            "wallet": wallet,
            "margin_balance": margin_balance,
            "unrealized_pnl": unrealized,
            "funding_payment": funding_payment,
            "equity": equity,
            "event": event,
            "liquidated": liquidated,
        })

    result = pd.concat([data, pd.DataFrame(rows)], axis=1)
    result["drawdown"] = result["equity"] / result["equity"].cummax() - 1.0
    metrics = {
        "total_return_pct": float((result["equity"].iloc[-1] / initial_cash - 1.0) * 100.0),
        "max_drawdown_pct": float(result["drawdown"].min() * 100.0),
        "closed_trades": int(closed_trades),
        "liquidations": int(liquidations),
        "funding_paid_quote": float(total_funding),
        "fees_quote": float(total_fees),
        "observations": int(len(result)),
    }
    return result, metrics
