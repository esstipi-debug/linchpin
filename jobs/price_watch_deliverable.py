"""Deliverable writer for the discovery-assisted watch cycle (Task 11 / PR-11's
agent-tool wiring) -- kept in its own small module (matching the established
``cost_to_serve_deliverable.py`` / ``inventory_deliverable.py`` split) rather
than added to ``jobs/price_watch.py``, which is already near the repo's
800-line file cap (see that module's own docstring and the plan's
Consolidated Risk Register).

Deliberately NO ``jobs.price_watch``/``scm_agent`` import here, even under
``TYPE_CHECKING`` -- this module is imported eagerly at the top of
``scm_agent/tools.py`` alongside every other ``*_deliverable`` module, and an
eager import of ``jobs.price_watch`` (which itself imports ``scm_agent.events``)
would recreate the exact circular-import hazard ``price_intelligence_tool()``
documents. Duck-typed on the report's public fields instead.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.export import write_summary_csv

_CYCLE_OUTCOME_COLUMNS: tuple[str, ...] = (
    "site", "competitor_sku_ref", "matched_product_id", "status", "reason",
)


def write_operational(report: object, out_dir: str | Path, client: str = "Client") -> dict[str, Path]:
    """One row per confirmed pair checked this cycle -- ``price_watch_cycle.csv``
    (``site, competitor_sku_ref, matched_product_id, status, reason``). Always
    written, even with zero pairs checked (a stable header, the same
    "nothing to report" idiom ``jobs.price_watch.write_homologation`` and
    ``jobs.markdown_liquidation_job`` already use) -- never a missing file
    with no explanation (golden rule 14). Every string cell passes through
    ``src.sanitize.defuse_formula`` via ``write_summary_csv`` (OWASP CSV
    injection), the same convention every other CSV deliverable in this repo
    uses.

    ``report.pending_escalations`` / ``report.scaled_watches`` (Task 9's R5
    output) are deliberately NOT written here -- they are surfaced through the
    Guided Execution Layer (``scm_agent.tool_options.price_watch_options``),
    never a second, silent channel for the same escalation.
    """
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)

    path = d / "price_watch_cycle.csv"
    outcomes = list(report.outcomes)
    if outcomes:
        rows = [
            {
                "site": o.site,
                "competitor_sku_ref": o.competitor_sku_ref,
                "matched_product_id": o.matched_product_id,
                "status": o.status,
                "reason": o.reason,
            }
            for o in outcomes
        ]
        written = {"csv": write_summary_csv(rows, path)}
    else:
        pd.DataFrame(columns=list(_CYCLE_OUTCOME_COLUMNS)).to_csv(path, index=False)
        written = {"csv": path}

    # `client` accepted for interface symmetry with every other write_operational
    # in this repo -- this CSV has no per-client Summary sheet of its own.
    _ = client
    return written
