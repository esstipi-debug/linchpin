# Frequently Asked Questions

Based on **Vandeput (2020)**, *Inventory Optimization: Models and Simulations*.

---

## Getting started

### Do I need Excel or Power BI?
No. Core models run in **Python**. Excel (`.xlsx`) and Power BI (CSV dataset) are optional export layers.

### How do I run the models?
```bash
pip install -r requirements.txt
python examples/run_part1_part2.py --simulate
python examples/run_batch.py          # all SKUs
python examples/run_complete.py --simulate
pytest
```

### Which Python version?
3.10+. CI tests 3.11, 3.12, 3.13.

---

## Data

### CSV format
```csv
date,product_id,quantity,unit_cost,lead_time_days
2024-01-01,SKU-A,100,50,7
```

- `unit_cost` → holding cost via rate (default 25%/year)
- `lead_time_days` → converted to periods (52 weeks/year)

### How much history?
Book examples use 1–2 years weekly data. More history improves σ estimates; 52+ periods minimum recommended.

---

## Models

### Normal vs gamma demand?
Use `distribution="auto"` in policies (default in batch). Gamma applies when skewness > σ/μ (Ch. 9).

### Fill rate vs cycle service level?
Different metrics (Ch. 7). High fill rate β can coexist with low cycle SL α. Report both.

### S vs mean on-hand?
Order-up-to **S** is not average on-hand (§3.3). Simulation shows the gap.

### Lost sales vs backorders?
Simulation supports `lost_sales=True` on `(R,S)` and `(s,Q)`. Default is backorders.

---

## Exports

| Output | Command |
|--------|---------|
| CSV summary | `run_complete.py --export output/summary.csv` |
| Excel | `run_complete.py --excel excel-templates/out.xlsx` |
| Power BI | `build_powerbi_dataset.py --simulate` |
| Chart | `plot_inventory.py --product SKU-A` |

---

## Troubleshooting

### `ModuleNotFoundError: src`
Set `PYTHONPATH=.` or use `pytest.ini` (included).

### Windows Unicode errors
Avoid special characters in print output; repo uses ASCII in examples.

### Tests fail on scipy/numpy
Use Python 3.11+ with `pip install -r requirements.txt`.

---

## Contributing & support

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [Getting Started](GETTING_STARTED.md)
- [Methodology](METHODOLOGY.md)
- GitHub Issues on the repository

Book reference code: [supchains.com/resources-invopt](https://supchains.com/resources-invopt) (password `SupChains-IO`).
