---
name: vandeput-inventory-advanced
description: >-
  Gamma demand, serial multi-echelon GSM, newsvendor, KDE/discrete PMF, and
  simulation-based safety stock optimization from Vandeput (2020) Chapters 9-13.
  Use for skewed demand, supply chain networks, perishable one-shot ordering,
  or tuning inventory parameters by Monte Carlo simulation.
---

# Vandeput Part IV: Advanced Models

Parent skill: [vandeput-inventory-optimization](../vandeput-inventory-optimization/SKILL.md)

## Gamma demand (Ch. 9)

```python
from src.distributions import select_distribution, safety_stock_gamma

fit = select_distribution(demand_array)  # gamma if skew > sigma/mu
_, ss = safety_stock_gamma(mu_x=500, std_risk=400, cycle_service_level=0.95)
```

High CV: gamma Ss >> normal Ss.

## Multi-echelon GSM (Ch. 10)

```python
from src.multi_echelon import optimize_serial_gsm, serial_gsm_cases

cases = serial_gsm_cases([4, 3, 2], review_period=1.0)  # 4 patterns
best = optimize_serial_gsm([4,3,2], 100, 25, [1,2,4], 0.95, 1.0)
# optimal risk_periods often (4, 0, 6), cost ~485
```

## Newsvendor (Ch. 11)

```python
from src.newsvendor import muffin_pmf, optimal_newsvendor_discrete

r = optimal_newsvendor_discrete(muffin_pmf(), price=6, unit_cost=2, salvage_value=1)
# Q*=4, cr=0.8, profit~6
```

## Discrete demand / KDE (Ch. 12)

```python
from src.discrete_demand import histogram_pmf, kde_pmf
pmf = kde_pmf(historical_demand)
```

## Simulation optimization (Ch. 13)

```python
from src.simulation_opt import find_best_safety_stock_smart_start

sim, start_ss = find_best_safety_stock_smart_start(
    mean_demand=100, std_demand=25, lead_time_periods=2, review_period=1,
    holding_cost_per_period=1.25, fixed_order_cost=1000, backorder_cost=50)
```

Run: `python examples/run_part4.py`

Tests: `test_distributions.py`, `test_multi_echelon.py`, `test_newsvendor.py`, `test_simulation_opt.py`
