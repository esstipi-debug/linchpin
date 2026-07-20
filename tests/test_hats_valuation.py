"""Valuation tests: the neutral judge, the baseline mirror, the value table,
agreement@1 and the parallel runner (spec sec 5, sec 9, sec 12.4)."""

import pytest

from src.eoq import PriceBreak
from src.hats import (
    Candidate,
    HatConfig,
    baseline_plan,
    build_inputs,
    decision_cost,
    shortage_cost_per_unit,
)


def _flat_inputs():
    """Hand-checkable SKU: D=5200, mu_w=100, sigma_w=30, L_w=1, c=10, NO discounts
    (single base tier), defaults K=75, h_total=0.25, wacc=0.12, margin=0.30."""
    return build_inputs(
        sku="HAND", annual_demand=5200.0, mean_weekly=100.0, std_weekly=30.0,
        lead_time_weeks=1.0, unit_cost=10.0, config=HatConfig(),
        price_breaks=(PriceBreak(0.0, 10.0),),
    )


def test_judge_cost_verified_by_hand():
    """C(400, 0.95) term by term, constants derived by hand (comments):

    z(0.95)  = 1.6448536...          (Phi^-1)
    L_N(z)   = phi(z) - z*(1-0.95) = 0.1031356 - 0.0822427 = 0.0208932
    SS       = z * 30 * sqrt(1) = 49.3456
    purchase = D*c            = 5200 * 10                = 52000.000
    ordering = K*D/Q          = 75 * 5200 / 400          =   975.000
    holding  = h*c*(Q/2 + SS) = 0.25*10*(200 + 49.3456)  =   623.364
    shortage = p_short*(D/Q)*sigma_L*L_N
             = 4.285714 * 13 * 30 * 0.0208932            =    34.921
    total                                                = 53633.285
    """
    inp = _flat_inputs()
    assert shortage_cost_per_unit(inp) == pytest.approx(10.0 * 0.30 / 0.70)
    c = decision_cost(inp, Candidate(order_quantity=400.0, service_level=0.95))
    assert c == pytest.approx(53633.285, rel=1e-4)


def test_judge_shortage_term_vanishes_when_demand_is_certain():
    inp = build_inputs(
        sku="CERT", annual_demand=5200.0, mean_weekly=100.0, std_weekly=0.0,
        lead_time_weeks=1.0, unit_cost=10.0, config=HatConfig(),
        price_breaks=(PriceBreak(0.0, 10.0),),
    )
    c = decision_cost(inp, Candidate(order_quantity=400.0, service_level=0.95))
    assert c == pytest.approx(52000.0 + 975.0 + 0.25 * 10.0 * 200.0, rel=1e-9)


def test_baseline_plan_is_classic_eoq_at_sl_target():
    from src.eoq import compute_eoq
    inp = _flat_inputs()
    base = baseline_plan(inp)
    assert base.service_level == 0.95
    assert base.order_quantity == pytest.approx(
        compute_eoq(5200.0, 0.25 * 10.0, 75.0).order_quantity)
