"""Valuation tests: the neutral judge, the baseline mirror, the value table,
agreement@1 and the parallel runner (spec sec 5, sec 9, sec 12.4)."""

import os
import subprocess
import sys
from pathlib import Path

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


# -- baseline equivalence vs the real job (spec sec 5) ----------------------------

PORTFOLIO = "data/sample_demand_portfolio.csv"   # git-tracked testbed


def test_baseline_plan_matches_inventory_optimization_job():
    """baseline_plan() must mirror jobs/inventory_optimization.py's policy when
    fed the job's own engine inputs: same classic-EOQ Q, same SL 0.95."""
    from jobs import intake
    from jobs.inventory_optimization import run as run_inventory
    from src.forecasting import forecast_demand
    from src.sources import DataFrameDemandSource

    demand = intake.prepare(PORTFOLIO)
    report = run_inventory(demand, service_level=0.95, holding_rate=0.25, order_cost=75.0)
    rec = next(r for r in report.recommendations
               if r.product_id == "SKU-A" and not r.intermittent)
    source = DataFrameDemandSource(demand, periods_per_year=52.0)
    ei = forecast_demand(source.demand_series("SKU-A")).to_engine_inputs(periods_per_year=52.0)
    inp = build_inputs(
        sku="SKU-A", annual_demand=ei["annual_demand"],
        mean_weekly=ei["mean_demand_per_period"],
        std_weekly=ei["demand_std_per_period"],
        lead_time_weeks=rec.lead_periods, unit_cost=rec.unit_cost, config=HatConfig())
    base = baseline_plan(inp)
    assert base.order_quantity == pytest.approx(rec.order_quantity, rel=1e-9)
    assert base.service_level == rec.service_level == 0.95


# -- value table + agreement on the tracked sample CSV (spec sec 9) ---------------


def _value_rows(payload):
    from src.hat_council import settle, tension_map, value_row
    out = []
    for inp in payload["inputs"]:
        tmap = tension_map(inp)
        out.append(value_row(inp, tmap, settle(inp, payload["weights"])))
    return tuple(out)


def test_value_table_reproducible_on_sample_portfolio():
    from jobs import hats_job
    rows1 = _value_rows(hats_job.prepare(PORTFOLIO))
    rows2 = _value_rows(hats_job.prepare(PORTFOLIO))
    assert rows1 == rows2                                  # same inputs -> identical values
    assert len(rows1) == 8                                 # the 8 testbed SKUs
    for r in rows1:
        assert r.delta_usd == pytest.approx(r.c_baseline - r.c_n5)


def test_agreement_at_1_on_sample_portfolio_in_unit_interval():
    from jobs import hats_job
    from src.hat_council import agreement_at_1, settle, tension_map, top1_by_judge
    payload = hats_job.prepare(PORTFOLIO)
    pairs = []
    for inp in payload["inputs"]:
        tmap = tension_map(inp)
        pairs.append((top1_by_judge(inp, tmap), settle(inp, payload["weights"]).chosen))
    assert 0.0 <= agreement_at_1(pairs) <= 1.0


# -- the runner: ASCII, sections, TOTAL, determinism (spec sec 8, acceptance #1) --

REPO = Path(__file__).resolve().parents[1]


def _run_runner(*argv):
    env = {**os.environ, "PYTHONPATH": "."}
    return subprocess.run([sys.executable, "examples/run_hats.py", *argv],
                          cwd=REPO, env=env, capture_output=True, timeout=300)


def test_runner_single_sku_ascii_and_sections():
    proc = _run_runner("--sku", "SKU-A")
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    out = proc.stdout.decode("ascii")            # raises on ANY non-ASCII byte
    assert "== NIVEL 4: MAPA DE TENSION ==" in out
    assert "== NIVEL 5: SETTLEMENT ==" in out
    assert "== VALOR ==" in out
    assert "politica del operador" in out
    assert "(assumed)" in out                    # D8 default breaks on the sample CSV


def test_runner_all_prints_total_agreement_and_is_deterministic():
    p1 = _run_runner("--all")
    p2 = _run_runner("--all")
    assert p1.returncode == 0, p1.stderr.decode(errors="replace")
    out = p1.stdout.decode("ascii")
    assert "TOTAL" in out and "agreement@1" in out
    assert "Delta $ = a - c" in out
    assert p1.stdout == p2.stdout                # spec sec 6: identical bytes


def test_runner_cfo_weight_collapse_visible_in_acta():
    proc = _run_runner("--sku", "SKU-A", "--weights", "cfo=1")
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    assert "cfo cede 0.00" in proc.stdout.decode("ascii")   # acceptance #3
