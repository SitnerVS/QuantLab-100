"""Fail-closed position sizing and pre-trade risk checks.

This module is deliberately not wired to any exchange order endpoint.
"""
from __future__ import annotations

import math


def _finite_positive(name: str, value: float, *, allow_zero: bool = False) -> float:
    value = float(value)
    valid = math.isfinite(value) and (value >= 0 if allow_zero else value > 0)
    if not valid:
        qualifier = "finite and non-negative" if allow_zero else "finite and positive"
        raise ValueError(f"{name} must be {qualifier}")
    return value


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    *,
    side: str = "long",
    risk_fraction: float = 0.0025,
    max_notional_fraction: float = 1.0,
    max_leverage: float = 1.0,
    qty_step: float = 0.0,
    min_quantity: float = 0.0,
    min_notional: float = 0.0,
) -> dict:
    """Size a position from stop risk, then cap notional and venue constraints.

    Quantity is rounded down to the venue step. If the venue minimum cannot be
    met within the risk/notional budget, the result is rejected rather than
    silently increasing risk.
    """
    equity = _finite_positive("equity", equity)
    entry = _finite_positive("entry_price", entry_price)
    stop = _finite_positive("stop_price", stop_price)
    if side not in {"long", "short"}:
        raise ValueError("side must be 'long' or 'short'")
    if (side == "long" and stop >= entry) or (side == "short" and stop <= entry):
        raise ValueError("stop_price must be below entry for long and above entry for short")
    risk_fraction = _finite_positive("risk_fraction", risk_fraction)
    max_notional_fraction = _finite_positive("max_notional_fraction", max_notional_fraction)
    max_leverage = _finite_positive("max_leverage", max_leverage)
    qty_step = _finite_positive("qty_step", qty_step, allow_zero=True)
    min_quantity = _finite_positive("min_quantity", min_quantity, allow_zero=True)
    min_notional = _finite_positive("min_notional", min_notional, allow_zero=True)
    if risk_fraction > 1 or max_notional_fraction > 1:
        raise ValueError("risk_fraction and max_notional_fraction cannot exceed 1")

    risk_budget = equity * risk_fraction
    stop_distance = abs(entry - stop)
    risk_limited_qty = risk_budget / stop_distance
    notional_cap = equity * max_notional_fraction * max_leverage
    notional_limited_qty = notional_cap / entry
    quantity = min(risk_limited_qty, notional_limited_qty)
    if qty_step > 0:
        quantity = math.floor((quantity + 1e-12) / qty_step) * qty_step
    notional = quantity * entry
    estimated_stop_loss = quantity * stop_distance
    reason = None
    if quantity <= 0:
        reason = "rounded_quantity_is_zero"
    elif quantity < min_quantity:
        reason = "below_minimum_quantity"
    elif notional < min_notional:
        reason = "below_minimum_notional"
    elif estimated_stop_loss > risk_budget + max(1e-10, risk_budget * 1e-9):
        reason = "risk_budget_exceeded"

    return {
        "accepted": reason is None,
        "reason": reason,
        "side": side,
        "quantity": quantity if reason is None else 0.0,
        "candidate_quantity": quantity,
        "entry_price": entry,
        "stop_price": stop,
        "notional": notional if reason is None else 0.0,
        "risk_budget": risk_budget,
        "estimated_stop_loss": estimated_stop_loss,
        "notional_cap": notional_cap,
        "risk_fraction": risk_fraction,
    }


def evaluate_entry(
    *,
    data_age_seconds: float,
    max_data_age_seconds: float,
    reconciliation_age_seconds: float,
    max_reconciliation_age_seconds: float,
    daily_pnl_fraction: float,
    peak_drawdown_fraction: float,
    current_exposure_fraction: float,
    proposed_exposure_fraction: float,
    max_daily_loss_fraction: float = 0.01,
    max_drawdown_fraction: float = 0.05,
    max_exposure_fraction: float = 1.0,
    kill_switch: bool = False,
) -> dict:
    """Fail-closed entry gate. PnL fractions are signed: losses are negative."""
    numeric = {
        "data_age_seconds": data_age_seconds,
        "max_data_age_seconds": max_data_age_seconds,
        "reconciliation_age_seconds": reconciliation_age_seconds,
        "max_reconciliation_age_seconds": max_reconciliation_age_seconds,
        "daily_pnl_fraction": daily_pnl_fraction,
        "peak_drawdown_fraction": peak_drawdown_fraction,
        "current_exposure_fraction": current_exposure_fraction,
        "proposed_exposure_fraction": proposed_exposure_fraction,
        "max_daily_loss_fraction": max_daily_loss_fraction,
        "max_drawdown_fraction": max_drawdown_fraction,
        "max_exposure_fraction": max_exposure_fraction,
    }
    values = {key: float(value) for key, value in numeric.items()}
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("all risk-gate inputs must be finite")
    if any(values[key] < 0 for key in (
        "data_age_seconds", "max_data_age_seconds",
        "reconciliation_age_seconds", "max_reconciliation_age_seconds",
        "current_exposure_fraction", "proposed_exposure_fraction",
        "max_daily_loss_fraction", "max_drawdown_fraction",
        "max_exposure_fraction",
    )):
        raise ValueError("ages, exposures and loss limits must be non-negative")

    reasons = []
    if kill_switch:
        reasons.append("kill_switch_active")
    if values["data_age_seconds"] > values["max_data_age_seconds"]:
        reasons.append("market_data_stale")
    if values["reconciliation_age_seconds"] > values["max_reconciliation_age_seconds"]:
        reasons.append("exchange_reconciliation_stale")
    if values["daily_pnl_fraction"] <= -values["max_daily_loss_fraction"]:
        reasons.append("daily_loss_limit_reached")
    if values["peak_drawdown_fraction"] <= -values["max_drawdown_fraction"]:
        reasons.append("maximum_drawdown_reached")
    total_exposure = values["current_exposure_fraction"] + values["proposed_exposure_fraction"]
    if total_exposure > values["max_exposure_fraction"] + 1e-12:
        reasons.append("maximum_exposure_exceeded")

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "total_exposure_fraction": total_exposure,
    }
