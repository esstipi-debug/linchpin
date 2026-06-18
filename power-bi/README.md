# Power BI Dashboards

> **Status:** Planned. Connect to Python outputs or `data/sample_demand.csv`.

Vandeput (2020) uses Python for computation; dashboards are a **reporting layer** on top of model outputs.

## Planned visuals

| Page | Metrics | Book reference |
|------|---------|----------------|
| Inventory health | On-hand vs Ss / Cs zones | Table 5.2, §5.2 |
| Policy parameters | Q, s, S, R, L | Ch. 5 |
| Simulation | Cycle SL vs target α | §5.3, Table 5.3 |
| EOQ costs | Holding vs transaction | §2.2 |

## Current workaround

Export results from:

```bash
python examples/run_part1_part2.py --simulate > results.txt
```

Or load `data/sample_demand.csv` directly in Power BI for demand history charts.

Fill rate and forecast accuracy belong to **Ch. 7** and the companion forecasting book — not yet in this repo.
