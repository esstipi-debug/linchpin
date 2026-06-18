"""Batch analysis across all SKUs in a demand file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.cost_optimization import optimize_rs_policy
from src.data_loader import (
    ProductMetadata,
    annualize_demand,
    list_products,
    load_demand_csv,
    product_metadata,
)
from src.distributions import select_distribution
from src.eoq import compute_eoq, round_review_period_power_of_two
from src.export import write_summary_csv
from src.multi_echelon import optimize_serial_gsm
from src.policies import continuous_review_sq, periodic_review_rs


@dataclass(frozen=True)
class BatchConfig:
    holding_cost_rate: float = 0.25
    fixed_order_cost: float = 1000.0
    backorder_cost: float = 50.0
    service_level: float = 0.95
    periods_per_year: float = 52.0
    gsm_holding_costs: tuple[float, float, float] = (1.0, 2.0, 4.0)
    gsm_lead_times: tuple[int, int, int] = (4, 3, 2)


def analyze_product_row(
    data_path: Path,
    meta: ProductMetadata,
    config: BatchConfig,
) -> dict:
    """Single SKU summary row for batch export."""
    mu, sigma = meta.mean_demand_per_period, meta.demand_std_per_period
    annual_demand = annualize_demand(mu, config.periods_per_year)
    h_year = config.holding_cost_rate * meta.mean_unit_cost * config.periods_per_year
    h_period = h_year / config.periods_per_year

    eoq = compute_eoq(annual_demand, h_year, config.fixed_order_cost)
    review = round_review_period_power_of_two(eoq.review_period * config.periods_per_year)
    hist = load_demand_csv(data_path, product_id=meta.product_id).to_numpy()
    fit = select_distribution(hist)

    sq = continuous_review_sq(
        annual_demand,
        mu,
        sigma,
        h_year,
        config.fixed_order_cost,
        meta.lead_time_periods,
        config.service_level,
        config.periods_per_year,
        demand_distribution="auto",
        observed_skewness=fit.observed_skewness,
    )
    rs = periodic_review_rs(
        annual_demand,
        mu,
        sigma,
        h_year,
        config.fixed_order_cost,
        meta.lead_time_periods,
        review,
        config.service_level,
        demand_distribution="auto",
        observed_skewness=fit.observed_skewness,
    )
    best_rs = optimize_rs_policy(
        mu, sigma, meta.lead_time_periods, h_period, config.fixed_order_cost, config.backorder_cost
    )
    gsm = optimize_serial_gsm(
        list(config.gsm_lead_times),
        mu,
        sigma,
        list(config.gsm_holding_costs),
        config.service_level,
        1.0,
    )

    return {
        "product_id": meta.product_id,
        "mean_demand": mu,
        "demand_std": sigma,
        "unit_cost": meta.mean_unit_cost,
        "lead_time_periods": meta.lead_time_periods,
        "annual_demand": annual_demand,
        "distribution": fit.recommended.value,
        "eoq_Q": eoq.order_quantity,
        "sq_Q": sq.order_quantity,
        "sq_s": sq.reorder_point,
        "sq_Ss": sq.safety_stock.safety_stock,
        "rs_R": rs.review_period,
        "rs_S": rs.order_up_to_level,
        "rs_Ss": rs.safety_stock.safety_stock,
        "optimal_R": best_rs.review_period,
        "optimal_cost_period": best_rs.cost.total,
        "gsm_holding_cost": gsm.total_holding_cost,
    }


def run_batch_analysis(
    data_path: Path | str,
    output_csv: Path | str,
    config: BatchConfig | None = None,
) -> pd.DataFrame:
    """Analyze every product_id in CSV; write summary CSV."""
    config = config or BatchConfig()
    path = Path(data_path)
    rows = []
    for pid in list_products(path):
        meta = product_metadata(path, pid, periods_per_year=config.periods_per_year)
        rows.append(analyze_product_row(path, meta, config))
    df = pd.DataFrame(rows)
    write_summary_csv(rows, output_csv)
    return df
