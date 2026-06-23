"""Tests for the cost-to-serve / working-capital deck composer (jobs.cost_to_serve_deliverable).

Turns the CFO-lens analysis (segment profitability + cash-to-cash + cash-release) into the
client deck: the loss-making segments to fix or fire, the profit erosion, the working
capital tied up, and the cash a few days of cycle improvement would free.
"""

from jobs.cost_to_serve_deliverable import build
from src.cost_to_serve import SegmentActivity, ServiceCostRates, analyze_portfolio
from src.deliverable import Deliverable
from src.working_capital import cash_release_plan, working_capital

_RATES = ServiceCostRates(cost_per_order=5.0, cost_per_unit_shipped=1.5, return_handling_per_unit=8.0)
_RETAIL = SegmentActivity("Retail", 10_000.0, 500.0, 50.0, 6_000.0, 20.0, 400.0, 300.0)
_BARGAIN = SegmentActivity("Bargain", 2_000.0, 400.0, 80.0, 1_500.0, 40.0, 300.0, 300.0)


def _portfolio():
    return analyze_portfolio([_RETAIL, _BARGAIN], _RATES)


def test_build_returns_a_deliverable_with_the_overall_margin():
    d = build(_portfolio(), client="Acme")

    assert isinstance(d, Deliverable)
    assert d.client == "Acme"
    assert "6%" in d.summary or "6.0%" in d.summary               # overall net margin


def test_loss_making_segment_is_named_in_the_findings():
    text = build(_portfolio()).to_markdown()

    assert "Bargain" in text


def test_kpis_include_cash_cycle_and_release_when_provided():
    wc = working_capital(revenue=12_000.0, cogs=7_500.0, dio=60.0, dso=45.0, dpo=30.0)
    cr = cash_release_plan(revenue=12_000.0, cogs=7_500.0, dio_days=10.0)

    d = build(_portfolio(), working_cap=wc, cash_release=cr)

    names = {k.name for k in d.kpis}
    assert any("margin" in n.lower() for n in names)
    assert any("cash" in n.lower() or "cycle" in n.lower() for n in names)


def test_works_without_working_capital_inputs():
    d = build(_portfolio())  # cost-to-serve only, no cash lens

    assert isinstance(d, Deliverable)
    assert d.kpis  # still produces the profitability KPIs


def test_recommendations_address_the_worst_segment():
    d = build(_portfolio())

    assert any("Bargain" in r for r in d.recommendations)


def test_coverage_block_flags_the_commercial_residual():
    md = build(_portfolio()).to_markdown().lower()

    assert "re-pric" in md or "renegotiat" in md or "sign-off" in md


def test_cash_release_opportunity_surfaces_in_the_summary_or_findings():
    cr = cash_release_plan(revenue=12_000.0, cogs=7_500.0, dio_days=10.0, dso_days=5.0)

    text = (build(_portfolio(), cash_release=cr).to_markdown()).lower()

    assert "cash" in text and ("release" in text or "free" in text or "working capital" in text)


def test_markdown_is_ascii_only_for_cp1252_safety():
    wc = working_capital(revenue=12_000.0, cogs=7_500.0, dio=60.0, dso=45.0, dpo=30.0)
    cr = cash_release_plan(revenue=12_000.0, cogs=7_500.0, dio_days=10.0)

    md = build(_portfolio(), working_cap=wc, cash_release=cr,
               citations=("Christopher - cost-to-serve",)).to_markdown()

    assert md.isascii()


def test_citations_pass_through():
    d = build(_portfolio(), citations=("SCOR - cash-to-cash AM.1.1",))

    assert "SCOR - cash-to-cash AM.1.1" in d.citations
