"""End-to-end: activity-based cost-to-serve + working-capital -> CFO deck (gap #3).

Allocates the true cost of serving each channel (product + fulfillment + returns +
overhead), ranks them into the profitability "whale curve", layers on the cash-to-cash
cycle and the cash a few days of cycle improvement would free, and writes the CFO deck.
Numbers here are illustrative channel activity; in an engagement they come from the
order/sales data. ASCII-only output (Windows cp1252 safe).

Usage:
    python examples/run_cost_to_serve.py
    python examples/run_cost_to_serve.py --out deliverables/cost-to-serve
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.cost_to_serve_deliverable import build as build_deck  # noqa: E402
from scm_agent.knowledge import KnowledgeBase  # noqa: E402
from src.cost_to_serve import SegmentActivity, ServiceCostRates, analyze_portfolio  # noqa: E402
from src.working_capital import cash_release_plan, working_capital  # noqa: E402

# Illustrative channel activity (segment, revenue, units, orders, cogs, returns, freight, overhead).
_CHANNELS = (
    SegmentActivity("Enterprise", 500_000.0, 20_000.0, 200.0, 300_000.0, 100.0, 8_000.0, 15_000.0),
    SegmentActivity("Retail", 300_000.0, 30_000.0, 1_500.0, 195_000.0, 600.0, 12_000.0, 10_000.0),
    SegmentActivity("DTC", 180_000.0, 18_000.0, 4_000.0, 108_000.0, 1_200.0, 14_000.0, 9_000.0),
    SegmentActivity("Marketplace", 120_000.0, 25_000.0, 2_000.0, 84_000.0, 800.0, 18_000.0, 8_000.0),
)
_RATES = ServiceCostRates(cost_per_order=6.0, cost_per_unit_shipped=0.8, return_handling_per_unit=10.0)


def _citations(limit: int = 3) -> tuple[str, ...]:
    kb = KnowledgeBase()
    hits = kb.search("cost to serve profitability cash to cash working capital", graph="books", limit=limit)
    cites = []
    for c in hits:
        text = c.label + (f" - {c.source}" if c.source else "") + (f", {c.location}" if c.location else "")
        cites.append(text)
    return tuple(cites) or (
        "Christopher, Logistics & Supply Chain Management - cost-to-serve / Stobachoff curve",
        "SCOR Digital Standard - cash-to-cash (AM.1.1)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run cost-to-serve + working-capital and write the CFO deck.")
    parser.add_argument("--client", default="Demo Client")
    parser.add_argument("--out", default="deliverables/cost-to-serve")
    args = parser.parse_args()

    portfolio = analyze_portfolio(list(_CHANNELS), _RATES)

    total_cogs = sum(c.cogs for c in _CHANNELS)
    wc = working_capital(revenue=portfolio.total_revenue, cogs=total_cogs, dio=55.0, dso=42.0, dpo=35.0)
    # Cash freed by the S&OP inventory plan (8 DIO days) + a receivables push (4 DSO days).
    cr = cash_release_plan(revenue=portfolio.total_revenue, cogs=total_cogs, dio_days=8.0, dso_days=4.0)

    print(f"\n=== Cost-to-Serve & Working Capital: {args.client} ===")
    print(f"  revenue {portfolio.total_revenue:,.0f} across {len(portfolio.segments)} channels; "
          f"net-to-serve margin {portfolio.overall_net_margin * 100:.1f}%")
    print("\n  Profitability (ranked best -> worst):")
    for s in portfolio.segments:
        flag = "  <= LOSS" if s.net_to_serve < 0 else ""
        print(f"   {s.segment:<12} rev {s.revenue:>10,.0f}  net-to-serve {s.net_to_serve:>10,.0f} "
              f"({s.net_margin_pct * 100:>5.1f}%)  cost-to-serve {s.cost_to_serve_pct * 100:>4.1f}%{flag}")
    print(f"\n  Whale curve: profitable segments earn {portfolio.peak_profit:,.0f}; "
          f"loss tail erodes {portfolio.profit_erosion:,.0f} -> net {portfolio.total_net_to_serve:,.0f}")
    print(f"\n  Working capital: cash-to-cash {wc.cash_conversion_cycle:.0f} days, "
          f"net working capital {wc.net_working_capital:,.0f}")
    print(f"  Cash-release plan frees {cr.total_cash_released:,.0f}:")
    for r in cr.levers:
        print(f"    {r.lever:<20} -{r.days_improved:.0f} days -> {r.cash_released:,.0f}")

    deck = build_deck(portfolio, working_cap=wc, cash_release=cr,
                      client=args.client, prepared="2026-06-23", citations=_citations())
    paths = deck.write_all(args.out)
    print("\n  Deliverable written:")
    for kind, path in paths.items():
        print(f"    {kind:8}: {path}")


if __name__ == "__main__":
    main()
