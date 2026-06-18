"""Inventory policy simulation — Vandeput (2020), Chapter 5.3."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.random import Generator


@dataclass(frozen=True)
class SimulationResult:
    """Aggregated simulation metrics."""

    periods: int
    mean_on_hand: float
    mean_net_inventory: float
    simulated_cycle_service_level: float
    simulated_period_service_level: float
    stockout_periods: int
    mean_order_quantity: float


def _sample_demand(
    rng: Generator,
    periods: int,
    mean_demand: float,
    std_demand: float,
    historical_demand: np.ndarray | None,
) -> np.ndarray:
    if historical_demand is not None:
        hist = np.maximum(historical_demand.astype(float), 0.0)
        if len(hist) == 0:
            raise ValueError("historical_demand is empty")
        if len(hist) >= periods:
            return hist[:periods]
        indices = rng.integers(0, len(hist), size=periods)
        return hist[indices]

    draws = rng.normal(mean_demand, std_demand, size=periods)
    return np.maximum(draws, 0.0)


def simulate_rs_policy(
    order_up_to_level: float,
    lead_time_periods: int,
    review_period: int,
    periods: int = 10_000,
    *,
    mean_demand: float = 10.0,
    std_demand: float = 5.0,
    historical_demand: np.ndarray | None = None,
    seed: int | None = 42,
) -> SimulationResult:
    """
    Simulate periodic review (R, S) with backorders on net inventory.

    Backorders reduce net inventory below zero; excess demand is not lost.
    """
    if lead_time_periods < 0 or review_period <= 0:
        raise ValueError("invalid lead_time_periods or review_period")
    if order_up_to_level <= 0:
        raise ValueError("order_up_to_level must be > 0")

    rng = np.random.default_rng(seed)
    demand = _sample_demand(rng, periods, mean_demand, std_demand, historical_demand)

    on_hand = order_up_to_level
    pipeline: list[tuple[int, float]] = []
    backorders = 0.0

    on_hand_trace: list[float] = []
    net_trace: list[float] = []
    order_qty_trace: list[float] = []
    stockout_flags: list[bool] = []

    for t in range(periods):
        arrivals = [qty for due, qty in pipeline if due == t]
        if arrivals:
            received = sum(arrivals)
            on_hand += received
            if backorders > 0:
                fulfilled = min(on_hand, backorders)
                on_hand -= fulfilled
                backorders -= fulfilled
            pipeline = [(due, qty) for due, qty in pipeline if due != t]

        net_before_demand = on_hand + sum(q for _, q in pipeline) - backorders
        net_trace.append(net_before_demand)
        on_hand_trace.append(on_hand)

        if on_hand <= 0 and demand[t] > 0:
            stockout_flags.append(True)
        else:
            stockout_flags.append(False)

        if on_hand >= demand[t]:
            on_hand -= demand[t]
        else:
            short = demand[t] - on_hand
            backorders += short
            on_hand = 0.0

        if t % review_period == 0:
            net_inventory = on_hand + sum(q for _, q in pipeline) - backorders
            order_qty = max(order_up_to_level - net_inventory, 0.0)
            if order_qty > 0:
                pipeline.append((t + lead_time_periods, order_qty))
            order_qty_trace.append(order_qty)

    cycle_length = review_period + lead_time_periods
    cycles_without_stockout = 0
    total_cycles = 0
    for start in range(0, periods - cycle_length, cycle_length):
        window = stockout_flags[start : start + cycle_length]
        total_cycles += 1
        if not any(window):
            cycles_without_stockout += 1

    simulated_cycle_sl = (
        cycles_without_stockout / total_cycles if total_cycles else 0.0
    )
    simulated_period_sl = 1.0 - (sum(stockout_flags) / periods)

    return SimulationResult(
        periods=periods,
        mean_on_hand=float(np.mean(on_hand_trace)),
        mean_net_inventory=float(np.mean(net_trace)),
        simulated_cycle_service_level=simulated_cycle_sl,
        simulated_period_service_level=simulated_period_sl,
        stockout_periods=int(sum(stockout_flags)),
        mean_order_quantity=float(np.mean(order_qty_trace)) if order_qty_trace else 0.0,
    )


def simulate_sq_policy(
    reorder_point: float,
    order_quantity: float,
    lead_time_periods: int,
    periods: int = 10_000,
    *,
    mean_demand: float = 10.0,
    std_demand: float = 5.0,
    historical_demand: np.ndarray | None = None,
    seed: int | None = 42,
) -> SimulationResult:
    """Simulate continuous review (s, Q) with backorders."""
    if lead_time_periods < 0 or order_quantity <= 0:
        raise ValueError("invalid policy parameters")

    rng = np.random.default_rng(seed)
    demand = _sample_demand(rng, periods, mean_demand, std_demand, historical_demand)

    on_hand = reorder_point + order_quantity
    pipeline: list[tuple[int, float]] = []
    backorders = 0.0

    on_hand_trace: list[float] = []
    net_trace: list[float] = []
    order_qty_trace: list[float] = []
    stockout_flags: list[bool] = []

    for t in range(periods):
        arrivals = [qty for due, qty in pipeline if due == t]
        if arrivals:
            received = sum(arrivals)
            on_hand += received
            if backorders > 0:
                fulfilled = min(on_hand, backorders)
                on_hand -= fulfilled
                backorders -= fulfilled
            pipeline = [(due, qty) for due, qty in pipeline if due != t]

        net_inventory = on_hand + sum(qty for _, qty in pipeline) - backorders
        net_trace.append(net_inventory)
        on_hand_trace.append(on_hand)

        if on_hand <= 0 and demand[t] > 0:
            stockout_flags.append(True)
        else:
            stockout_flags.append(False)

        if on_hand >= demand[t]:
            on_hand -= demand[t]
        else:
            short = demand[t] - on_hand
            backorders += short
            on_hand = 0.0

        if net_inventory <= reorder_point:
            pipeline.append((t + lead_time_periods, order_quantity))
            order_qty_trace.append(order_quantity)

    cycle_length = max(lead_time_periods, 1)
    cycles_without_stockout = 0
    total_cycles = 0
    step = max(int(order_quantity / max(mean_demand, 1e-9)), 1)
    for start in range(0, periods - cycle_length, step):
        window = stockout_flags[start : start + cycle_length]
        if len(window) < cycle_length:
            break
        total_cycles += 1
        if not any(window):
            cycles_without_stockout += 1

    simulated_cycle_sl = (
        cycles_without_stockout / total_cycles if total_cycles else 0.0
    )
    simulated_period_sl = 1.0 - (sum(stockout_flags) / periods)

    return SimulationResult(
        periods=periods,
        mean_on_hand=float(np.mean(on_hand_trace)),
        mean_net_inventory=float(np.mean(net_trace)),
        simulated_cycle_service_level=simulated_cycle_sl,
        simulated_period_service_level=simulated_period_sl,
        stockout_periods=int(sum(stockout_flags)),
        mean_order_quantity=float(np.mean(order_qty_trace)) if order_qty_trace else 0.0,
    )
