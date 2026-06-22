---
name: vandeput-inventory-optimization
description: >-
  Implements inventory models from Nicolas Vandeput (2020) Inventory Optimization
  Models and Simulations using the linchpin Python repo. Covers
  EOQ, safety stock, (s,Q)/(R,S) policies, simulation, fill rate, cost optimization,
  gamma demand, multi-echelon GSM, newsvendor, KDE/discrete PMF, and simulation
  optimization. Use when working on this repo, Vandeput book examples, safety stock,
  reorder policies, fill rate vs cycle service level, or inventory simulation.
---

# Vandeput Inventory Optimization

**Source of truth:** Vandeput, N. (2020). *Inventory Optimization: Models and Simulations*. De Gruyter.

**Repo:** `linchpin` — Python 3.10+, numpy/pandas/scipy/pytest.

## Quick workflow

1. Read demand: `src/data_loader.py` → CSV `date,product_id,quantity,...`
2. Pick model by chapter (see [modules.md](modules.md))
3. Run example: `examples/run_part1_part2.py`, `run_part3.py`, `run_part4.py`
4. Validate: `pytest` (37 tests, book numeric examples)

```bash
pip install -r requirements.txt
python examples/run_part1_part2.py --simulate
python examples/run_part3.py
python examples/run_part4.py
pytest
```

Windows: use `Python313` if venv lacks scipy; set `$env:PYTHONPATH="."`.

## Decision tree

| Question | Module | Ch. |
|----------|--------|-----|
| Order quantity Q*? | `src/eoq.py` | 2 |
| Reorder point / S level? | `src/policies.py`, `src/safety_stock.py` | 4–5 |
| Stochastic lead time? | `src/risk_period.py` | 6 |
| Fill rate β vs cycle SL α? | `src/fill_rate.py` | 7 |
| Optimal service level / R? | `src/cost_optimization.py` | 8 |
| Non-normal / skewed demand? | `src/distributions.py` | 9 |
| Serial multi-echelon SS? | `src/multi_echelon.py` | 10 |
| One-shot perishable order? | `src/newsvendor.py` | 11 |
| Discrete demand from history? | `src/discrete_demand.py` | 12 |
| Tune SS by simulation? | `src/simulation_opt.py` | 13 |

## Key conventions

- **Net inventory** = on-hand + in-transit − backorders (simulation uses backorders, not lost sales)
- **Risk period τ:** `(s,Q)` → τ=L; `(R,S)` → τ=R+L
- **Ss** = z·σ_d·√τ (normal) or gamma ppf (skewed demand)
- **S is not average on-hand** — do not treat order-up-to as shelf target
- **Fill rate ≠ cycle service level** — high β can coexist with low α (§7.3.1)

## Book-aligned examples (tests)

| Example | Expected | Test file |
|---------|----------|-----------|
| EOQ §2.2.4 D=1000,k=50,h=1.75 | Q*≈239, C*≈418 | `test_eoq.py` |
| Bakery fill rate §7.3 inv=270 | Us≈4.53, β≈98% | `test_fill_rate.py` |
| Gamma high CV μ=500,σ=400 | Ss≈785 | `test_distributions.py` |
| GSM serial L=[4,3,2] | optimal (4,0,6), cost≈485 | `test_multi_echelon.py` |
| Muffins newsvendor | Q*=4, profit≈6 | `test_newsvendor.py` |

## Implementation pitfalls (this repo)

- `inverse_standard_loss`: use `np.polyval(coefficients, log(target))` **without** reversing coeffs
- Windows console: avoid Unicode `≈` in prints
- Newsvendor profit: `P(Q) = p·E[S] − c·Q + v·E[(Q−D)+]` (not double-count cu on shortage)
- Newsvendor discrete Q*: smallest Q with CDF(Q) ≥ cu/(cu+co)
- GSM optimal case is often `(4,0,6)` not all-downstream `(0,0,10)` for h=[1,2,4]

## When extending

- Match existing dataclass + pure-function style in `src/`
- Add test with book numeric example before documenting
- Update `README.md`, `documentation/METHODOLOGY.md`, `CHANGELOG.md`
- Do not claim ARIMA/Prophet/Excel templates unless implemented

## References

- Formulas & symbols: [formulas.md](formulas.md)
- Module map & API: [modules.md](modules.md)
- Official book code: supchains.com/resources-invopt (password `SupChains-IO`)
