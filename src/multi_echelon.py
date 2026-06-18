"""Multi-echelon GSM (serial) — Vandeput (2020), Chapter 10."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
from scipy.stats import norm

from src.safety_stock import service_level_factor


@dataclass(frozen=True)
class EchelonNode:
    index: int
    lead_time: float
    holding_cost: float
    risk_period: float
    safety_stock: float
    order_up_to: float


@dataclass(frozen=True)
class GSMAllocation:
    case_id: int
    risk_periods: tuple[float, ...]
    nodes: tuple[EchelonNode, ...]
    total_holding_cost: float
    echelon_order_up_to: tuple[float, ...]


def serial_gsm_cases(
    lead_times: list[float],
    review_period: float = 1.0,
) -> list[tuple[float, ...]]:
    """
    All-or-nothing risk-period patterns for serial chain (Section 10.4.3).

    2^(n-1) cases; demand node always holds review period in its coverage when stocking.
    """
    n = len(lead_times)
    if n == 0:
        raise ValueError("lead_times required")
    total = sum(lead_times) + review_period
    cases: list[tuple[float, ...]] = []

    for mask in product([0, 1], repeat=n - 1):
        x_tau = [0.0] * n
        cumulative = 0.0
        for i in range(n - 1):
            if mask[i]:
                x_tau[i] = cumulative + lead_times[i]
                cumulative = 0.0
            else:
                cumulative += lead_times[i]
                x_tau[i] = 0.0
        x_tau[-1] = total - sum(x_tau[:-1])
        if x_tau[-1] < review_period:
            continue
        cases.append(tuple(x_tau))

    # Deduplicate while preserving order
    unique: list[tuple[float, ...]] = []
    for case in cases:
        if case not in unique:
            unique.append(case)
    return unique


def evaluate_serial_allocation(
    risk_periods: tuple[float, ...],
    lead_times: list[float],
    mean_demand_per_period: float,
    demand_std_per_period: float,
    holding_costs: list[float],
    cycle_service_level: float,
    review_period: float = 1.0,
    case_id: int = 0,
) -> GSMAllocation:
    """Ss_i = z * sigma_d * sqrt(x_i); cost = sum(Ss_i * h_i) (eq. 10.1)."""
    z = service_level_factor(cycle_service_level)
    nodes: list[EchelonNode] = []
    for i, (lt, h, x_tau) in enumerate(zip(lead_times, holding_costs, risk_periods)):
        ss = z * demand_std_per_period * (x_tau**0.5) if x_tau > 0 else 0.0
        mu_x = mean_demand_per_period * x_tau
        order_up_to = mu_x + ss if x_tau > 0 else 0.0
        nodes.append(
            EchelonNode(
                index=i,
                lead_time=lt,
                holding_cost=h,
                risk_period=x_tau,
                safety_stock=ss,
                order_up_to=order_up_to,
            )
        )

    total_cost = sum(node.safety_stock * node.holding_cost for node in nodes)
    order_up_levels = [node.order_up_to for node in nodes]
    echelon = []
    running = 0.0
    for s in reversed(order_up_levels):
        running += s
        echelon.append(running)
    echelon = tuple(reversed(echelon))

    return GSMAllocation(
        case_id=case_id,
        risk_periods=risk_periods,
        nodes=tuple(nodes),
        total_holding_cost=total_cost,
        echelon_order_up_to=echelon,
    )


def optimize_serial_gsm(
    lead_times: list[float],
    mean_demand_per_period: float,
    demand_std_per_period: float,
    holding_costs: list[float],
    cycle_service_level: float,
    review_period: float = 1.0,
) -> GSMAllocation:
    """Pick allocation minimizing holding cost (Section 10.4.3)."""
    cases = serial_gsm_cases(lead_times, review_period)
    best: GSMAllocation | None = None
    for idx, case in enumerate(cases, start=1):
        candidate = evaluate_serial_allocation(
            case,
            lead_times,
            mean_demand_per_period,
            demand_std_per_period,
            holding_costs,
            cycle_service_level,
            review_period,
            case_id=idx,
        )
        if best is None or candidate.total_holding_cost < best.total_holding_cost:
            best = candidate
    if best is None:
        raise ValueError("no feasible GSM allocation")
    return best


def echelon_inventory(
    local_on_hand: list[float],
) -> list[float]:
    """Echelon inventory = sum from node i through downstream (Section 10.4.4)."""
    n = len(local_on_hand)
    result = []
    for i in range(n):
        result.append(sum(local_on_hand[i:]))
    return result


def echelon_orders(
    local_on_hand: list[float],
    in_transit: list[float],
    echelon_targets: tuple[float, ...],
) -> list[float]:
    """Orders = echelon target - echelon net inventory."""
    net_local = [on_hand + transit for on_hand, transit in zip(local_on_hand, in_transit)]
    echelon_net = echelon_inventory(net_local)
    return [max(target - net, 0.0) for target, net in zip(echelon_targets, echelon_net)]
