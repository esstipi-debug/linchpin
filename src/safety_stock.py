"""Safety stock under normal demand — Vandeput (2020), Chapter 4."""

from __future__ import annotations

from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True)
class SafetyStockResult:
    """Safety stock for a risk period of tau periods."""

    safety_stock: float
    service_level_factor: float
    cycle_service_level: float
    risk_periods: float


def service_level_factor(cycle_service_level: float) -> float:
    """z_alpha = Phi^{-1}(alpha) (Section 4.2.4)."""
    if not 0 < cycle_service_level < 1:
        raise ValueError("cycle_service_level must be between 0 and 1 (exclusive)")
    return float(norm.ppf(cycle_service_level))


def safety_stock(
    demand_std_per_period: float,
    cycle_service_level: float,
    risk_periods: float = 1.0,
) -> SafetyStockResult:
    """
    Safety stock Ss = z_alpha * sigma_d * sqrt(tau) (eq. 4.3).

    risk_periods (tau):
        Lead time L for (s, Q); lead time + review period (R + L) for (R, S).
    """
    if demand_std_per_period < 0:
        raise ValueError("demand_std_per_period must be >= 0")
    if risk_periods <= 0:
        raise ValueError("risk_periods must be > 0")

    z_alpha = service_level_factor(cycle_service_level)
    ss = z_alpha * demand_std_per_period * (risk_periods**0.5)

    return SafetyStockResult(
        safety_stock=ss,
        service_level_factor=z_alpha,
        cycle_service_level=cycle_service_level,
        risk_periods=risk_periods,
    )


def inventory_for_service_level(
    mean_demand_per_period: float,
    demand_std_per_period: float,
    cycle_service_level: float,
) -> float:
    """Total inventory at period start: mu_d + z_alpha * sigma_d (eq. 4.1)."""
    z_alpha = service_level_factor(cycle_service_level)
    return mean_demand_per_period + z_alpha * demand_std_per_period


def cycle_service_level_from_inventory(
    inventory_level: float,
    mean_demand_per_period: float,
    demand_std_per_period: float,
) -> float:
    """alpha = F_N(inv; mu_d, sigma_d)."""
    if demand_std_per_period == 0:
        return 1.0 if inventory_level >= mean_demand_per_period else 0.0
    return float(norm.cdf(inventory_level, loc=mean_demand_per_period, scale=demand_std_per_period))
