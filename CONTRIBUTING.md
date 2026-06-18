# Contributing

Thank you for improving this implementation of **Vandeput (2020)** inventory models.

## Setup

```bash
git clone https://github.com/esstipi-debug/supply-chain-optimization.git
cd supply-chain-optimization
python -m venv venv
# Windows: venv\Scripts\activate
pip install -r requirements.txt
pytest
```

## What to contribute

| Area | Examples |
|------|----------|
| Models | New book sections, bug fixes in formulas |
| Tests | Numeric examples from the book (§ references) |
| Examples | New workflows, plots |
| Docs | FAQ, METHODOLOGY, case studies |
| Export | Excel/Power BI dataset improvements |

## Workflow

1. Fork and branch: `feature/short-description`
2. Match existing style: dataclasses, type hints, minimal scope
3. Add tests for book numeric examples when possible
4. Run `pytest` before PR
5. Update CHANGELOG.md for user-visible changes

## PR checklist

- [ ] Tests pass (`pytest`)
- [ ] No fake marketing claims in docs
- [ ] Book section referenced in docstrings where relevant
- [ ] CHANGELOG updated if behavior changed

## Code style

- PEP 8, type hints on public functions
- Pure functions in `src/`; CLI in `examples/`
- Do not commit secrets, `.env`, or local `output/`

## Questions

Open a GitHub issue with reproduction steps and Python version.
