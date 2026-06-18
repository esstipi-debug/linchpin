"""Cost and service level optimization — Vandeput (2020), Chapter 8."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
from scipy.stats import norm

from src.fill_rate import fill_rate_from_safety_stock, normal_loss_standard
from src.risk_period import RiskPeriodStats, demand_over_risk_period


@dataclass(frozen=True)
class CostBreakdown:
    """Inventory cost components per period (R,S) or per year (s,Q)."""

    total: float
    holding: float
    transaction: float
    backorder: float
    cycle_service_level: float
    fill_rate: float
    service_level_factor: float
    safety_stock: float


@dataclass(frozen=True)
class RSOptimizationResult:
    """Best (R,S) policy from review-period search."""

    review_period: float
    cost: CostBreakdown
    order_up_to_level: float
    risk_stats: RiskPeriodStats


@dataclass(frozen=True)
class SQOptimizationResult:
    """Optimized (s,Q) policy after Q/z iteration (Section 8.3.1)."""

    order_quantity: float
    reorder_point: float
    cost: CostBreakdown
    iterations: int
    risk_stats: RiskPeriodStats


def optimal_cycle_service_level_rs(
    holding_cost_per_period: float,
    review_period: float,
    backorder_cost: float,
) -> float:
    """alpha* = 1 - h*R/b (eq. 8.3). Returns NaN if make-to-order is optimal."""
    if backorder_cost <= 0:
        raise ValueError("backorder_cost must be > 0")
    alpha = 1.0 - (holding_cost_per_period * review_period) / backorder_cost
    return max(0.0, min(1.0, alpha))


def optimal_cycle_service_level_sq(
    holding_cost_per_year: float,
    order_quantity: float,
    annual_demand: float,
    backorder_cost: float,
) -> float:
    """alpha* = 1 - h*Q/(b*D) (eq. 8.4)."""
    if backorder_cost <= 0 or annual_demand <= 0:
        raise ValueError("backorder_cost and annual_demand must be > 0")
    alpha = 1.0 - (holding_cost_per_year * order_quantity) / (backorder_cost * annual_demand)
    return max(0.0, min(1.0, alpha))


def rs_cost_per_period(
    holding_cost_per_period: float,
    mean_demand_per_period: float,
    review_period: float,
    service_level_factor: float,
    sigma_x: float,
    fixed_order_cost: float,
    backorder_cost: float,
) -> CostBreakdown:
    """
    C = h(dR/2 + z*sigma_x) + k/R + b*sigma_x*L_N(z)/R (eq. 8.2).
    """
    if review_period <= 0:
        raise ValueError("review_period must be > 0")

    cycle_stock = mean_demand_per_period * review_period / 2
    safety = service_level_factor * sigma_x
    holding = holding_cost_per_period * (cycle_stock + safety)
    transaction = fixed_order_cost / review_period
    backorder = backorder_cost * sigma_x * float(normal_loss_standard(service_level_factor)) / review_period
    cycle_demand = mean_demand_per_period * review_period
    beta = fill_rate_from_safety_stock(safety, cycle_demand, sigma_x)

    return CostBreakdown(
        total=holding + transaction + backorder,
        holding=holding,
        transaction=transaction,
        backorder=backorder,
        cycle_service_level=float(norm.cdf(service_level_factor)),
        fill_rate=beta,
        service_level_factor=service_level_factor,
        safety_stock=safety,
    )


def sq_cost_per_year(
    holding_cost_per_year: float,
    order_quantity: float,
    service_level_factor: float,
    sigma_x: float,
    annual_demand: float,
    fixed_order_cost: float,
    backorder_cost: float,
) -> CostBreakdown:
    """
    C = h(Q/2 + z*sigma_x) + kD/Q + b*sigma_x*L_N(z)*D/Q (Section 8.3.1).
    """
    if order_quantity <= 0 or annual_demand <= 0:
        raise ValueError("order_quantity and annual_demand must be > 0")

    cycle_stock = order_quantity / 2
    safety = service_level_factor * sigma_x
    holding = holding_cost_per_year * (cycle_stock + safety)
    transaction = fixed_order_cost * annual_demand / order_quantity
    loss = float(normal_loss_standard(service_level_factor))
    backorder = backorder_cost * sigma_x * loss * annual_demand / order_quantity
    beta = fill_rate_from_safety_stock(safety, order_quantity, sigma_x)

    return CostBreakdown(
        total=holding + transaction + backorder,
        holding=holding,
        transaction=transaction,
        backorder=backorder,
        cycle_service_level=float(norm.cdf(service_level_factor)),
        fill_rate=beta,
        service_level_factor=service_level_factor,
        safety_stock=safety,
    )


def optimize_rs_policy(
    mean_demand_per_period: float,
    demand_std_per_period: float,
    mean_lead_time: float,
    holding_cost_per_period: float,
    fixed_order_cost: float,
    backorder_cost: float,
    review_periods: list[float] | None = None,
    lead_time_std: float = 0.0,
) -> RSOptimizationResult:
    """Search review periods; for each R use optimal z* (Section 8.2)."""
    if review_periods is None:
        review_periods = [float(r) for r in range(1, 8)]

    best: RSOptimizationResult | None = None

    for r in review_periods:
        risk = demand_over_risk_period(
            mean_demand_per_period,
            demand_std_per_period,
            mean_lead_time,
            lead_time_std,
            review_period=r,
        )
        alpha = optimal_cycle_service_level_rs(holding_cost_per_period, r, backorder_cost)
        if alpha <= 0:
            continue
        z = float(norm.ppf(alpha))
        cost = rs_cost_per_period(
            holding_cost_per_period,
            mean_demand_per_period,
            r,
            z,
            risk.demand_std,
            fixed_order_cost,
            backorder_cost,
        )
        order_up_to = (
            mean_demand_per_period * (mean_lead_time + r) + cost.safety_stock
        )
        candidate = RSOptimizationResult(
            review_period=r,
            cost=cost,
            order_up_to_level=order_up_to,
            risk_stats=risk,
        )
        if best is None or candidate.cost.total < best.cost.total:
            best = candidate

    if best is None:
        raise ValueError("no feasible review period: backorder cost too low vs holding")
    return best


def optimize_sq_policy(
    annual_demand: float,
    mean_demand_per_period: float,
    demand_std_per_period: float,
    mean_lead_time: float,
    holding_cost_per_year: float,
    fixed_order_cost: float,
    backorder_cost: float,
    lead_time_std: float = 0.0,
    max_iterations: int = 50,
    tolerance: float = 1e-4,
) -> SQOptimizationResult:
    """
    Iterate Q and z* until convergence (Section 8.3.1 steps 1–4).
    """
    risk = demand_over_risk_period(
        mean_demand_per_period,
        demand_std_per_period,
        mean_lead_time,
        lead_time_std,
        review_period=0.0,
    )
    q = math.sqrt(2 * fixed_order_cost * annual_demand / holding_cost_per_year)
    z = 0.0

    for iteration in range(1, max_iterations + 1):
        alpha = optimal_cycle_service_level_sq(holding_cost_per_year, q, annual_demand, backorder_cost)
        z_new = float(norm.ppf(max(alpha, 1e-9)))
        loss = float(normal_loss_standard(z_new))
        q_new = math.sqrt(2 * (fixed_order_cost + backorder_cost * risk.demand_std * loss) * annual_demand / holding_cost_per_year)

        if abs(q_new - q) < tolerance and abs(z_new - z) < tolerance:
            q, z = q_new, z_new
            break
        q, z = q_new, z_new
    else:
        iteration = max_iterations

    cost = sq_cost_per_year(
        holding_cost_per_year,
        q,
        z,
        risk.demand_std,
        annual_demand,
        fixed_order_cost,
        backorder_cost,
    )
    reorder_point = risk.mean_demand + cost.safety_stock

    return SQOptimizationResult(
        order_quantity=q,
        reorder_point=reorder_point,
        cost=cost,
        iterations=iteration,
        risk_stats=risk,
    )


def compare_review_periods(
    mean_demand_per_period: float,
    demand_std_per_period: float,
    mean_lead_time: float,
    holding_cost_per_period: float,
    fixed_order_cost: float,
    backorder_cost: float,
    review_periods: list[float] | None = None,
    lead_time_std: float = 0.0,
) -> pd.DataFrame:
    """Table like Figure 8.5 — cost, alpha*, fill rate by R."""
    if review_periods is None:
        review_periods = [float(r) for r in range(1, 8)]

    rows: list[dict] = []
    for r in review_periods:
        risk = demand_over_risk_period(
            mean_demand_per_period,
            demand_std_per_period,
            mean_lead_time,
            lead_time_std,
            review_period=r,
        )
        alpha = optimal_cycle_service_level_rs(holding_cost_per_period, r, backorder_cost)
        z = float(norm.ppf(max(alpha, 1e-9)))
        cost = rs_cost_per_period(
            holding_cost_per_period,
            mean_demand_per_period,
            r,
            z,
            risk.demand_std,
            fixed_order_cost,
            backorder_cost,
        )
        rows.append(
            {
                "review_period": r,
                "inventory_cost": round(cost.total, 2),
                "cycle_service_level": round(cost.cycle_service_level, 4),
                "fill_rate": round(cost.fill_rate, 4),
                "safety_stock": round(cost.safety_stock, 2),
            }
        )
    return pd.DataFrame(rows)
