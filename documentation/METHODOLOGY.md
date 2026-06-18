# Methodology

Implementation reference for **Nicolas Vandeput**, *Inventory Optimization: Models and Simulations* (De Gruyter, 2020).

---

## Philosophy

> All models are wrong, but some are helpful. — George Box

The book progresses from **deterministic** models (Part I) to **stochastic** models with **simulation** validation (Part II+). This repo follows the same path: equations first, then simulate to check assumptions.

**Tools in the book:**

- **Python** — computation, simulation, optimization
- **Excel / Power BI** — export layers (`excel_export.py`, `powerbi_export.py`)

---

## Part I — Deterministic supply chains

### Chapter 1 — Inventory policies

| Policy | Notation | When to order | How much |
|--------|----------|---------------|----------|
| Continuous review | `(s, Q)` | When net inventory ≤ s | Fixed Q |
| Periodic review | `(R, S)` | Every R periods | Up to level S |
| Periodic + fixed Q | `(R, s, Q)` | Every R if inventory ≤ s | Fixed Q |

**Terminology warning (§1.5):** “reorder point”, “stock target”, and “ROP” mean different things across vendors. Always define terms explicitly.

### Chapter 2 — EOQ

**Cost model** (eq. 2.1):

```
C(Q) = k·D/Q + h·Q/2
```

**Optimum** (eq. 2.2–2.3):

```
Q* = √(2kD/h)
C* = √(2kDh)
```

At Q*, holding cost equals transaction cost.

**Sensitivity (§2.4):** mis-estimating k or h by 2× changes Q* by ~41% but total cost by only ~6%.

**Implementation:** `src/eoq.py`

### Chapter 3 — Lead time and review period

Deterministic reorder point:

```
s = d·L          (continuous review, no safety stock yet)
S = d·L + d·R    (periodic review)
```

**Power-of-2 review period (§3.2.1):** round R to 2^k × base period; worst-case cost penalty ~6%.

**Confusion curse (§3.3):** for `(R,S)` with long L, average on-hand ≪ S.

---

## Part II — Stochastic supply chains

### Chapter 4 — Safety stock

**Cycle service level α:** probability of no stockout during an order cycle (not the same as fill rate — Ch. 7).

**Normal demand** over τ periods (eq. 4.3):

```
Ss = z_α · σ_d · √τ
z_α = Φ⁻¹(α)
```

Use **forecast error σ_e** instead of σ_d when using forecasts (§4.2.5).

**Demand aggregation:** over τ independent periods, σ scales with √τ.

**Implementation:** `src/safety_stock.py`

### Chapter 5 — Policies + simulation

#### (s, Q)

```
Ss = z_α · σ_d · √L
s  = d·L + Ss
Q  = Q*   (from EOQ)
```

Risk period τ = L.

#### (R, S)

```
Ss = z_α · σ_d · √(R + L)
S  = d·L + d·R + Ss
```

Risk period τ = R + L (blind spot between reviews — §5.1.2).

**Expected on-hand** (theoretical):

| Policy | Cycle stock | Safety stock |
|--------|-------------|--------------|
| (s,Q) | Q/2 | Ss |
| (R,S) | d·R/2 | Ss |

**Inventory zones (Table 5.2):**

| Zone | Condition |
|------|-----------|
| Shortage | on-hand ≤ 0 |
| Under-stock | 0 < on-hand < Ss |
| Target | Ss ≤ on-hand ≤ Cs + Ss |
| Over-stock | above cycle + safety + in-transit |

**Simulation (§5.3):** discrete-period model with backorders; validates cycle service level vs theory.

**Implementation:** `src/policies.py`, `src/simulation.py`

---

## Part III — Advanced stochastic models (implemented)

### Chapter 6 — Stochastic lead time

Combined demand over risk period (eq. 6.4–6.5):

```
sigma_x = sqrt(tau * sigma_d^2 + sigma_L^2 * mu_d^2)
mu_x = mu_d * tau        (tau = L or R+L)
```

**Implementation:** `src/risk_period.py`

### Chapter 7 — Fill rate

Fill rate beta = 1 - Us/dc, where Us uses the normal loss function:

```
L_N(x) = phi(x) - x*(1 - Phi(x))
beta = 1 - (sigma_x/dc) * L_N(Ss/sigma_x)
```

To target fill rate beta, invert via `inverse_standard_loss(dc*(1-beta)/sigma_x)`.

**Key insight (§7.4):** fill rate depends on cycle stock + safety stock; cycle service level only on safety stock. Do not use cycle SL as KPI when order cycles are long.

**Implementation:** `src/fill_rate.py`

### Chapter 8 — Cost optimization

**(R,S) cost per period (eq. 8.2):**

```
C = h(dR/2 + z*sigma_x) + k/R + b*sigma_x*L_N(z)/R
alpha* = 1 - hR/b                    (eq. 8.3)
```

**(s,Q) cost per year:**

```
C = h(Q/2 + z*sigma_x) + kD/Q + b*sigma_x*L_N(z)*D/Q
alpha* = 1 - hQ/(bD)                 (eq. 8.4)
Q* = sqrt(2(k + b*Us)D / h)          (eq. 8.5, iterate with z*)
```

**Implementation:** `src/cost_optimization.py`, `examples/run_part3.py`

---

## Assumptions (Part I–II)

| Assumption | Limitation |
|------------|------------|
| Independent periods | Auto-correlation not modeled; extend with time-series if needed |
| Backorders default | Use `lost_sales=True` in simulation for retail/perishable cases |
| Single-echelon default | GSM serial chain in `multi_echelon.py`; not general networks |
| Forecast σ_e | Use companion forecasting book; pass σ manually today |

---

## Glossary (selected)

| Term | Definition |
|------|------------|
| Cycle stock | Inventory to cover expected demand in a cycle |
| Safety stock | Buffer against demand/supply variation |
| Net inventory | On-hand + in-transit − backorders |
| Risk period | Max wait until next replenishment (L or R+L) |
| Fill rate | Fraction of demand served from stock (Ch. 7) |
| Cycle service level | Prob. no stockout in one replenishment cycle |

Full glossary: book pp. 283+.

---

## Planned (Part III–IV)

| Chapter | Topic | Module |
|---------|-------|--------|
| 6 | Stochastic lead time | `src/risk_period.py` ✅ |
| 7 | Fill rate | `src/fill_rate.py` ✅ |
| 8 | Cost / service optimization | `src/cost_optimization.py` ✅ |
| 9 | Beyond normality (gamma) | `src/distributions.py` ✅ |
| 10 | Multi-echelon (GSM) | `src/multi_echelon.py` ✅ |
| 11 | Newsvendor | `src/newsvendor.py` ✅ |
| 12 | Histograms / KDE | `src/discrete_demand.py` ✅ |
| 13 | Simulation optimization | `src/simulation_opt.py` ✅ |

---

## References

- Vandeput, N. (2020). *Inventory Optimization: Models and Simulations*. De Gruyter.
- Silver, E., Pyke, D., Thomas, D. — classic inventory reference cited in the book.
- Harris, F. W. (1913) — original EOQ.
