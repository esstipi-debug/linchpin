"""Compose a CFO-lens deck from the cost-to-serve + working-capital analysis (gap #3).

Bridges `src.cost_to_serve` (segment profitability + the whale curve) and
`src.working_capital` (cash-to-cash + cash-release) into the client deliverable: which
segments to fix or fire, how much profit the loss-making tail erodes, the working
capital tied up, and the cash a few days of cycle improvement would free. The cash lens
is optional - the deck degrades to a pure profitability review when it is absent.
Additive - a caller opts in.
"""
from __future__ import annotations

from collections.abc import Sequence

from src.cost_to_serve import CostToServePortfolio
from src.deliverable import DataSource, Deliverable, Finding, Kpi
from src.working_capital import CashReleasePlan, WorkingCapital

_RESIDUAL = (
    "Re-pricing, customer renegotiation, and segment-exit decisions are commercial calls, "
    "and the cash-release targets need finance sign-off. Risk if skipped: known loss-makers "
    "keep draining margin and cash stays locked in the cycle."
)


def build(
    portfolio: CostToServePortfolio,
    *,
    working_cap: WorkingCapital | None = None,
    cash_release: CashReleasePlan | None = None,
    client: str = "Client",
    prepared: str = "",
    citations: Sequence[str] = (),
    confidence: float = 0.85,
) -> Deliverable:
    """Build the cost-to-serve / working-capital deck from a portfolio (+ optional cash lens)."""
    has_cash = cash_release is not None and cash_release.total_cash_released > 0

    summary = (
        f"Net-to-serve margin {portfolio.overall_net_margin * 100:.0f}% on "
        f"{portfolio.total_revenue:,.0f} revenue across {len(portfolio.segments)} segments; "
        f"{len(portfolio.loss_making)} loss-making."
    )
    if has_cash:
        summary += f" Cash-release opportunity: {cash_release.total_cash_released:,.0f} in working capital."

    findings: list[Finding] = []
    if portfolio.loss_making:
        names = ", ".join(f"{s.segment} ({s.net_to_serve:,.0f})" for s in portfolio.loss_making)
        findings.append(Finding(
            f"{len(portfolio.loss_making)} loss-making segment(s)",
            f"Net-to-serve is negative for: {names}. Cost to serve outruns the revenue.",
            impact="fix the cost-to-serve, re-price, or exit",
        ))
    if portfolio.profit_erosion > 0:
        findings.append(Finding(
            "Profit eroded by the tail",
            f"Profitable segments earn {portfolio.peak_profit:,.0f}; the loss-making tail erodes "
            f"that to {portfolio.total_net_to_serve:,.0f} net.",
            impact=f"{portfolio.profit_erosion:,.0f} recoverable",
        ))
    worst_cts = max(portfolio.segments, key=lambda s: s.cost_to_serve_pct)
    findings.append(Finding(
        f"Highest cost-to-serve: {worst_cts.segment}",
        f"{worst_cts.cost_to_serve_pct * 100:.0f}% of its revenue goes to fulfillment, returns "
        "and overhead - not product.",
        impact="target order consolidation / returns reduction here",
    ))
    if working_cap is not None:
        findings.append(Finding(
            "Working capital tied up",
            f"Cash-to-cash cycle {working_cap.cash_conversion_cycle:.0f} days; net working capital "
            f"{working_cap.net_working_capital:,.0f} (inventory {working_cap.inventory_investment:,.0f} "
            f"+ receivables {working_cap.receivables:,.0f} - payables {working_cap.payables:,.0f}).",
            impact="every cycle day cut frees cash",
        ))
    if has_cash:
        levers = "; ".join(
            f"{r.lever} -{r.days_improved:.0f}d -> {r.cash_released:,.0f}" for r in cash_release.levers
        )
        findings.append(Finding(
            "Cash-release opportunity",
            f"Improving the cycle frees {cash_release.total_cash_released:,.0f} in working capital "
            f"({levers}).",
            impact="one-time cash unlock",
        ))

    kpis: list[Kpi] = [
        Kpi("Overall net-to-serve margin", f"{portfolio.overall_net_margin * 100:.0f}%",
            target=">0% per segment", rationale="Profit after the true cost of serving each segment"),
        Kpi("Loss-making segments", str(len(portfolio.loss_making)), target="0",
            rationale="Segments whose cost to serve outruns revenue"),
    ]
    if working_cap is not None:
        kpis.append(Kpi("Cash-to-cash cycle", f"{working_cap.cash_conversion_cycle:.0f} days",
                        target="minimize",
                        rationale="Days of working capital tied up paying suppliers before collecting cash"))
        kpis.append(Kpi("Net working capital", f"{working_cap.net_working_capital:,.0f}",
                        rationale="Cash locked in inventory + receivables - payables"))
    if has_cash:
        kpis.append(Kpi("Cash-release opportunity", f"{cash_release.total_cash_released:,.0f}",
                        rationale="Cash freed by the targeted cycle improvement"))

    data_sources = (
        DataSource("Segment revenue / volume / COGS", "order & sales data", "monthly"),
        DataSource("Activity cost rates (order / unit / return)", "engagement parameters", "per cycle"),
    )

    recommendations: list[str] = []
    if portfolio.loss_making:
        recommendations.append(
            "Fix the cost-to-serve, re-price, or exit the loss-making segment(s): "
            f"{', '.join(s.segment for s in portfolio.loss_making)}."
        )
    else:
        recommendations.append(f"Protect margin on the thinnest segment ({portfolio.segments[-1].segment}).")
    if has_cash:
        recommendations.append(
            f"Execute the cash-release plan to free {cash_release.total_cash_released:,.0f} "
            "in working capital."
        )
    recommendations.append(
        "Take segment exit / re-pricing decisions and cash targets to the CFO review for sign-off."
    )

    return Deliverable(
        title="Cost-to-Serve & Working Capital Review",
        client=client,
        summary=summary,
        findings=tuple(findings),
        kpis=tuple(kpis),
        data_sources=data_sources,
        recommendations=tuple(recommendations),
        citations=tuple(citations),
        confidence=confidence,
        residual=_RESIDUAL,
        prepared=prepared,
    )
