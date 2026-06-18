# Case Studies & Exercises

Worked examples aligned with **Vandeput (2020)**, *Inventory Optimization: Models and Simulations*.

> Previous marketing case studies in this file were placeholders. Use the exercises below with the Python implementation.

---

## Exercise 1 — EOQ (§2.2.4)

**Given:** D = 1000 units/year, k = 50 €/order, h = 1.75 €/unit/year

```bash
python -c "
from src.eoq import compute_eoq
r = compute_eoq(1000, 1.75, 50)
print(f'Q*={r.order_quantity:.0f}, C*={r.optimal_total_cost:.0f}')
"
```

**Expected:** Q* ≈ 239, C* ≈ 418

---

## Exercise 2 — Safety stock (Table 4.1)

**Given:** μ_d = 100, σ_d = 25, α = 95%

```bash
python -c "
from src.safety_stock import safety_stock, service_level_factor
print('z =', round(service_level_factor(0.95), 2))
print('Ss =', round(safety_stock(25, 0.95, 1).safety_stock))
print('Inventory =', round(100 + safety_stock(25, 0.95, 1).safety_stock))
"
```

**Expected:** z ≈ 1.64, inventory ≈ 141

---

## Exercise 3 — (R,S) vs average on-hand (§3.3, §5.3)

Compare order-up-to **S** with simulated mean on-hand for long lead time:

```bash
python examples/run_part1_part2.py --product SKU-A --lead-time 4 --simulate
```

Observe: **S** is much higher than mean on-hand — do not treat S as “target stock on shelf”.

---

## Exercise 4 — Your SKU

Replace `data/sample_demand.csv` with your weekly/monthly demand history and run:

```bash
python examples/run_part1_part2.py --product YOUR-SKU --simulate
```

Calibrate `--holding-cost`, `--order-cost`, and `--lead-time` from finance and supplier data (§2.1, §3.1).

---

## Exercise 5 — Newsvendor muffins (§11.3)

```bash
python -c "
from src.newsvendor import muffin_pmf, optimal_newsvendor_discrete
r = optimal_newsvendor_discrete(muffin_pmf(), price=6, unit_cost=2, salvage_value=1)
print(f'Q*={r.optimal_quantity:.0f}, profit={r.expected_profit:.2f}')
"
```

**Expected:** Q* = 4, profit ≈ 6.00 EUR

---

## Exercise 6 — Serial GSM (§10.4)

```bash
python -c "
from src.multi_echelon import optimize_serial_gsm
b = optimize_serial_gsm([4,3,2], 100, 25, [1,2,4], 0.95, 1.0)
print(b.risk_periods, round(b.total_holding_cost))
"
```

**Expected:** (4, 0, 6), cost ≈ 485

---

## Further reading in the book

| Scenario | Chapter |
|----------|---------|
| Volume discounts | §2.5.3 |
| Fill rate vs cycle SL | Ch. 7 |
| Optimal service level | Ch. 8 |
| Non-normal demand | Ch. 9 |
| Multi-echelon network | Ch. 10 |
| Newsvendor / perishables | Ch. 11 |

Official code snippets: [supchains.com/resources-invopt](https://supchains.com/resources-invopt)
