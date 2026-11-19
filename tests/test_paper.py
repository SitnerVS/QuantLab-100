import pytest

from quantlab.paper.engine import apply_paper_signal, new_account, rub_to_usd


def test_buy_and_sell_updates_cash_and_realized_pnl():
    account = new_account(25)
    account, buy = apply_paper_signal(
        account, 1, 100, "2026-01-01T00:00:00+00:00",
        fee_rate=0, slippage_rate=0, spread_rate=0,
    )
    assert buy["status"] == "buy"
    assert account["cash"] == pytest.approx(0)
    assert account["quantity"] == pytest.approx(0.25)

    account, sell = apply_paper_signal(
        account, 0, 110, "2026-01-01T01:00:00+00:00",
        fee_rate=0, slippage_rate=0, spread_rate=0,
    )
    assert sell["status"] == "sell"
    assert account["cash"] == pytest.approx(27.5)
    assert account["realized_pnl"] == pytest.approx(2.5)
    assert account["quantity"] == 0


def test_duplicate_bar_is_idempotent():
    account = new_account(25)
    account, _ = apply_paper_signal(account, 1, 100, "bar-1", 0, 0, 0)
    cash = account["cash"]
    quantity = account["quantity"]
    account, event = apply_paper_signal(account, 1, 105, "bar-1", 0, 0, 0)
    assert event["status"] == "duplicate_bar"
    assert account["cash"] == cash
    assert account["quantity"] == quantity
    assert len(account["ledger"]) == 1


def test_costs_reduce_entry_and_exit_proceeds():
    account = new_account(25)
    account, _ = apply_paper_signal(account, 1, 100, "bar-1", 0.001, 0.001, 0.002)
    account, event = apply_paper_signal(account, 0, 100, "bar-2", 0.001, 0.001, 0.002)
    assert event["status"] == "sell"
    assert account["cash"] < 25
    assert account["realized_pnl"] < 0


def test_entry_fee_is_included_in_realized_pnl():
    account = new_account(25)
    account, _ = apply_paper_signal(account, 1, 100, "bar-1", 0.01, 0, 0)
    account, sell = apply_paper_signal(account, 0, 100, "bar-2", 0.01, 0, 0)
    assert sell["status"] == "sell"
    assert account["realized_pnl"] == pytest.approx(-0.495049504950496)


def test_rub_capital_is_converted_to_usd_quote_currency():
    assert rub_to_usd(25, 100) == pytest.approx(0.25)


def test_rub_conversion_rejects_invalid_rate():
    with pytest.raises(ValueError):
        rub_to_usd(25, 0)
