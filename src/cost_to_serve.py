"""Cost-to-serve allocation engine (capability gap #3, the CFO lens).

Activity-based cost-to-serve: every customer / channel / SKU segment is charged for
the cost of *serving* it, not just its product cost. Four pools - product (COGS or
landed cost), fulfillment (orders + units shipped + outbound freight), returns, and
overhead (account management / dedicated service) - roll up to the net-to-serve margin.
A portfolio view then ranks segments best-to-worst and exposes the profitability
concentration (the "whale curve": cumulative profit peaks above the net total, then the
loss-making tail erodes it).

This promotes the ad-hoc ``profit / sales`` the SCM harnesses compute into an auditable
module that works *without* a precomputed profit column - the general consulting case.
Pure / deterministic (frozen dataclasses + pure functions). Reference: Christopher,
*Logistics & Supply Chain Management* (cost-to-serve / Stobachoff curve); Cooper &
Kaplan, activity-based costing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceCostRates:
    """Activity cost-driver rates, shared across the segments in one analysis."""

    cost_per_order: float = 0.0            # pick / pack / handle per order line
    cost_per_unit_shipped: float = 0.0     # variable fulfillment per unit
    return_handling_per_unit: float = 0.0  # reverse-logistics cost per returned unit


@dataclass(frozen=True)
class SegmentActivity:
    """The revenue and volume drivers for one segment over a period."""

    segment: str
    revenue: float
    units: float
    orders: float
    cogs: float                    # product cost (COGS or landed cost) for the segment
    returns_units: float = 0.0
    outbound_freight: float = 0.0  # freight-to-customer already known (e.g. from data)
    overhead: float = 0.0          # direct fixed cost to serve: account mgmt / dedicated service


@dataclass(frozen=True)
class SegmentCostToServe:
    """One segment fully costed: the four pools, the net-to-serve, and the margins."""

    segment: str
    revenue: float
    product_cost: float
    fulfillment_cost: float
    returns_cost: float
    overhead_cost: float
    total_cost_to_serve: float
    gross_margin: float        # revenue - product_cost (before the cost to serve)
    net_to_serve: float        # revenue - total cost to serve (the CFO number)
    net_margin_pct: float      # net_to_serve / revenue (0 when no revenue)
    cost_to_serve_pct: float   # (fulfillment + returns + overhead) / revenue


@dataclass(frozen=True)
class CostToServePortfolio:
    """The ranked portfolio plus its profitability concentration."""

    segments: tuple[SegmentCostToServe, ...]   # ranked best-to-worst by net_to_serve
    total_revenue: float
    total_net_to_serve: float
    overall_net_margin: float
    loss_making: tuple[SegmentCostToServe, ...]
    peak_profit: float         # sum of the positive segments (the whale-curve peak)
    profit_erosion: float      # peak - total: how much the loss-making tail destroys


def cost_to_serve(activity: SegmentActivity, rates: ServiceCostRates) -> SegmentCostToServe:
    """Allocate the four cost pools to one segment and roll up its net-to-serve margin."""
    product = activity.cogs
    fulfillment = (
        activity.orders * rates.cost_per_order
        + activity.units * rates.cost_per_unit_shipped
        + activity.outbound_freight
    )
    returns = activity.returns_units * rates.return_handling_per_unit
    overhead = activity.overhead
    total = product + fulfillment + returns + overhead

    revenue = activity.revenue
    net = revenue - total
    net_margin = (net / revenue) if revenue > 0 else 0.0
    cts_pct = ((fulfillment + returns + overhead) / revenue) if revenue > 0 else 0.0

    return SegmentCostToServe(
        segment=activity.segment,
        revenue=revenue,
        product_cost=product,
        fulfillment_cost=fulfillment,
        returns_cost=returns,
        overhead_cost=overhead,
        total_cost_to_serve=total,
        gross_margin=revenue - product,
        net_to_serve=net,
        net_margin_pct=net_margin,
        cost_to_serve_pct=cts_pct,
    )


def rank_segments(
    activities: list[SegmentActivity], rates: ServiceCostRates
) -> list[SegmentCostToServe]:
    """Cost every segment and sort them best-to-worst by net-to-serve."""
    costed = [cost_to_serve(a, rates) for a in activities]
    return sorted(costed, key=lambda s: s.net_to_serve, reverse=True)


def analyze_portfolio(
    activities: list[SegmentActivity], rates: ServiceCostRates
) -> CostToServePortfolio:
    """Roll the segments into a portfolio view with the profitability concentration."""
    if not activities:
        raise ValueError("no segments to analyze")
    ranked = rank_segments(activities, rates)

    total_revenue = sum(s.revenue for s in ranked)
    total_net = sum(s.net_to_serve for s in ranked)
    peak = sum(s.net_to_serve for s in ranked if s.net_to_serve > 0)

    return CostToServePortfolio(
        segments=tuple(ranked),
        total_revenue=total_revenue,
        total_net_to_serve=total_net,
        overall_net_margin=(total_net / total_revenue) if total_revenue > 0 else 0.0,
        loss_making=tuple(s for s in ranked if s.net_to_serve < 0),
        peak_profit=peak,
        profit_erosion=peak - total_net,
    )
