"""Demand over risk-period — Vandeput (2020), Chapters 5–6."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskPeriodStats:
    """Demand statistics aggregated over the inventory risk period."""

    mean_demand: float
    demand_std: float
    risk_periods: float
    mean_lead_time: float
    review_period: float


def demand_over_risk_period(
    mean_demand_per_period: float,
    demand_std_per_period: float,
    mean_lead_time: float,
    lead_time_std: float = 0.0,
    review_period: float = 0.0,
) -> RiskPeriodStats:
    """
    Combined stochastic demand and lead time (eq. 6.4–6.5).

    sigma_x = sqrt(tau * sigma_d^2 + sigma_L^2 * mu_d^2)
    where tau = L for (s,Q) or R+L for (R,S).
    """
    if mean_demand_per_period < 0 or demand_std_per_period < 0:
        raise ValueError("demand parameters must be >= 0")
    if mean_lead_time < 0 or lead_time_std < 0 or review_period < 0:
        raise ValueError("lead time / review parameters must be >= 0")

    tau = mean_lead_time + review_period
    mu_x = mean_demand_per_period * tau
    variance = tau * (demand_std_per_period**2) + (lead_time_std**2) * (mean_demand_per_period**2)
    sigma_x = math.sqrt(max(variance, 0.0))

    return RiskPeriodStats(
        mean_demand=mu_x,
        demand_std=sigma_x,
        risk_periods=tau,
        mean_lead_time=mean_lead_time,
        review_period=review_period,
    )
