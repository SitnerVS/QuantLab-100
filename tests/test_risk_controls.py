import pytest

from quantlab.risk.controls import calculate_position_size, evaluate_entry


def test_position_size_is_limited_by_stop_risk():
    result = calculate_position_size(
        10_000, 100, 98, risk_fraction=0.0025,
        max_notional_fraction=1.0, max_leverage=1.0,
    )
    assert result["accepted"] is True
    assert result["quantity"] == pytest.approx(12.5)
    assert result["estimated_stop_loss"] == pytest.approx(25)


def test_position_size_rounds_down_to_exchange_step():
    result = calculate_position_size(
        10_000, 100, 98, qty_step=0.1,
    )
    assert result["accepted"] is True
    assert result["quantity"] == pytest.approx(12.5)


def test_position_rejected_if_venue_minimum_would_exceed_risk_budget():
    result = calculate_position_size(
        100, 100, 99, risk_fraction=0.0025,
        min_quantity=0.01,
    )
    assert result["accepted"] is False
    assert result["reason"] == "below_minimum_quantity"
    assert result["quantity"] == 0


def test_short_stop_must_be_above_entry():
    with pytest.raises(ValueError, match="above entry"):
        calculate_position_size(1000, 100, 99, side="short")


def test_risk_gate_rejects_stale_data_and_daily_loss():
    result = evaluate_entry(
        data_age_seconds=90, max_data_age_seconds=30,
        reconciliation_age_seconds=10, max_reconciliation_age_seconds=60,
        daily_pnl_fraction=-0.012, peak_drawdown_fraction=-0.02,
        current_exposure_fraction=0.1, proposed_exposure_fraction=0.1,
    )
    assert result["accepted"] is False
    assert "market_data_stale" in result["reasons"]
    assert "daily_loss_limit_reached" in result["reasons"]


def test_risk_gate_blocks_when_kill_switch_is_active():
    result = evaluate_entry(
        data_age_seconds=0, max_data_age_seconds=30,
        reconciliation_age_seconds=0, max_reconciliation_age_seconds=60,
        daily_pnl_fraction=0, peak_drawdown_fraction=0,
        current_exposure_fraction=0, proposed_exposure_fraction=0.1,
        kill_switch=True,
    )
    assert result["accepted"] is False
    assert result["reasons"] == ["kill_switch_active"]


def test_risk_gate_rejects_exposure_over_limit():
    result = evaluate_entry(
        data_age_seconds=0, max_data_age_seconds=30,
        reconciliation_age_seconds=0, max_reconciliation_age_seconds=60,
        daily_pnl_fraction=0, peak_drawdown_fraction=0,
        current_exposure_fraction=0.9, proposed_exposure_fraction=0.2,
        max_exposure_fraction=1.0,
    )
    assert result["accepted"] is False
    assert "maximum_exposure_exceeded" in result["reasons"]


def test_risk_gate_rejects_non_finite_inputs():
    with pytest.raises(ValueError, match="finite"):
        evaluate_entry(
            data_age_seconds=float("nan"), max_data_age_seconds=30,
            reconciliation_age_seconds=0, max_reconciliation_age_seconds=60,
            daily_pnl_fraction=0, peak_drawdown_fraction=0,
            current_exposure_fraction=0, proposed_exposure_fraction=0.1,
        )
