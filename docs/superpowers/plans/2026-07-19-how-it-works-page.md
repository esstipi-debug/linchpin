# How It Works Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `GET /how-it-works`, an interactive, English-language, internal/onboarding page explaining how Kern works: two donut-chart lenses on its 41 capabilities, how it's grounded and adapted to client context, and its alignment with SCOR/CPIM/CLTD/CSCP/SCPro/CPSM/ISO 9001/28000.

**Architecture:** A pure-data module (`webapp/how_it_works_data.py`) feeds a pure-rendering module (`webapp/how_it_works_page.py`, hand-built inline-SVG donuts + HTML snippet helpers, no charting library) that assembles one HTML string, served by a new FastAPI route in `webapp/app.py`. A small vanilla-JS file (`webapp/static/how_it_works.js`) drives all client-side interactivity (donut lens tabs, click-to-expand tool lists, expandable cards/accordion). No new dependencies, no CSP changes.

**Tech Stack:** Python 3.11+, FastAPI, `html.escape` for output safety, inline SVG, vanilla JS. Same dark/teal design system as `webapp/stocky_alternative_page.py` (Inter + JetBrains Mono, `--ink/--panel/--accent` CSS custom properties).

## Global Constraints

- **41 tools total**, verified against `build_default_registry()` in `scm_agent/tools.py` — every count in this feature must sum to 41 (both donut lenses).
- **33 curated knowledge-graph sources** — never write "25 fuentes" (the README's stale figure); this feature always says 33.
- **Never write "Kern is ASCM/ISO-certified"** or any phrasing implying Kern itself holds a credential. Always "implements the same models taught in...", "aligns with...", "maps to...".
- **No sales content**: no pricing, no lead-capture form, no CTA button. Only quiet wayfinding links (Home, live console).
- **No new external JS/CSS dependencies.** No charting library, no CDN script. CSP is `script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com` (confirmed sufficient in `webapp/security.py`, no change needed).
- **Every dynamic string rendered into HTML goes through `html.escape`**, even hardcoded content — matches the existing convention in `webapp/stocky_alternative_page.py`.
- Source of truth for the standards content: `documentation/KERN_NIVEL_REFERENCIA_SCM.md` (translated to English for this page's copy; substance must not change).
- Full design rationale: `docs/superpowers/specs/2026-07-19-how-it-works-page-design.md`.

---

## Task 1: Content data module

**Files:**
- Create: `webapp/how_it_works_data.py`
- Test: `tests/test_how_it_works_data.py`

**Interfaces:**
- Produces: `ToolInfo` (frozen dataclass: `key: str`, `label: str`, `domain_area: str`, `scor_bucket: str`, `one_liner: str`), `TOOLS: tuple[ToolInfo, ...]` (41 entries), `DOMAIN_AREA_ORDER: tuple[str, ...]` (9 labels, descending-count order), `SCOR_BUCKET_ORDER: tuple[str, ...]` (7 labels), `tally_by_domain_area() -> dict[str, int]`, `tally_by_scor_bucket() -> dict[str, int]`, `CertCoverage` (frozen dataclass: `name: str`, `body: str`, `level: str`, `covered: tuple[str, ...]`, `gaps: tuple[str, ...]`), `CERTIFICATIONS: tuple[CertCoverage, ...]` (5 entries), `IsoClause` (frozen dataclass: `clause: str`, `kern_behavior: str`), `ISO_9001_CLAUSES: tuple[IsoClause, ...]`, `ISO_28000_ELEMENTS: tuple[IsoClause, ...]`, `Gap` (frozen dataclass: `name: str`, `current_state: str`, `standard: str`), `HONEST_GAPS: tuple[Gap, ...]`.
- Consumes: nothing (leaf module, no imports from the rest of `webapp/` or `scm_agent/`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_how_it_works_data.py`:

```python
"""Unit tests for webapp/how_it_works_data.py -- the static content data
backing GET /how-it-works. No HTTP client needed; these are pure-data
invariant checks."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from webapp.how_it_works_data import (  # noqa: E402
    CERTIFICATIONS,
    DOMAIN_AREA_ORDER,
    HONEST_GAPS,
    ISO_28000_ELEMENTS,
    ISO_9001_CLAUSES,
    SCOR_BUCKET_ORDER,
    TOOLS,
    tally_by_domain_area,
    tally_by_scor_bucket,
)


def test_exactly_41_tools_with_unique_keys() -> None:
    assert len(TOOLS) == 41
    assert len({t.key for t in TOOLS}) == 41


def test_domain_area_tally_sums_to_41_and_matches_spec() -> None:
    tally = tally_by_domain_area()
    assert sum(tally.values()) == 41
    assert tally == {
        "Inventory & replenishment": 9,
        "Network & logistics": 7,
        "Inventory control & health": 6,
        "Pricing & finance": 6,
        "Demand & classification": 3,
        "Procurement & sourcing": 3,
        "Returns, risk & benchmarking": 3,
        "Planning cadence & projects": 3,
        "Leadership": 1,
    }
    assert set(tally) == set(DOMAIN_AREA_ORDER)


def test_scor_bucket_tally_sums_to_41_and_matches_spec() -> None:
    tally = tally_by_scor_bucket()
    assert sum(tally.values()) == 41
    assert tally == {
        "Plan": 15,
        "Order/Fulfill": 8,
        "Orchestrate": 8,
        "Transform": 4,
        "Source": 3,
        "Return": 2,
        "Outside SCOR scope": 1,
    }
    assert set(tally) == set(SCOR_BUCKET_ORDER)


def test_every_tool_uses_a_known_domain_area_and_scor_bucket() -> None:
    for tool in TOOLS:
        assert tool.domain_area in DOMAIN_AREA_ORDER, tool.key
        assert tool.scor_bucket in SCOR_BUCKET_ORDER, tool.key
        assert tool.label and tool.one_liner, tool.key


def test_five_certifications_with_valid_levels_and_nonempty_lists() -> None:
    assert len(CERTIFICATIONS) == 5
    assert {c.name for c in CERTIFICATIONS} == {"CPIM", "CLTD", "CSCP", "SCPro", "CPSM"}
    for cert in CERTIFICATIONS:
        assert cert.level in {"High", "Medium-high", "Partial"}
        assert cert.covered
        assert cert.gaps


def test_iso_clauses_and_gaps_are_nonempty() -> None:
    assert len(ISO_9001_CLAUSES) >= 8
    assert len(ISO_28000_ELEMENTS) >= 3
    assert len(HONEST_GAPS) >= 5
    for gap in HONEST_GAPS:
        assert gap.name and gap.current_state and gap.standard
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_data.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'webapp.how_it_works_data'`

- [ ] **Step 3: Write the implementation**

Create `webapp/how_it_works_data.py`:

```python
"""Static content data for GET /how-it-works (webapp/how_it_works_page.py).

Every count here is verified against the actual code, not copied from a
possibly-stale doc: 41 tools = build_default_registry()'s 41 register()
calls in scm_agent/tools.py. The domain-area grouping matches README.md's
"All 40 capabilities" table (corrected here to 41 -- launch_readiness,
tool #41, postdates that table's last refresh). The SCOR Digital Standard
bucket per tool is grounded in documentation/KERN_NIVEL_REFERENCIA_SCM.md
Section 2 (itself generated from a direct code read on 2026-07-17),
cross-checked during this feature's design phase by a 45-agent adversarial
verification workflow against the tools' actual source -- see
docs/superpowers/specs/2026-07-19-how-it-works-page-design.md Section 4.2
for the two gaps that document's own table had (reconciliation/
odoo_replenishment/excel_replenishment bundled under the tool they extend;
launch_readiness added to Plan; leadership_chain marked as genuinely outside
SCOR's scope rather than force-fit).

If a future PR changes the tool count, add/remove/re-bucket a tool here in
the SAME PR -- this module is the single source of truth the donuts and
tallies are computed from, precisely so the numbers can never drift from
what render_how_it_works_html() actually draws.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolInfo:
    key: str
    label: str
    domain_area: str
    scor_bucket: str
    one_liner: str


DOMAIN_AREA_ORDER: tuple[str, ...] = (
    "Inventory & replenishment",
    "Network & logistics",
    "Inventory control & health",
    "Pricing & finance",
    "Demand & classification",
    "Procurement & sourcing",
    "Returns, risk & benchmarking",
    "Planning cadence & projects",
    "Leadership",
)

SCOR_BUCKET_ORDER: tuple[str, ...] = (
    "Plan",
    "Order/Fulfill",
    "Orchestrate",
    "Transform",
    "Source",
    "Return",
    "Outside SCOR scope",
)

TOOLS: tuple[ToolInfo, ...] = (
    # -- Inventory & replenishment (9) --
    ToolInfo("inventory_optimization", "Inventory Optimization", "Inventory & replenishment", "Plan",
             "Forecast -> (s,Q)/(R,S) policy -> budget-constrained portfolio allocation."),
    ToolInfo("newsvendor", "Newsvendor", "Inventory & replenishment", "Plan",
             "Single-period order quantity via the critical-ratio rule, for perishable/seasonal demand."),
    ToolInfo("multi_echelon", "Multi-Echelon", "Inventory & replenishment", "Plan",
             "Guaranteed-Service Model safety-stock placement across a serial chain."),
    ToolInfo("ddmrp", "DDMRP", "Inventory & replenishment", "Plan",
             "Demand Driven MRP buffer zones and a decoupled lead time."),
    ToolInfo("simulation", "Simulation", "Inventory & replenishment", "Plan",
             "Monte Carlo validation of an inventory policy: fill rate, backorders, lost sales."),
    ToolInfo("digital_twin", "Digital Twin", "Inventory & replenishment", "Orchestrate",
             "A network scenario factory that feeds what-if analysis across the suite."),
    ToolInfo("drp", "DRP", "Inventory & replenishment", "Order/Fulfill",
             "Distribution Requirements Planning: a timed, multi-echelon replenishment grid."),
    ToolInfo("odoo_replenishment", "Odoo Replenishment", "Inventory & replenishment", "Plan",
             "Live Odoo ERP read plus staged, reversible replenishment writeback."),
    ToolInfo("excel_replenishment", "Excel Replenishment", "Inventory & replenishment", "Plan",
             "Client spreadsheet read plus staged, reversible replenishment writeback."),
    # -- Inventory control & health (6) --
    ToolInfo("cycle_count", "Cycle Count", "Inventory control & health", "Plan",
             "Cycle-counting program design by ABC class, tracking inventory record accuracy."),
    ToolInfo("reconciliation", "Reconciliation", "Inventory control & health", "Plan",
             "Reconciles inventory records against a physical count."),
    ToolInfo("excess_obsolete", "Excess & Obsolete", "Inventory control & health", "Plan",
             "Classifies SKUs healthy/excess/dead and sizes the cash tied up in slow stock."),
    ToolInfo("markdown_liquidation", "Markdown & Liquidation", "Inventory control & health", "Return",
             "Clearance pricing for excess stock, with a competitor price floor."),
    ToolInfo("fefo", "FEFO", "Inventory control & health", "Order/Fulfill",
             "First-Expired-First-Out issue order plus a markdown-vs-scrap disposition."),
    ToolInfo("data_quality", "Data Quality", "Inventory control & health", "Orchestrate",
             "Master/inventory data quality checks, including GTIN validation."),
    # -- Procurement & sourcing (3) --
    ToolInfo("sourcing", "Sourcing", "Procurement & sourcing", "Source",
             "Supplier scorecarding via OTIF/DIFOT and defect rate."),
    ToolInfo("landed_cost", "Landed Cost", "Procurement & sourcing", "Source",
             "Total cost to destination, Incoterm-aware."),
    ToolInfo("acceptance_sampling", "Acceptance Sampling", "Procurement & sourcing", "Source",
             "Incoming-quality sampling plan by AQL/LTPD."),
    # -- Network & logistics (7) --
    ToolInfo("facility_location", "Facility Location", "Network & logistics", "Order/Fulfill",
             "Cost-minimizing single-facility siting via center-of-gravity and Weiszfeld."),
    ToolInfo("transportation", "Transportation", "Network & logistics", "Order/Fulfill",
             "Mode selection (parcel/LTL/FTL/intermodal) and the LTL-to-FTL break-even."),
    ToolInfo("vehicle_routing", "Vehicle Routing", "Network & logistics", "Order/Fulfill",
             "Vehicle routing via Clarke-Wright savings and the sweep algorithm."),
    ToolInfo("warehouse_layout", "Warehouse Layout", "Network & logistics", "Order/Fulfill",
             "A parametric, navigable 3D warehouse layout: racks, aisles, docks, yard."),
    ToolInfo("slotting", "Slotting", "Network & logistics", "Order/Fulfill",
             "Warehouse slotting by cube-per-order index and pick affinity."),
    ToolInfo("queuing", "Queuing", "Network & logistics", "Transform",
             "Cost-optimal server counts via an M/M/c queuing model."),
    ToolInfo("scheduling", "Scheduling", "Network & logistics", "Transform",
             "Job dispatching rules (SPT/EDD/FCFS/LPT) to minimize flow time or lateness."),
    # -- Pricing & finance (6) --
    ToolInfo("pricing", "Pricing", "Pricing & finance", "Orchestrate",
             "Price elasticity to a margin-maximizing price point."),
    ToolInfo("price_intelligence", "Price Intelligence", "Pricing & finance", "Orchestrate",
             "One-shot competitor price position analysis."),
    ToolInfo("price_watch", "Price Watch", "Pricing & finance", "Orchestrate",
             "Recurring, read-only competitor price monitoring with auto-onboarding."),
    ToolInfo("financial_kpis", "Financial KPIs", "Pricing & finance", "Orchestrate",
             "Inventory turns, DIO, GMROI, cash-to-cash."),
    ToolInfo("cost_to_serve", "Cost to Serve", "Pricing & finance", "Order/Fulfill",
             "Cost-to-serve by customer/channel, including the whale-curve view."),
    ToolInfo("learning_curve", "Learning Curve", "Pricing & finance", "Transform",
             "Wright's-law cost projection over cumulative production volume."),
    # -- Returns, risk & benchmarking (3) --
    ToolInfo("returns", "Returns", "Returns, risk & benchmarking", "Return",
             "Reverse-logistics disposition (restock/refurbish/liquidate/scrap)."),
    ToolInfo("risk", "Risk", "Returns, risk & benchmarking", "Orchestrate",
             "A supply chain risk register: EMV, FMEA, and a TTR-vs-TTS resilience gap."),
    ToolInfo("dea", "DEA", "Returns, risk & benchmarking", "Orchestrate",
             "Data Envelopment Analysis efficiency benchmarking."),
    # -- Demand & classification (3) --
    ToolInfo("abc_xyz", "ABC-XYZ", "Demand & classification", "Plan",
             "ABC-XYZ classification into a 9-cell policy matrix."),
    ToolInfo("forecast", "Forecast", "Demand & classification", "Plan",
             "Demand forecasting, including intermittent-demand methods."),
    ToolInfo("whatif", "What-If", "Demand & classification", "Plan",
             "Sensitivity analysis: tornado charts, best/worst case, break-even."),
    # -- Planning cadence & projects (3) --
    ToolInfo("sop", "S&OP", "Planning cadence & projects", "Plan",
             "Aggregate Sales & Operations Planning: Chase/Level/Hybrid strategies."),
    ToolInfo("earned_value", "Earned Value", "Planning cadence & projects", "Transform",
             "Project earned-value management: SV/CV/SPI/CPI."),
    ToolInfo("launch_readiness", "Launch Readiness", "Planning cadence & projects", "Plan",
             "Campaign launch-date readiness versus lead time and coverage."),
    # -- Leadership (1) --
    ToolInfo("leadership_chain", "Leadership Chain", "Leadership", "Outside SCOR scope",
             "A CHAIN leadership profile and directives -- an organizational assessment, "
             "not a supply chain operation."),
)


def tally_by_domain_area() -> dict[str, int]:
    counts = Counter(t.domain_area for t in TOOLS)
    return {area: counts.get(area, 0) for area in DOMAIN_AREA_ORDER}


def tally_by_scor_bucket() -> dict[str, int]:
    counts = Counter(t.scor_bucket for t in TOOLS)
    return {bucket: counts.get(bucket, 0) for bucket in SCOR_BUCKET_ORDER}


@dataclass(frozen=True)
class CertCoverage:
    name: str
    body: str
    level: str  # "High" | "Medium-high" | "Partial"
    covered: tuple[str, ...]
    gaps: tuple[str, ...]


CERTIFICATIONS: tuple[CertCoverage, ...] = (
    CertCoverage(
        "CPIM", "ASCM", "High",
        covered=(
            "Demand forecasting, including intermittent demand",
            "EOQ and volume discounts",
            "Safety stock from forecast-error sigma",
            "(s,Q) and (R,S) policies",
            "Newsvendor model",
            "Multi-echelon Guaranteed-Service Model",
            "DDMRP",
            "ABC-XYZ classification",
            "Aggregate S&OP",
            "DRP",
            "Policy simulation",
            "Cycle counting / inventory record accuracy",
            "Job sequencing",
            "Learning curve",
        ),
        gaps=(
            "Detailed MRP-II / multi-level BOM explosion",
            "Formal master production scheduling (MPS)",
            "Order-level plant capacity management",
        ),
    ),
    CertCoverage(
        "CLTD", "ASCM", "High",
        covered=(
            "DRP",
            "Facility location",
            "Mode selection and LTL/FTL break-even",
            "Vehicle routing (CVRP)",
            "Warehouse layout and slotting",
            "FEFO / expiry management",
            "Cost-to-serve",
            "Landed cost",
            "Reverse logistics",
        ),
        gaps=(
            "Customs / international trade compliance beyond Incoterm + tariff",
            "Operational WMS/TMS",
            "Multi-facility network optimization (only single-facility siting today)",
            "Global trade compliance",
        ),
    ),
    CertCoverage(
        "CSCP", "ASCM", "Medium-high",
        covered=(
            "End-to-end integration via the orchestrator",
            "SCOR process mapping",
            "Technology: digital twin, agent, writeback",
            "Metrics: cash-to-cash, cost-to-serve, DEA",
            "TTR/TTS risk",
        ),
        gaps=(
            "Computable sustainability (only unstructured knowledge, no calculation engine)",
            "Network/chain design at MILP scale",
            "Customer collaboration / CRM",
            "Strategic supplier relationship management",
        ),
    ),
    CertCoverage(
        "SCPro", "CSCMP", "Medium-high",
        covered=(
            "Network analysis: facility location, digital twin",
            "KPIs and benchmarking: DEA, financial KPIs",
            "Problem-solving: decision support, MCDM, what-if",
            "Project management: earned value",
        ),
        gaps=(
            "Network analysis at scale (joint optimization)",
            "Live external data integration (most calculation is offline by design)",
            "Sustainability",
        ),
    ),
    CertCoverage(
        "CPSM", "ISM", "Partial",
        covered=(
            "Supplier performance: OTIF/PPM",
            "Landed cost / TCO",
            "Multi-criteria supplier selection: BWM/TOPSIS",
            "Acceptance sampling",
            "Change/negotiation analysis",
            "Supply risk",
        ),
        gaps=(
            "Deep supplier relationship management (Kraljic segmentation, power matrix, "
            "supplier development)",
            "Contract lifecycle management",
            "Category strategy",
            "End-to-end strategic sourcing",
            "Supplier ethics/diversity",
            "Spend analysis",
        ),
    ),
)


@dataclass(frozen=True)
class IsoClause:
    clause: str
    kern_behavior: str


ISO_9001_CLAUSES: tuple[IsoClause, ...] = (
    IsoClause("4.4 / 8.1 Process approach",
              "A fixed, self-describing pipeline: every capability is a Tool with "
              "prepare/run/qa/deliver -- the same sequence for all 41."),
    IsoClause("7.5 Documented information",
              "An EvidenceRecord (SHA-256 of inputs, control totals, formula versions, QA "
              "attestations); a writeback AuditEntry; a Keep-a-Changelog CHANGELOG; L3 "
              "citations on every deliverable."),
    IsoClause("8.5.1 Control of production",
              "Grounding, confidence, and guided options on every deliverable; personas/KPIs "
              "per mode."),
    IsoClause("8.5.2 Traceability",
              "Partial: data_quality validates GTIN (GS1); lots/ gives FEFO plus expiry. Lot "
              "genealogy is not yet built."),
    IsoClause("8.6 Release of products",
              "A double gate: the tool's own QA, plus a citation_gate in packages."),
    IsoClause("8.7 Control of nonconforming outputs",
              "QA fails => zero deliverables. A package's runner computes everything first "
              "and only writes if every step passes."),
    IsoClause("8.5.6 Control of changes",
              "Writeback stage -> signed, time-boxed approval -> apply -> rollback. Autonomy "
              "config changes only via a signed Changeset."),
    IsoClause("9.1 Monitoring and measurement",
              "forecast_metrics, financial_kpis, dea, reliability.py."),
    IsoClause("10 Continual improvement",
              "A verify/backtest loop feeding a ToolReliabilityReport, which drives "
              "evidence-based autonomy promotion."),
)

ISO_28000_ELEMENTS: tuple[IsoClause, ...] = (
    IsoClause("Risk assessment",
              "risk.py: EMV, FMEA RPN, a risk heatmap, and the TTR-vs-TTS gap; risk_period "
              "for lead-time risk."),
    IsoClause("System security controls",
              "Bounded parameters, client allowlisting, path-traversal defense, a 25 MB "
              "upload cap, rate limiting, constant-time API-key comparison, CSP, "
              "formula-injection defusing."),
    IsoClause("Change authorization",
              "Signed, time-boxed (HMAC) approvals tied to an idempotency + content hash; "
              "autonomy tiers with human gates; SLA-bound escalation."),
    IsoClause("Continuity / fail-safe",
              "A hardening flag refuses to boot without required controls; the "
              "never-unprotected contract; idempotent apply plus rollback; graceful "
              "degradation without an LLM key."),
)


@dataclass(frozen=True)
class Gap:
    name: str
    current_state: str
    standard: str


HONEST_GAPS: tuple[Gap, ...] = (
    Gap(
        "Computable sustainability",
        "Only unstructured knowledge (a book in the graph); no carbon/GHG calculation "
        "engine yet, even though the pricing/logistics layer already names sustainability "
        "as a persona concern.",
        "SCOR ES, CSCP, ISO 14001",
    ),
    Gap(
        "Deep supplier relationship management",
        "Supplier scorecarding is OTIF/DIFOT plus defect rate only; no Kraljic "
        "segmentation, power analysis, or supplier development.",
        "CPSM, CSCP",
    ),
    Gap(
        "Lot-level traceability / genealogy",
        "GTIN validation plus FEFO/expiry exist; no one-up/one-down chain of custody or "
        "EPCIS event log.",
        "ISO 9001 8.5.2, food/pharma",
    ),
    Gap(
        "Broad regulatory compliance",
        "Strong on pricing (EU/UK Omnibus) and customs (Incoterm); missing trade "
        "compliance, HS classification, denied-party screening.",
        "CLTD, CPSM",
    ),
    Gap(
        "Quantified resilience",
        "A qualitative TTR-vs-TTS gap exists in the risk register; no network stress-test "
        "with recovery time/impact simulation.",
        "SCOR AG (agility)",
    ),
    Gap(
        "Network optimization at scale",
        "Only single-facility siting (Weiszfeld); no multi-facility p-median/MILP.",
        "CLTD, SCPro",
    ),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_data.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add webapp/how_it_works_data.py tests/test_how_it_works_data.py
git commit -m "feat: add how-it-works page content data (41 tools, SCOR/ASCM mapping)"
```

---

## Task 2: Donut SVG rendering helper

**Files:**
- Create: `webapp/how_it_works_page.py` (started here; grows through Tasks 3-4)
- Test: `tests/test_how_it_works_page.py` (started here; grows through Tasks 3, 4, 6)

**Interfaces:**
- Consumes: nothing from Task 1 yet (generic helper, takes plain `(label, count)` pairs).
- Produces: `_donut_svg(segments: Sequence[tuple[str, int]], *, element_id: str, size: int = 240, stroke_width: int = 36) -> str`, `_DONUT_COLORS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_how_it_works_page.py`:

```python
"""Tests for webapp/how_it_works_page.py -- the /how-it-works page renderer.
Rendering-helper tests call the (module-private, deliberately imported
directly here) functions without an HTTP client; Task 6 adds HTTP-level
tests through the real FastAPI app, mirroring tests/test_stocky_alternative_page.py."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from webapp.how_it_works_page import _donut_svg  # noqa: E402


def test_donut_svg_has_one_circle_per_segment_and_correct_total() -> None:
    svg = _donut_svg([("A", 2), ("B", 1), ("C", 1)], element_id="test-donut")
    assert svg.count("<circle") == 3
    assert 'id="test-donut"' in svg
    assert ">4<" in svg  # the total, rendered as center text


def test_donut_svg_segment_percentages_are_correct() -> None:
    svg = _donut_svg([("A", 2), ("B", 1), ("C", 1)], element_id="test-donut")
    assert 'data-pct="50"' in svg
    assert svg.count('data-pct="25"') == 2


def test_donut_svg_escapes_labels() -> None:
    svg = _donut_svg([("<script>", 1), ("B", 1)], element_id="xss-donut")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_donut_svg_rejects_empty_total() -> None:
    import pytest

    with pytest.raises(ValueError):
        _donut_svg([("A", 0), ("B", 0)], element_id="empty-donut")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.how_it_works_page'`

- [ ] **Step 3: Write the implementation**

Create `webapp/how_it_works_page.py`:

```python
"""Server-rendered HTML for GET /how-it-works.

An internal/onboarding page (not a sales page -- see
docs/superpowers/specs/2026-07-19-how-it-works-page-design.md): what Kern
does, its 41 capabilities under two donut-chart lenses (domain area / SCOR
Digital Standard process), how it's grounded and adapted per client, and its
alignment with SCOR/CPIM/CLTD/CSCP/SCPro/CPSM/ISO 9001/28000.

Reuses the SAME dark/teal visual system as webapp/stocky_alternative_page.py
(Inter + JetBrains Mono, --ink/--panel/--accent tokens) for visual
consistency across the site, but is otherwise a fully self-contained page
(its own <style> block, per this codebase's per-page convention -- see
paquetes_page.py/pricing_page.py/tower_page.py, none of which share a CSS
file either).

No charting library: donuts are hand-built inline SVG (stroke-dasharray/
stroke-dashoffset arcs). All interactivity (lens tabs, click-to-expand tool
lists, expandable cards/accordion) lives in webapp/static/how_it_works.js,
loaded via a <script src> tag -- confirmed compatible with the base CSP
(webapp/security.py's csp_for_path() only special-cases /console and
/static/prototype; this route gets the strict default, which already allows
'self'-hosted scripts).
"""

from __future__ import annotations

import math
from html import escape
from typing import Sequence

_DONUT_COLORS: tuple[str, ...] = (
    "#4fd1c5",  # accent
    "#5eead4",  # accent-bright
    "#f5b942",  # warn
    "#8b7cf6",
    "#f47174",
    "#63b3ed",
    "#68d391",
    "#f6ad55",
    "#b794f4",
)


def _donut_svg(
    segments: Sequence[tuple[str, int]],
    *,
    element_id: str,
    size: int = 240,
    stroke_width: int = 36,
) -> str:
    """Render an accessible inline SVG donut chart.

    `segments` is an ordered sequence of (label, count) pairs; count must be
    >= 0 and the total must be > 0. Each segment becomes one <circle> arc
    carrying data-label/data-count/data-pct attributes (read by
    static/how_it_works.js for click-to-filter) plus a native <title> so a
    hover tooltip works with zero JS.
    """
    total = sum(count for _, count in segments)
    if total <= 0:
        raise ValueError("donut segments must sum to a positive total")

    radius = (size - stroke_width) / 2
    circumference = 2 * math.pi * radius
    center = size / 2

    cumulative = 0.0
    arcs: list[str] = []
    for i, (label, count) in enumerate(segments):
        color = _DONUT_COLORS[i % len(_DONUT_COLORS)]
        fraction = count / total
        dash = fraction * circumference
        gap = circumference - dash
        offset = -cumulative
        cumulative += dash
        pct = round(fraction * 100)
        safe_label = escape(str(label))
        arcs.append(
            f'<circle class="donut-seg" data-label="{safe_label}" data-count="{count}" '
            f'data-pct="{pct}" tabindex="0" cx="{center}" cy="{center}" r="{radius:.3f}" '
            f'fill="none" stroke="{color}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="{dash:.3f} {gap:.3f}" stroke-dashoffset="{offset:.3f}" '
            f'transform="rotate(-90 {center} {center})">'
            f"<title>{safe_label}: {count} ({pct}%)</title>"
            "</circle>"
        )

    return (
        f'<svg class="donut" id="{escape(element_id)}" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}" role="img" aria-label="Donut chart">'
        + "".join(arcs)
        + f'<text x="{center}" y="{center}" class="donut-total" text-anchor="middle" '
        f'dominant-baseline="middle">{total}</text>'
        + "</svg>"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add webapp/how_it_works_page.py tests/test_how_it_works_page.py
git commit -m "feat: add inline-SVG donut helper for the how-it-works page"
```

---

## Task 3: Supporting content renderers

**Files:**
- Modify: `webapp/how_it_works_page.py`
- Modify: `tests/test_how_it_works_page.py`

**Interfaces:**
- Consumes: `ToolInfo`, `CertCoverage`, `IsoClause` from `webapp.how_it_works_data` (Task 1).
- Produces: `_expandable_card(title: str, summary: str, detail_html: str, *, card_id: str) -> str`, `_coverage_bar(cert: CertCoverage, *, bar_id: str) -> str`, `_iso_accordion_row(clause: IsoClause, *, row_id: str) -> str`, `_stepper(stages: Sequence[tuple[str, str]]) -> str` (stage name, one-liner).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_how_it_works_page.py`:

```python
from webapp.how_it_works_data import CertCoverage, IsoClause  # noqa: E402
from webapp.how_it_works_page import (  # noqa: E402
    _coverage_bar,
    _expandable_card,
    _iso_accordion_row,
    _stepper,
)


def test_expandable_card_has_toggle_button_and_hidden_detail() -> None:
    html = _expandable_card("Title", "Summary", "<p>Detail</p>", card_id="card-1")
    assert 'data-target="card-1"' in html
    assert 'id="card-1"' in html
    assert "hidden" in html
    assert "Title" in html and "Summary" in html and "Detail" in html


def test_coverage_bar_renders_level_and_covered_gaps() -> None:
    cert = CertCoverage(
        "CPIM", "ASCM", "High", covered=("Forecasting",), gaps=("MRP-II",)
    )
    html = _coverage_bar(cert, bar_id="cert-cpim")
    assert "CPIM" in html and "ASCM" in html and "High" in html
    assert "Forecasting" in html
    assert "MRP-II" in html
    assert html.count('class="bar-seg filled"') == 4  # "High" = 4/4 segments filled


def test_coverage_bar_partial_level_fills_two_segments() -> None:
    cert = CertCoverage("CPSM", "ISM", "Partial", covered=("X",), gaps=("Y",))
    html = _coverage_bar(cert, bar_id="cert-cpsm")
    assert html.count('class="bar-seg filled"') == 2


def test_iso_accordion_row_renders_clause_and_behavior() -> None:
    clause = IsoClause("8.7 Control of nonconforming outputs", "QA fails => zero deliverables.")
    html = _iso_accordion_row(clause, row_id="iso-1")
    assert "8.7 Control of nonconforming outputs" in html
    assert "QA fails =&gt; zero deliverables." in html or "QA fails => zero deliverables." in html


def test_stepper_renders_all_stages() -> None:
    html = _stepper([("Brief", "A plain-language request."), ("QA", "Gate that vetoes bad results.")])
    assert "Brief" in html and "A plain-language request." in html
    assert "QA" in html and "Gate that vetoes bad results." in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v -k "card or bar or accordion or stepper"`
Expected: FAIL with `ImportError: cannot import name '_expandable_card'`

- [ ] **Step 3: Write the implementation**

Append to `webapp/how_it_works_page.py` (after `_donut_svg`, before any later additions):

```python
from webapp.how_it_works_data import CertCoverage, IsoClause  # noqa: E402

_LEVEL_FILL: dict[str, int] = {"High": 4, "Medium-high": 3, "Partial": 2}


def _expandable_card(title: str, summary: str, detail_html: str, *, card_id: str) -> str:
    return (
        f'<button type="button" class="card-toggle" data-target="{escape(card_id)}" '
        f'aria-expanded="false">'
        f"<h3>{escape(title)}</h3><p class=\"sub\">{escape(summary)}</p>"
        "</button>"
        f'<div class="card-detail" id="{escape(card_id)}" hidden>{detail_html}</div>'
    )


def _coverage_bar(cert: CertCoverage, *, bar_id: str) -> str:
    filled = _LEVEL_FILL.get(cert.level, 1)
    segments = "".join(
        f'<span class="bar-seg{" filled" if i < filled else ""}"></span>' for i in range(4)
    )
    covered_items = "".join(f"<li>{escape(item)}</li>" for item in cert.covered)
    gap_items = "".join(f"<li>{escape(item)}</li>" for item in cert.gaps)
    return (
        f'<button type="button" class="cert-toggle" data-target="{escape(bar_id)}" '
        f'aria-expanded="false">'
        f'<span class="cert-name">{escape(cert.name)}</span>'
        f'<span class="cert-body">{escape(cert.body)}</span>'
        f'<span class="cert-bar" aria-hidden="true">{segments}</span>'
        f'<span class="cert-level">{escape(cert.level)}</span>'
        "</button>"
        f'<div class="cert-detail" id="{escape(bar_id)}" hidden>'
        f"<h4>Covered</h4><ul class=\"check\">{covered_items}</ul>"
        f"<h4>Gaps</h4><ul class=\"gap\">{gap_items}</ul>"
        "</div>"
    )


def _iso_accordion_row(clause: IsoClause, *, row_id: str) -> str:
    return (
        f'<button type="button" class="iso-toggle" data-target="{escape(row_id)}" '
        f'aria-expanded="false">'
        f'<span class="iso-clause">{escape(clause.clause)}</span>'
        '<span class="iso-chevron" aria-hidden="true">&#9662;</span>'
        "</button>"
        f'<div class="iso-detail" id="{escape(row_id)}" hidden>'
        f"<p>{escape(clause.kern_behavior)}</p></div>"
    )


def _stepper(stages: Sequence[tuple[str, str]]) -> str:
    items = "".join(
        f'<li class="step"><span class="step-name">{escape(name)}</span>'
        f'<span class="step-detail">{escape(detail)}</span></li>'
        for name, detail in stages
    )
    return f'<ol class="stepper">{items}</ol>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v`
Expected: PASS (9 tests total)

- [ ] **Step 5: Commit**

```bash
git add webapp/how_it_works_page.py tests/test_how_it_works_page.py
git commit -m "feat: add expandable-card/coverage-bar/ISO-accordion/stepper renderers"
```

---

## Task 4: Assemble the full page

**Files:**
- Modify: `webapp/how_it_works_page.py`
- Modify: `tests/test_how_it_works_page.py`

**Interfaces:**
- Consumes: everything from Tasks 1-3 (`TOOLS`, `DOMAIN_AREA_ORDER`, `SCOR_BUCKET_ORDER`, `tally_by_domain_area`, `tally_by_scor_bucket`, `CERTIFICATIONS`, `ISO_9001_CLAUSES`, `ISO_28000_ELEMENTS`, `HONEST_GAPS`, `_donut_svg`, `_expandable_card`, `_coverage_bar`, `_iso_accordion_row`, `_stepper`).
- Produces: `render_how_it_works_html() -> str` (no arguments -- fully static content, per the spec's non-goal of a live/parameterized page).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_how_it_works_page.py`:

```python
from webapp.how_it_works_page import render_how_it_works_html  # noqa: E402


def test_page_mentions_41_tools_and_33_sources_not_stale_numbers() -> None:
    html = render_how_it_works_html()
    assert "41" in html
    assert "33" in html
    assert "25 curated" not in html  # the README's stale source count must never appear here


def test_page_has_both_donut_lenses_totaling_41() -> None:
    html = render_how_it_works_html()
    assert 'id="donut-domain"' in html
    assert 'id="donut-scor"' in html
    assert 'id="donut-guided"' in html  # the never-unprotected donut, 4 outcomes


def test_page_lists_all_five_certifications() -> None:
    html = render_how_it_works_html()
    for name in ("CPIM", "CLTD", "CSCP", "SCPro", "CPSM"):
        assert name in html


def test_page_has_no_certification_overclaim_language() -> None:
    html = render_how_it_works_html().lower()
    assert "kern is certified" not in html
    assert "kern is ascm-certified" not in html
    assert "kern is iso" not in html


def test_page_has_no_sales_content() -> None:
    html = render_how_it_works_html().lower()
    assert "buy.stripe.com" not in html
    assert "btn-primary" not in html  # the site's CTA-button class, intentionally absent here


def test_page_has_trademark_disclaimer_and_source_doc_link() -> None:
    html = render_how_it_works_html()
    assert "ASCM" in html
    assert "not affiliated with" in html or "not certified by" in html
    assert "KERN_NIVEL_REFERENCIA_SCM" in html


def test_page_has_quiet_nav_links() -> None:
    html = render_how_it_works_html()
    assert 'href="/"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v -k "page_"`
Expected: FAIL with `ImportError: cannot import name 'render_how_it_works_html'`

- [ ] **Step 3: Write the implementation**

First, replace Task 3's `from webapp.how_it_works_data import CertCoverage, IsoClause`
line (near the top of the file, right after the `_donut_svg` function) with the
same import expanded to cover everything this task also needs — one import
statement for the whole module, not two:

```python
from webapp.how_it_works_data import (  # noqa: E402
    CERTIFICATIONS,
    DOMAIN_AREA_ORDER,
    HONEST_GAPS,
    ISO_28000_ELEMENTS,
    ISO_9001_CLAUSES,
    SCOR_BUCKET_ORDER,
    TOOLS,
    CertCoverage,
    IsoClause,
    tally_by_domain_area,
    tally_by_scor_bucket,
)
```

Then append the rest of the page below the existing Task 2/3 helpers:

```python
_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How Kern Works | Kern</title>
<meta name="description" content="How Kern's 41 supply-chain capabilities work: what feeds them, how they adapt to a client's context, and how they align with SCOR, CPIM, CLTD, CSCP, SCPro, CPSM, and ISO 9001/28000.">
<link rel="icon" href="data:,">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#080b11; --panel:#111722; --panel-2:#0f141d;
    --line:#1e2733; --line-2:#283341;
    --txt:#e7eef6; --txt-2:#c4cfdb; --muted:#9aa7b6; --faint:#5e6b7a;
    --accent:#4fd1c5; --accent-bright:#5eead4; --accent-soft:rgba(79,209,197,.14); --accent-bd:rgba(79,209,197,.45);
    --warn:#f5b942; --warn-soft:rgba(245,185,66,.12); --warn-bd:rgba(245,185,66,.4);
    --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
    --sans:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
    --r:13px;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--ink);color:var(--txt);font-family:var(--sans);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;
    background-image:radial-gradient(1100px 520px at 10% -8%,rgba(79,209,197,.09),transparent 60%),radial-gradient(900px 620px at 110% 0%,rgba(120,90,255,.06),transparent 55%);background-attachment:fixed}
  a{color:var(--accent-bright);text-decoration:none}
  .wrap{max-width:920px;margin:0 auto;padding:0 22px}
  header{border-bottom:1px solid var(--line);background:rgba(8,11,17,.7);backdrop-filter:blur(10px)}
  header .wrap{display:flex;align-items:center;justify-content:space-between;height:60px;max-width:1080px}
  .brand{display:flex;align-items:center;gap:9px;font:700 17px/1 var(--mono)}
  .brand .d{color:var(--accent)}
  header nav{display:flex;gap:18px;align-items:center;font-size:14px;color:var(--txt-2)}
  h1{font-size:clamp(1.9rem,1.3rem+2.4vw,3rem);font-weight:800;letter-spacing:-.02em;margin:0 0 .3em;line-height:1.15}
  h2{font-size:1.35rem;font-weight:700;margin:0 0 .5em;letter-spacing:-.01em}
  h3{font-size:1.05rem;font-weight:700;margin:0 0 .3em}
  h4{font-size:.85rem;font-weight:700;margin:14px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
  .eyebrow{font:600 12px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--accent-bright)}
  .muted{color:var(--muted)} .sub{color:var(--txt-2)}
  section{padding:34px 0}
  section + section{border-top:1px solid var(--line)}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:22px}
  ul.check{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
  ul.check li{padding-left:22px;position:relative;color:var(--txt-2);font-size:13.5px}
  ul.check li::before{content:"\\2713";position:absolute;left:0;top:0;color:var(--accent-bright);font-weight:700}
  ul.gap{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
  ul.gap li{padding-left:22px;position:relative;color:var(--txt-2);font-size:13.5px}
  ul.gap li::before{content:"\\2013";position:absolute;left:0;top:0;color:var(--warn)}
  footer{border-top:1px solid var(--line);padding:26px 0;color:var(--faint);font-size:13px}
  footer .wrap{max-width:1080px}

  /* -- stepper -- */
  .stepper{list-style:none;margin:22px 0 0;padding:0;display:flex;gap:0;flex-wrap:wrap;counter-reset:step}
  .stepper .step{flex:1 1 150px;padding:14px 16px;border:1px solid var(--line-2);border-radius:var(--r);background:var(--panel-2);position:relative;counter-increment:step}
  .stepper .step::before{content:counter(step);position:absolute;top:-10px;left:14px;background:var(--accent);color:#06201d;font:700 11px/18px var(--mono);width:18px;height:18px;border-radius:50%;text-align:center}
  .step-name{display:block;font:700 14px/1.2 var(--sans);color:var(--txt);margin-bottom:6px}
  .step-detail{display:block;font-size:12.5px;color:var(--txt-2)}

  /* -- lens tabs + donuts -- */
  .lens-tabs{display:flex;gap:8px;margin:18px 0 14px}
  .lens-tab{font:600 13px/1 var(--sans);padding:9px 16px;border-radius:999px;border:1px solid var(--line-2);background:transparent;color:var(--txt-2);cursor:pointer}
  .lens-tab.active{background:var(--accent-soft);border-color:var(--accent-bd);color:var(--txt)}
  .lens-panel[hidden]{display:none}
  .donut-row{display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start}
  .donut{flex:0 0 auto}
  .donut-seg{cursor:pointer;transition:opacity .15s}
  .donut-seg:hover, .donut-seg:focus{opacity:.8;outline:none}
  .donut-total{fill:var(--txt);font:700 28px/1 var(--mono)}
  .tool-list{flex:1 1 260px;min-width:220px}
  .tool-list[hidden]{display:none}
  .tool-list .bucket-block[hidden]{display:none}
  .tool-list h4{margin-top:0}
  .tool-list .tool-row{padding:8px 0;border-bottom:1px solid var(--line)}
  .tool-list .tool-row:last-child{border-bottom:none}
  .tool-list .tool-key{font:600 13px/1.3 var(--mono);color:var(--accent-bright)}
  .tool-list .tool-desc{display:block;font-size:12.5px;color:var(--txt-2);margin-top:2px}

  /* -- expandable cards -- */
  .card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-top:16px}
  .card-toggle{display:block;width:100%;text-align:left;background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px;cursor:pointer;color:inherit;font:inherit}
  .card-toggle:hover{border-color:var(--accent-bd)}
  .card-detail{background:var(--panel-2);border:1px solid var(--line);border-top:none;border-radius:0 0 var(--r) var(--r);padding:14px 16px;margin-top:-14px;font-size:13px;color:var(--txt-2)}
  .card-detail[hidden]{display:none}

  /* -- certification coverage bars -- */
  .cert-toggle{display:grid;grid-template-columns:80px 1fr 90px 100px;gap:12px;align-items:center;width:100%;text-align:left;background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:12px 16px;cursor:pointer;color:inherit;font:inherit;margin-top:8px}
  .cert-name{font:700 14px/1 var(--mono);color:var(--txt)}
  .cert-body{font-size:12px;color:var(--muted)}
  .cert-bar{display:flex;gap:3px}
  .bar-seg{width:16px;height:8px;border-radius:2px;background:var(--line-2)}
  .bar-seg.filled{background:var(--accent)}
  .cert-level{font-size:12.5px;color:var(--txt-2);text-align:right}
  .cert-detail{background:var(--panel-2);border:1px solid var(--line);border-top:none;padding:12px 16px 16px}
  .cert-detail[hidden]{display:none}

  /* -- ISO accordion -- */
  .iso-toggle{display:flex;justify-content:space-between;align-items:center;width:100%;text-align:left;background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:12px 16px;cursor:pointer;color:inherit;font:inherit;margin-top:6px}
  .iso-clause{font:600 13.5px/1.3 var(--sans)}
  .iso-detail{background:var(--panel-2);border:1px solid var(--line);border-top:none;padding:10px 16px 14px;font-size:13px;color:var(--txt-2)}
  .iso-detail[hidden]{display:none}

  @media(max-width:640px){.cert-toggle{grid-template-columns:1fr;gap:6px}}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <span class="brand"><span class="d">&#9672;</span> Kern</span>
    <nav><a href="/">Home</a><a href="/demo">Live console</a></nav>
  </div>
</header>
<main class="wrap">
"""

_FOOT = """
<footer><div class="wrap">
  SCOR&reg; is a framework of the Association for Supply Chain Management (ASCM).
  APICS, CPIM, CSCP, and CLTD are ASCM certifications. SCPro is a CSCMP
  certification. CPSM is an Institute for Supply Management (ISM) certification.
  Kern is not affiliated with, endorsed by, or certified by ASCM, CSCMP, or ISM --
  this page shows how Kern's own capabilities relate to those public frameworks.
  Full technical detail: <code>documentation/KERN_NIVEL_REFERENCIA_SCM.md</code>.
</div></footer>
</main>
</body>
</html>
"""


def _tool_list_html(order: Sequence[str], group_by: str, *, list_id: str) -> str:
    """One <div data-bucket="..."> block per bucket in `order`, each hidden by
    default and unhidden by static/how_it_works.js when the matching donut
    segment is clicked. `group_by` is "domain_area" or "scor_bucket"."""
    blocks: list[str] = []
    for bucket in order:
        rows = "".join(
            f'<div class="tool-row"><span class="tool-key">{escape(t.label)}</span>'
            f'<span class="tool-desc">{escape(t.one_liner)}</span></div>'
            for t in TOOLS
            if getattr(t, group_by) == bucket
        )
        blocks.append(f'<div class="bucket-block" data-bucket="{escape(bucket)}" hidden>{rows}</div>')
    return f'<div class="tool-list" id="{escape(list_id)}" hidden>{"".join(blocks)}</div>'


def render_how_it_works_html() -> str:
    domain_tally = tally_by_domain_area()
    scor_tally = tally_by_scor_bucket()

    stepper_html = _stepper([
        ("Brief", "A plain-language request, optionally with a data file attached."),
        ("Classify", "The orchestrator matches the brief's intent to one of 41 registered tools."),
        ("Run", "The matched tool's own prepare -> run pipeline executes against the data provided."),
        ("QA", "The tool's own QA gate checks the result. If QA fails, nothing ships -- zero deliverables."),
        ("Deliver", "A grounded, cited deliverable -- or, if execution wasn't safe, ranked options, a "
                     "prepared handoff, or an escalation."),
    ])

    domain_donut = _donut_svg(
        [(area, domain_tally[area]) for area in DOMAIN_AREA_ORDER], element_id="donut-domain"
    )
    scor_donut = _donut_svg(
        [(bucket, scor_tally[bucket]) for bucket in SCOR_BUCKET_ORDER], element_id="donut-scor"
    )
    domain_list = _tool_list_html(DOMAIN_AREA_ORDER, "domain_area", list_id="donut-domain-list")
    scor_list = _tool_list_html(SCOR_BUCKET_ORDER, "scor_bucket", list_id="donut-scor-list")

    guided_donut = _donut_svg(
        [("EXECUTED", 1), ("OPTIONS", 1), ("HANDOFF", 1), ("ESCALATED", 1)], element_id="donut-guided"
    )

    grounding_cards = "".join([
        _expandable_card(
            "Knowledge graph", "33 curated SCM sources + the codebase itself",
            "<p>Every deliverable carries L3 citations, gated by <code>citation_gate</code> "
            "(minimum 2 citations, max 2 hops, an EXCLUDED_CONCEPTS false-friend filter) so a "
            "result is never grounded in an off-topic source.</p>",
            card_id="card-knowledge",
        ),
        _expandable_card(
            "Client profiles", "Per-client cost/capacity parameters that persist",
            "<p>Holding rate, order cost, service level, lead time, warehouse capacity -- "
            "asked once, stored under <code>clients/&lt;slug&gt;/profile.json</code>, and "
            "merged into every later run so the same brief produces a client-specific answer "
            "instead of a generic one.</p>",
            card_id="card-profiles",
        ),
        _expandable_card(
            "QA gate", "\"QA fails => no deliverable\"",
            "<p>Enforced in one place by the orchestrator. A result that fails its own tool's "
            "QA check is refused, not shipped.</p>",
            card_id="card-qa",
        ),
        _expandable_card(
            "Optional LLM layer", "Works with or without one",
            "<p>The deterministic engine is the core. An optional LLM provider sharpens intent "
            "routing and the narrative summary when configured, but every model in the engine "
            "runs the same with or without it.</p>",
            card_id="card-llm",
        ),
    ])

    cert_bars = "".join(
        _coverage_bar(cert, bar_id=f"cert-{cert.name.lower()}") for cert in CERTIFICATIONS
    )
    iso_9001_rows = "".join(
        _iso_accordion_row(clause, row_id=f"iso9001-{i}") for i, clause in enumerate(ISO_9001_CLAUSES)
    )
    iso_28000_rows = "".join(
        _iso_accordion_row(clause, row_id=f"iso28000-{i}") for i, clause in enumerate(ISO_28000_ELEMENTS)
    )
    gap_rows = "".join(
        f'<div class="panel" style="margin-top:10px">'
        f"<h3>{escape(gap.name)}</h3>"
        f'<p class="sub">{escape(gap.current_state)}</p>'
        f'<p class="muted" style="font-size:12.5px;margin-top:6px">Asked for by: {escape(gap.standard)}</p>'
        "</div>"
        for gap in HONEST_GAPS
    )

    return (
        _HEAD
        + f"""
<section style="padding-top:44px">
  <span class="eyebrow">How Kern Works</span>
  <h1>A brief goes in. A grounded, QA-gated deliverable comes out.</h1>
  <p class="sub" style="max-width:64ch;font-size:1.05rem">
    Kern is an agentic supply-chain engine: {len(TOOLS)} agent-routable capabilities behind one
    pipeline, grounded in a knowledge graph of 33 curated sources, adapted to each client's own
    cost and capacity parameters.
  </p>
  {stepper_html}
</section>

<section>
  <span class="eyebrow">{len(TOOLS)} capabilities, two lenses</span>
  <h2 style="margin-top:10px">The same {len(TOOLS)} tools, grouped two ways</h2>
  <div class="lens-tabs" role="tablist">
    <button type="button" class="lens-tab active" data-lens="domain" role="tab" aria-selected="true">By domain area</button>
    <button type="button" class="lens-tab" data-lens="scor" role="tab" aria-selected="false">By SCOR Digital Standard process</button>
  </div>
  <div class="lens-panel" data-lens="domain">
    <div class="donut-row">{domain_donut}{domain_list}</div>
  </div>
  <div class="lens-panel" data-lens="scor" hidden>
    <div class="donut-row">{scor_donut}{scor_list}</div>
    <p class="sub" style="margin-top:14px;max-width:64ch">
      <b>Transform</b> (production/manufacturing execution) is Kern's thinnest SCOR category by
      design -- Kern is a planning and decision-support engine, not a manufacturing execution
      system (MES).
    </p>
  </div>
  <p class="muted" style="font-size:12.5px;margin-top:10px">Click a segment to see its tools. Each tool sits in exactly one bucket per lens.</p>
</section>

<section>
  <span class="eyebrow">Grounding &amp; adaptation</span>
  <h2 style="margin-top:10px">How it's fed, and how it adapts to your context</h2>
  <div class="card-grid">{grounding_cards}</div>
</section>

<section>
  <span class="eyebrow">Never-unprotected</span>
  <h2 style="margin-top:10px">Every result is one of four outcomes</h2>
  <div class="donut-row">
    {guided_donut}
    <div class="tool-list" style="min-width:220px">
      <div class="tool-row"><span class="tool-key">EXECUTED</span><span class="tool-desc">The agent did it autonomously.</span></div>
      <div class="tool-row"><span class="tool-key">OPTIONS</span><span class="tool-desc">Ranked choices for a human to pick.</span></div>
      <div class="tool-row"><span class="tool-key">HANDOFF</span><span class="tool-desc">A prepared, ready-to-approve next step.</span></div>
      <div class="tool-row"><span class="tool-key">ESCALATED</span><span class="tool-desc">Routed to a human with an SLA.</span></div>
    </div>
  </div>
  <p class="muted" style="font-size:12.5px;margin-top:10px">
    Structural -- the four possible outcome shapes -- not a measured run-frequency split.
  </p>
</section>

<section>
  <span class="eyebrow">Standards &amp; certifications</span>
  <h2 style="margin-top:10px">How this maps to SCOR and five SCM certifications</h2>
  <p class="sub" style="max-width:64ch">
    SCOR Digital Standard's own <b>Orchestrate</b> category -- added for the "digital" layer:
    twins, analytics, agents, resilience -- is where Kern's agentic guarantees (the QA gate,
    never-unprotected, signed staged writeback) land, ahead of what most commercial suites do
    here.
  </p>
  <h3 style="margin-top:22px">Certification coverage</h3>
  <p class="sub">A tool can touch more than one certification's body of knowledge at once, so
    this is a coverage level per certification, not a tool count.</p>
  <div>{cert_bars}</div>
  <h3 style="margin-top:26px">ISO 9001 alignment</h3>
  <div>{iso_9001_rows}</div>
  <h3 style="margin-top:22px">ISO 28000 alignment</h3>
  <div>{iso_28000_rows}</div>
  <h3 style="margin-top:26px">Honest gaps</h3>
  <p class="sub">What Kern does not cover yet, and which standard asks for it.</p>
  <div>{gap_rows}</div>
</section>
"""
        + _FOOT
    )
```

Note: the `<script src="...">` tag for `webapp/static/how_it_works.js` is added
in Task 5 by editing the `_FOOT` constant directly — Task 4 only needs the page
to render correctly without it (the interactivity JS is additive, not required
for the HTML/content assertions this task's tests check).

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v`
Expected: PASS (16 tests total)

- [ ] **Step 5: Commit**

```bash
git add webapp/how_it_works_page.py tests/test_how_it_works_page.py
git commit -m "feat: assemble render_how_it_works_html() with all 6 content sections"
```

---

## Task 5: Interactivity script

**Files:**
- Create: `webapp/static/how_it_works.js`
- Modify: `webapp/how_it_works_page.py` (`_FOOT`, to load the script)

**Interfaces:**
- Consumes: the DOM structure produced by Task 4 (`.lens-tab[data-lens]`, `.lens-panel[data-lens]`, `.donut-seg[data-label]`, `svg.donut#<id>` paired with `.tool-list#<id>-list` containing `.bucket-block[data-bucket]`, `.card-toggle[data-target]`/`.card-detail#<id>`, `.cert-toggle[data-target]`/`.cert-detail#<id>`, `.iso-toggle[data-target]`/`.iso-detail#<id>`).
- Produces: no exported interface (a plain IIFE, loaded once per page).

- [ ] **Step 1: Write the implementation**

There is no Python/pytest harness for client-side JS in this repo (confirmed:
no `.js` test runner is configured anywhere under `tests/`), so this task has
no automated red/green cycle — it is verified manually in Task 7 via the
browser, per this project's web-testing convention ("start the dev server and
use the feature in a browser before reporting the task as complete").

Create `webapp/static/how_it_works.js`:

```javascript
// Interactivity for GET /how-it-works: donut lens tabs, click-to-expand
// tool lists on donut segments, and expand/collapse for the grounding
// cards / certification bars / ISO accordion. Vanilla JS, no dependencies
// (matches this project's zero-external-JS-library convention).
(function () {
  "use strict";

  function bindToggle(selector) {
    document.querySelectorAll(selector).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var targetId = btn.getAttribute("data-target");
        var target = document.getElementById(targetId);
        if (!target) {
          return;
        }
        var isHidden = target.hasAttribute("hidden");
        if (isHidden) {
          target.removeAttribute("hidden");
          btn.setAttribute("aria-expanded", "true");
        } else {
          target.setAttribute("hidden", "");
          btn.setAttribute("aria-expanded", "false");
        }
      });
    });
  }

  function bindDonutLensTabs() {
    var tabs = document.querySelectorAll(".lens-tab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var lens = tab.getAttribute("data-lens");
        tabs.forEach(function (t) {
          var isActive = t === tab;
          t.classList.toggle("active", isActive);
          t.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        document.querySelectorAll(".lens-panel").forEach(function (panel) {
          panel.hidden = panel.getAttribute("data-lens") !== lens;
        });
      });
    });
  }

  function showBucket(svgId, label) {
    var listContainer = document.getElementById(svgId + "-list");
    if (!listContainer) {
      return;
    }
    listContainer.hidden = false;
    listContainer.querySelectorAll(".bucket-block").forEach(function (block) {
      block.hidden = block.getAttribute("data-bucket") !== label;
    });
  }

  function bindDonutSegmentExpand() {
    document.querySelectorAll(".donut-seg").forEach(function (seg) {
      seg.addEventListener("click", function () {
        var svg = seg.closest("svg");
        if (!svg) {
          return;
        }
        showBucket(svg.id, seg.getAttribute("data-label"));
      });
      seg.addEventListener("keydown", function (evt) {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          var svg = seg.closest("svg");
          if (svg) {
            showBucket(svg.id, seg.getAttribute("data-label"));
          }
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindToggle(".card-toggle");
    bindToggle(".cert-toggle");
    bindToggle(".iso-toggle");
    bindDonutLensTabs();
    bindDonutSegmentExpand();
  });
})();
```

- [ ] **Step 2: Wire the script tag into the page**

In `webapp/how_it_works_page.py`, edit `_FOOT` to load the script right before
`</body>`:

```python
_FOOT = """
<footer><div class="wrap">
  SCOR&reg; is a framework of the Association for Supply Chain Management (ASCM).
  APICS, CPIM, CSCP, and CLTD are ASCM certifications. SCPro is a CSCMP
  certification. CPSM is an Institute for Supply Management (ISM) certification.
  Kern is not affiliated with, endorsed by, or certified by ASCM, CSCMP, or ISM --
  this page shows how Kern's own capabilities relate to those public frameworks.
  Full technical detail: <code>documentation/KERN_NIVEL_REFERENCIA_SCM.md</code>.
</div></footer>
</main>
<script src="/static/how_it_works.js"></script>
</body>
</html>
"""
```

- [ ] **Step 3: Add a regression test that the script tag is present**

Append to `tests/test_how_it_works_page.py`:

```python
def test_page_loads_the_interactivity_script() -> None:
    html = render_how_it_works_html()
    assert '<script src="/static/how_it_works.js"></script>' in html
```

- [ ] **Step 4: Run the full page test file**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v`
Expected: PASS (17 tests total)

- [ ] **Step 5: Commit**

```bash
git add webapp/static/how_it_works.js webapp/how_it_works_page.py tests/test_how_it_works_page.py
git commit -m "feat: add how-it-works page interactivity (tabs, expand/collapse)"
```

---

## Task 6: Wire the route + HTTP-level tests

**Files:**
- Modify: `webapp/app.py`
- Modify: `tests/test_how_it_works_page.py`

**Interfaces:**
- Consumes: `render_how_it_works_html` from `webapp.how_it_works_page` (Task 4).
- Produces: `GET /how-it-works` (FastAPI route, no params, returns `HTMLResponse`).

- [ ] **Step 1: Write the failing HTTP-level tests**

Append to `tests/test_how_it_works_page.py`:

```python
from fastapi.testclient import TestClient  # noqa: E402

from webapp.app import app  # noqa: E402

client = TestClient(app)


def test_how_it_works_route_returns_200_html() -> None:
    resp = client.get("/how-it-works")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_how_it_works_route_serves_the_interactivity_script() -> None:
    resp = client.get("/static/how_it_works.js")
    assert resp.status_code == 200
    assert "bindDonutLensTabs" in resp.text


def test_how_it_works_route_body_matches_direct_render() -> None:
    """HTMLResponse must not transform the string in any way -- catches a
    route-wiring bug (wrong render call, double-escaping, truncation) that
    the Task 4 direct-render tests can't see since they never go through
    the HTTP layer."""
    resp = client.get("/how-it-works")
    assert resp.text == render_how_it_works_html()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v -k "route"`
Expected: FAIL with 404 (`assert 404 == 200`) since the route does not exist yet.

- [ ] **Step 3: Add the route**

In `webapp/app.py`, add the import alongside the other page-renderer imports
(near line 85, next to the `stocky_alternative_page` import):

```python
from webapp.how_it_works_page import render_how_it_works_html  # noqa: E402
```

Then add the route immediately after the existing `@app.get("/stocky-alternative")`
handler (immediately before the `app.mount("/static", ...)` line):

```python
@app.get("/how-it-works")
def how_it_works_page() -> HTMLResponse:
    """Internal/onboarding page explaining how Kern works -- see
    webapp/how_it_works_page.py's module docstring. Fully static (no request
    params): every number it shows is curated at write time against the
    actual code, not computed per-request."""
    return HTMLResponse(render_how_it_works_html())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. py -m pytest tests/test_how_it_works_page.py -v`
Expected: PASS (20 tests total)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `PYTHONPATH=. py -m pytest tests/ -q`
Expected: all tests pass (no regressions in unrelated modules)

- [ ] **Step 6: Run ruff on touched files**

Run: `py -m ruff check webapp/how_it_works_data.py webapp/how_it_works_page.py webapp/app.py tests/test_how_it_works_data.py tests/test_how_it_works_page.py`
Expected: no errors (fix any import-order/unused-import findings and re-run)

- [ ] **Step 7: Commit**

```bash
git add webapp/app.py tests/test_how_it_works_page.py
git commit -m "feat: mount GET /how-it-works"
```

---

## Task 7: Manual browser verification

**Files:** none (verification only; fix-forward commits only if an issue is found)

- [ ] **Step 1: Start the dev server**

Use the project's preview tooling to start `uvicorn webapp.app:app --reload`
(from the repo root) and open `http://localhost:8000/how-it-works`.

- [ ] **Step 2: Verify the domain-area donut**

Confirm the donut renders 9 segments, hovering each shows a native tooltip
with its label/count/percentage, and clicking a segment reveals that domain
area's tool list below (with no other bucket's tools showing). Confirm the
center total reads 41.

- [ ] **Step 3: Verify the SCOR lens tab**

Click "By SCOR Digital Standard process." Confirm the panel switches, the
second donut renders 7 segments (Plan/Order-Fulfill/Orchestrate/Transform/
Source/Return/Outside SCOR scope) totaling 41, and the "Transform is Kern's
thinnest category" caption is visible.

- [ ] **Step 4: Verify the never-unprotected donut**

Confirm it shows 4 equal segments (EXECUTED/OPTIONS/HANDOFF/ESCALATED) and the
"structural, not a measured run-frequency split" caption is present.

- [ ] **Step 5: Verify the grounding cards, certification bars, and ISO accordion**

Click each of the 4 grounding cards and confirm each expands/collapses on
repeated clicks. Click each of the 5 certification bars and confirm the
Covered/Gaps lists appear. Click a few ISO accordion rows and confirm they
expand/collapse independently of each other.

- [ ] **Step 6: Check for console errors and CSP violations**

Use the browser console and network tools to confirm there are no JS errors
and no `Content-Security-Policy` violation warnings.

- [ ] **Step 7: Responsive check**

Resize to 320px, 768px, and 1440px widths. Confirm no horizontal overflow and
the certification bars' grid collapses to a single column below 640px (per
the `@media(max-width:640px)` rule added in Task 4).

- [ ] **Step 8: Screenshot**

Take a full-page screenshot at the default desktop width as verification
evidence.

- [ ] **Step 9: Fix forward if anything failed**

If any check in Steps 2-7 fails, fix the specific file (data/render/JS) and
re-run the affected pytest file plus this manual check before proceeding.
Commit any fix with a `fix:` message.

- [ ] **Step 10: Final full-suite check and push**

Run: `PYTHONPATH=. py -m pytest tests/ -q`
Expected: all green.

```bash
git push -u origin feat/how-it-works-page
```

(Opening the PR itself is a separate, explicit step for whoever runs this
plan — do not open it automatically as part of this task.)
