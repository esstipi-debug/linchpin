# Excel Templates

> **Status:** Planned export layer. Core models run in Python (`src/`).

Per Vandeput (2020), Excel is best for **visualizing results** and simple what-if checks — not for Monte Carlo simulation or advanced distributions.

## Planned sheets

| Sheet | Source module | Book chapter |
|-------|---------------|--------------|
| EOQ calculator | `src/eoq.py` | Ch. 2 |
| Safety stock | `src/safety_stock.py` | Ch. 4 |
| Policy (s,Q) / (R,S) | `src/policies.py` | Ch. 5 |
| Simulation summary | `src/simulation.py` | Ch. 5.3 |

## Workflow (current)

1. Run `python examples/run_part1_part2.py --simulate`
2. Copy outputs into your own workbook, or wait for automated CSV/Excel export (roadmap)

## Reference formulas in Excel

```
EOQ:     =SQRT(2*D*k/h)
z_alpha: =NORM.S.INV(alpha)
Ss:      =NORM.S.INV(alpha)*sigma*SQRT(tau)
```

See [METHODOLOGY.md](../documentation/METHODOLOGY.md) for full notation.
