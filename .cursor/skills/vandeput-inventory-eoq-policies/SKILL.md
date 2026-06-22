---
name: vandeput-inventory-eoq-policies
description: >-
  EOQ, safety stock, (s,Q) and (R,S) policies, and discrete simulation with
  backorders from Vandeput (2020) Chapters 2-5. Use when calculating economic
  order quantity, reorder points, order-up-to levels, or validating policies
  via simulation in the linchpin repo.
---

# Vandeput Part I–II: EOQ & Policies

Parent skill: [vandeput-inventory-optimization](../vandeput-inventory-optimization/SKILL.md)

## When to use

- Fixed order cost + holding cost → **EOQ**
- Continuous review → **(s, Q)**
- Periodic review → **(R, S)**
- Validate cycle service level → **simulation**

## Code

```python
from src.eoq import compute_eoq
from src.policies import continuous_review_sq, periodic_review_rs
from src.simulation import simulate_rs_policy, simulate_sq_policy

eoq = compute_eoq(annual_demand=1000, holding_cost=1.75, order_cost=50)
sq = continuous_review_sq(annual_demand=5200, mean_demand_per_period=100,
                          demand_std_per_period=25, holding_cost_per_year=65,
                          fixed_order_cost=50, mean_lead_time=1, cycle_service_level=0.95)
sim = simulate_rs_policy(sq.order_up_to_level, lead_time_periods=1,
                         review_period=1, mean_demand=100, std_demand=25)
```

## Rules

- Round review period to power of 2 when book requires (§3.2)
- S >> mean on-hand for long lead times — warn users
- Simulation: backorders only; lost sales need different logic (§5.3.2)

## Tests

`tests/test_eoq.py`, `test_safety_stock.py`, `test_simulation.py`

Run: `python examples/run_part1_part2.py --simulate`
