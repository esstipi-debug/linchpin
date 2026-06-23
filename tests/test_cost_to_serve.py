"""Tests for the cost-to-serve allocation engine (capability gap #3, CFO lens).

Activity-based cost-to-serve: allocate product + fulfillment + returns + overhead to
each customer / channel / SKU segment, yielding the net-to-serve margin and the
profitability concentration (the "whale curve"). Promotes the ad-hoc profit/sales the
SCM harnesses compute into an auditable module that works without a precomputed profit
column. Math hand-checked here for the QA gate. Reference: Christopher, *Logistics &
Supply Chain Management* (cost-to-serve / Stobachoff curve); Cooper & Kaplan (ABC).
"""

import pytest

from src.cost_to_serve import (
    SegmentActivity,
    ServiceCostRates,
    analyze_portfolio,
    cost_to_serve,
    rank_segments,
)

# A profitable segment and a loss-making one, sharing the same activity-cost rates.
_RATES = ServiceCostRates(
    cost_per_order=5.0,
    cost_per_unit_shipped=1.5,
    return_handling_per_unit=8.0,
)
_RETAIL = SegmentActivity(
    segment="Retail",
    revenue=10_000.0,
    units=500.0,
    orders=50.0,
    cogs=6_000.0,
    returns_units=20.0,
    outbound_freight=400.0,
    overhead=300.0,
)
_BARGAIN = SegmentActivity(
    segment="Bargain",
    revenue=2_000.0,
    units=400.0,
    orders=80.0,
    cogs=1_500.0,
    returns_units=40.0,
    outbound_freight=300.0,
    overhead=300.0,
)


def test_cost_to_serve_allocates_each_activity_pool():
    cts = cost_to_serve(_RETAIL, _RATES)

    assert cts.product_cost == pytest.approx(6_000.0)               # cogs
    assert cts.fulfillment_cost == pytest.approx(1_400.0)           # 50*5 + 500*1.5 + 400
    assert cts.returns_cost == pytest.approx(160.0)                 # 20*8
    assert cts.overhead_cost == pytest.approx(300.0)
    assert cts.total_cost_to_serve == pytest.approx(7_860.0)


def test_net_to_serve_and_margins():
    cts = cost_to_serve(_RETAIL, _RATES)

    assert cts.gross_margin == pytest.approx(4_000.0)              # revenue - cogs
    assert cts.net_to_serve == pytest.approx(2_140.0)             # revenue - total CTS
    assert cts.net_margin_pct == pytest.approx(0.214)
    assert cts.cost_to_serve_pct == pytest.approx(0.186)          # (fulfil+ret+ovh)/rev


def test_a_high_touch_low_revenue_segment_goes_negative():
    cts = cost_to_serve(_BARGAIN, _RATES)

    # product 1500 + fulfil (400+600+300=1300) + returns 320 + overhead 300 = 3420 > 2000.
    assert cts.total_cost_to_serve == pytest.approx(3_420.0)
    assert cts.net_to_serve == pytest.approx(-1_420.0)
    assert cts.net_margin_pct < 0


def test_zero_revenue_segment_has_no_margin_blowup():
    empty = SegmentActivity(segment="New", revenue=0.0, units=0.0, orders=0.0, cogs=0.0)

    cts = cost_to_serve(empty, _RATES)

    assert cts.net_to_serve == pytest.approx(0.0)
    assert cts.net_margin_pct == pytest.approx(0.0)               # guarded, not inf/NaN
    assert cts.cost_to_serve_pct == pytest.approx(0.0)


def test_rank_segments_orders_best_to_worst_by_net_to_serve():
    ranked = rank_segments([_BARGAIN, _RETAIL], _RATES)

    assert [s.segment for s in ranked] == ["Retail", "Bargain"]
    assert ranked[0].net_to_serve > ranked[1].net_to_serve


def test_portfolio_rolls_up_and_finds_the_loss_makers():
    p = analyze_portfolio([_RETAIL, _BARGAIN], _RATES)

    assert p.total_revenue == pytest.approx(12_000.0)
    assert p.total_net_to_serve == pytest.approx(720.0)           # 2140 - 1420
    assert p.overall_net_margin == pytest.approx(0.06)            # 720/12000
    assert [s.segment for s in p.loss_making] == ["Bargain"]


def test_whale_curve_peak_and_erosion():
    p = analyze_portfolio([_RETAIL, _BARGAIN], _RATES)

    # Cumulative profit peaks at the sum of the positive segments, then the
    # loss-makers erode it back down to the net total.
    assert p.peak_profit == pytest.approx(2_140.0)
    assert p.profit_erosion == pytest.approx(1_420.0)             # peak - total


def test_empty_portfolio_is_rejected():
    with pytest.raises(ValueError):
        analyze_portfolio([], _RATES)
