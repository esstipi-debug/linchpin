---
name: vandeput-inventory-service-cost
description: >-
  Fill rate, normal loss function, stochastic lead time, and cost/service level
  optimization for (R,S) and (s,Q) from Vandeput (2020) Chapters 6-8. Use when
  target fill rate differs from cycle service level, optimizing review period R,
  or computing optimal alpha star from holding and backorder costs.
---

# Vandeput Part III: Service & Cost

Parent skill: [vandeput-inventory-optimization](../vandeput-inventory-optimization/SKILL.md)

## Fill rate vs cycle SL (Ch. 7)

- **β (fill rate):** fraction of demand served from stock
- **α (cycle SL):** prob. no stockout in one replenishment cycle
- High β can occur with low α — always report both

```python
from src.fill_rate import safety_stock_for_fill_rate, fill_rate_from_inventory

fr = safety_stock_for_fill_rate(cycle_demand=250, demand_std_risk=30, target_fill_rate=0.98)
inv = 250 + fr.safety_stock  # ~270
check = fill_rate_from_inventory(inv, 250, 250, 30)  # beta~98%, alpha~73%
```

## Cost optimization (Ch. 8)

```python
from src.cost_optimization import optimize_rs_policy, optimize_sq_policy

best_rs = optimize_rs_policy(mean_demand_per_period=100, demand_std_per_period=25,
    mean_lead_time=1, holding_cost_per_period=2, fixed_order_cost=1000,
    backorder_cost=50)
# alpha* = 1 - h*R/b
```

## Stochastic lead time (Ch. 6)

Pass `lead_time_std` to policies and optimizers; uses eq. 6.4–6.5 via `demand_over_risk_period`.

## Pitfall

`inverse_standard_loss`: polynomial coefficients are **not** reversed for `np.polyval`.

Run: `python examples/run_part3.py` | Tests: `test_fill_rate.py`, `test_cost_optimization.py`
