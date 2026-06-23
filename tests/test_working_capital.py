"""Tests for the working-capital / cash-release engine (capability gap #3, CFO lens).

Cash-to-cash cycle (DIO + DSO - DPO) and the cash freed by improving each lever:
trimming inventory days or receivables days, or extending payables days. Inventory and
payables scale on COGS; receivables scale on revenue. Math hand-checked for the QA gate.
Reference: SCOR cash-to-cash (AM.1.1); Chopra & Meindl, working-capital levers.
"""

import pytest

from src.financial_kpis import cash_to_cash
from src.working_capital import cash_release_plan, working_capital

_REVENUE = 1_000_000.0
_COGS = 600_000.0


def test_working_capital_decomposes_the_cash_cycle():
    wc = working_capital(revenue=_REVENUE, cogs=_COGS, dio=60.0, dso=45.0, dpo=30.0)

    assert wc.cash_conversion_cycle == pytest.approx(75.0)            # 60 + 45 - 30
    assert wc.inventory_investment == pytest.approx(_COGS / 365 * 60)  # 98_630.14
    assert wc.receivables == pytest.approx(_REVENUE / 365 * 45)        # 123_287.67
    assert wc.payables == pytest.approx(_COGS / 365 * 30)              # 49_315.07
    assert wc.net_working_capital == pytest.approx(
        _COGS / 365 * 60 + _REVENUE / 365 * 45 - _COGS / 365 * 30
    )


def test_cash_conversion_cycle_matches_financial_kpis():
    wc = working_capital(revenue=_REVENUE, cogs=_COGS, dio=60.0, dso=45.0, dpo=30.0)

    assert wc.cash_conversion_cycle == pytest.approx(cash_to_cash(60.0, 45.0, 30.0))


def test_cash_cycle_can_be_negative_when_payables_dominate():
    wc = working_capital(revenue=_REVENUE, cogs=_COGS, dio=20.0, dso=10.0, dpo=45.0)

    assert wc.cash_conversion_cycle == pytest.approx(-15.0)           # famous DTC / Dell case


def test_cash_release_per_lever():
    plan = cash_release_plan(
        revenue=_REVENUE, cogs=_COGS, dio_days=10.0, dso_days=5.0, dpo_days=5.0
    )

    by_lever = {r.lever: r.cash_released for r in plan.levers}
    assert by_lever["inventory (DIO)"] == pytest.approx(_COGS / 365 * 10)    # 16_438.36
    assert by_lever["receivables (DSO)"] == pytest.approx(_REVENUE / 365 * 5)  # 13_698.63
    assert by_lever["payables (DPO)"] == pytest.approx(_COGS / 365 * 5)       # 8_219.18
    assert plan.total_cash_released == pytest.approx(
        _COGS / 365 * 10 + _REVENUE / 365 * 5 + _COGS / 365 * 5
    )


def test_cash_release_only_lists_levers_that_move():
    plan = cash_release_plan(revenue=_REVENUE, cogs=_COGS, dio_days=10.0)

    assert [r.lever for r in plan.levers] == ["inventory (DIO)"]
    assert plan.total_cash_released == pytest.approx(_COGS / 365 * 10)


def test_dio_cash_release_equals_the_inventory_investment_delta():
    # Freeing N days of inventory should equal the drop in inventory investment.
    before = working_capital(revenue=_REVENUE, cogs=_COGS, dio=60.0, dso=45.0, dpo=30.0)
    after = working_capital(revenue=_REVENUE, cogs=_COGS, dio=50.0, dso=45.0, dpo=30.0)
    plan = cash_release_plan(revenue=_REVENUE, cogs=_COGS, dio_days=10.0)

    delta = before.inventory_investment - after.inventory_investment
    assert plan.total_cash_released == pytest.approx(delta)


def test_no_levers_means_no_cash_released():
    plan = cash_release_plan(revenue=_REVENUE, cogs=_COGS)

    assert plan.levers == ()
    assert plan.total_cash_released == pytest.approx(0.0)
