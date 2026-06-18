"""Deterministic EOQ model — Vandeput (2020), Chapter 2."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class EOQResult:
    """Optimal order quantity and associated costs."""

    order_quantity: float
    optimal_total_cost: float
    holding_cost: float
    transaction_cost: float
    orders_per_year: float
    review_period: float


def compute_eoq(
    annual_demand: float,
    holding_cost_per_unit: float,
    fixed_order_cost: float,
) -> EOQResult:
    """
    Economic Order Quantity (eq. 2.2–2.3).

    Parameters
    ----------
    annual_demand:
        Yearly demand D (units/year).
    holding_cost_per_unit:
        Variable holding cost h (currency/unit/year).
    fixed_order_cost:
        Fixed transaction cost k per order (currency).
    """
    if annual_demand <= 0 or holding_cost_per_unit <= 0 or fixed_order_cost <= 0:
        raise ValueError("annual_demand, holding_cost_per_unit, and fixed_order_cost must be > 0")

    q_star = math.sqrt(2 * fixed_order_cost * annual_demand / holding_cost_per_unit)
    optimal_cost = math.sqrt(2 * fixed_order_cost * annual_demand * holding_cost_per_unit)
    holding = holding_cost_per_unit * q_star / 2
    transaction = fixed_order_cost * annual_demand / q_star
    orders_per_year = annual_demand / q_star
    review_period = q_star / annual_demand

    return EOQResult(
        order_quantity=q_star,
        optimal_total_cost=optimal_cost,
        holding_cost=holding,
        transaction_cost=transaction,
        orders_per_year=orders_per_year,
        review_period=review_period,
    )


def total_cost(
    order_quantity: float,
    annual_demand: float,
    holding_cost_per_unit: float,
    fixed_order_cost: float,
) -> float:
    """Total yearly supply chain cost for a given Q (eq. 2.1)."""
    if order_quantity <= 0:
        raise ValueError("order_quantity must be > 0")
    return fixed_order_cost * annual_demand / order_quantity + holding_cost_per_unit * order_quantity / 2


def cost_ratio_vs_optimal(order_quantity: float, optimal_quantity: float) -> float:
    """C(Q)/C(Q*) ratio from sensitivity analysis (Section 2.4)."""
    if order_quantity <= 0 or optimal_quantity <= 0:
        raise ValueError("quantities must be > 0")
    return 0.5 * (optimal_quantity / order_quantity + order_quantity / optimal_quantity)


def round_review_period_power_of_two(
    optimal_period: float,
    base_period: float = 1.0,
) -> float:
    """
    Power-of-2 review period policy (Section 3.2.1).

    Returns R = 2^k * base_period with k minimal such that T*/sqrt(2) <= R <= sqrt(2)*T*.
    """
    if optimal_period <= 0 or base_period <= 0:
        raise ValueError("periods must be > 0")

    lower = optimal_period / math.sqrt(2)
    upper = optimal_period * math.sqrt(2)
    k = 0
    while True:
        candidate = (2**k) * base_period
        if lower <= candidate <= upper:
            return candidate
        if candidate > upper:
            return candidate
        k += 1
