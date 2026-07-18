# Launch Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Kern agent tool #41 `launch_readiness` — cross a campaign launch-date list against real supplier lead time and campaign-shaped stock coverage, returning a green/yellow/red readiness verdict per SKU.

**Architecture:** A pandas-only `jobs/launch_readiness_job.py` reads two CSVs (campaign calendar + inventory/lead-time), shapes demand by the campaign lift (`src.sop_engine.demand_plan.price_cut_lift_ratio`), folds lead-time variability into demand-during-lead-time (`src.risk_period.demand_over_risk_period`), projects coverage vs the launch date (`src.safety_stock.safety_stock`), and emits a protected `GuidedOutcome` per SKU. A `scm_agent/tool_options.py` builder aggregates the per-SKU outcomes into one run-level outcome; `scm_agent/tools.py` wires it as a `Tool` registered in `build_default_registry()`; `scm_agent/citation_gate.py` anchors its L3 citations. No new math — every quantitative step reuses an existing engine function.

**Tech Stack:** Python 3.11+, pandas, scipy (via safety_stock), pytest. Frozen dataclasses + pure functions (repo `src/` style).

**Spec:** `docs/superpowers/specs/2026-07-18-launch-readiness-design.md` (adversarially audited; read it before starting).

## Global Constraints

- **Worktree:** all work happens in `C:/Users/Gamer/Music/scm/.wt-launch-readiness` on branch `feat/launch-readiness` (already created, based on `main` 801a73b). Run every command from that directory.
- **Tests:** `PYTHONPATH=. python -m pytest tests/<file> -q`. Never push straight to `main`: feature branch → draft PR → CI green on py3.11/3.12/3.13 → squash-merge.
- **ASCII-only in code strings** (Windows cp1252 breaks on em dashes) — use `-`, not `—`, in any string a deck/CSV/console may print. Markdown docs are utf-8 and fine.
- **`src/`-leaf imports only in the job** (prod-boot safety, spec §9): `jobs/launch_readiness_job.py` imports only stdlib + pandas + `src.*` (`deliverable`, `escalation`, `export`, `guided`, `risk_period`, `safety_stock`, `sop_engine.demand_plan`). Do NOT import `jobs.qa` or any other `jobs.*` module (keeps the import graph leaf-clean; the job's `verify()` reuses `src.guided.verify_guided` + explicit checks instead of `jobs.qa.coverage_gate` — a deliberate refinement of spec §7.1 for import hygiene, giving the identical guarantee because escalations are built via `escalate()` which always sets `route_to`/`sla`).
- **Lift is a fraction:** `expected_lift_pct = 0.20` means +20%. Floor every resolved lift at `-1.0`. Reject a direct `expected_lift_pct > 5.0` as a percent-vs-fraction typo.
- **safety_stock `risk_periods=1.0` is mandatory** — `risk.demand_std` is already aggregated over the risk period (spec §5 step 3). Any other value double-counts.
- **Scope:** NO marketing-tool integration. The module docstring and the deck residual must state the output is a report a human forwards.
- **Verdict constants:** `VERDICT_GREEN = "green"`, `VERDICT_YELLOW = "yellow"`, `VERDICT_RED = "red"`.

---

### Task 1: Core per-SKU engine (data model + verdict logic + `run`)

**Files:**
- Create: `jobs/launch_readiness_job.py`
- Test: `tests/test_launch_readiness_job.py`

**Interfaces:**
- Consumes (existing, verified): `src.sop_engine.demand_plan.price_cut_lift_ratio(current_price, proposed_price, elasticity) -> float`; `src.risk_period.demand_over_risk_period(mean_demand_per_period, demand_std_per_period, mean_lead_time, lead_time_std=0.0, review_period=0.0) -> RiskPeriodStats(mean_demand, demand_std, ...)`; `src.safety_stock.safety_stock(demand_std_per_period, cycle_service_level, risk_periods=1.0) -> SafetyStockResult(safety_stock, ...)`; `src.guided.{as_executed, as_options, ExecutionOption, GuidedOutcome, EXECUTED, verify_guided}`; `src.escalation.{OPERATIONAL, escalate}`.
- Produces (later tasks rely on these exact names/types): `LaunchInput` (frozen dataclass, fields below), `LaunchLine` (frozen), `LaunchReadinessReport` (frozen), `run(payload: dict) -> LaunchReadinessReport`, and the module constants `VERDICT_GREEN/VERDICT_YELLOW/VERDICT_RED`, `_LIFT_FLOOR`, `_MAX_SANE_LIFT`, `_DEFAULT_SERVICE_LEVEL`.

- [ ] **Step 1: Write the failing tests for the verdict logic**

Create `tests/test_launch_readiness_job.py`:

```python
"""Tests for the launch_readiness agent job (Kern tool #41)."""

from datetime import date

import pytest

from jobs import launch_readiness_job as lrj
from src.guided import EXECUTED, ESCALATED, OPTIONS

AS_OF = date(2026, 7, 1)


def _run_one(inp: "lrj.LaunchInput", *, service_level: float = 0.95):
    report = lrj.run({"records": [inp], "as_of_date": AS_OF, "target_service_level": service_level})
    assert len(report.lines) == 1
    return report.lines[0]


def _covered(**kw) -> "lrj.LaunchInput":
    base = dict(product_id="sku", launch_date=date(2026, 7, 31), lift_pct=0.0, has_coverage=True,
                on_hand=200.0, daily_demand=10.0, lead_time_days=7.0, demand_std=0.0, lead_time_std=0.0)
    base.update(kw)
    return lrj.LaunchInput(**base)


def test_green_when_on_hand_covers_to_launch():
    line = _run_one(_covered(on_hand=1000.0))  # 100 days cover vs 30 to launch
    assert line.verdict == lrj.VERDICT_GREEN
    assert line.outcome.status == EXECUTED
    assert line.days_of_cover == 100.0


def test_yellow_order_now_when_on_hand_above_reorder_point():
    line = _run_one(_covered(on_hand=200.0))  # cover 20 < 30; lead 7 fits; reorder = 10*7 = 70
    assert line.verdict == lrj.VERDICT_YELLOW
    assert line.outcome.status == OPTIONS
    assert line.reorder_point == 70.0
    rec = next(o for o in line.outcome.options if o.recommended)
    assert "order" in rec.label.lower()


def test_yellow_limited_allocation_when_below_reorder_point():
    line = _run_one(_covered(on_hand=50.0))  # cover 5 < 30; reorder 70; on_hand 50 < 70
    assert line.verdict == lrj.VERDICT_YELLOW
    rec = next(o for o in line.outcome.options if o.recommended)
    assert "limited" in rec.label.lower()
    assert line.outcome.confidence < 0.8


def test_red_when_lead_time_exceeds_days_to_launch():
    line = _run_one(_covered(launch_date=date(2026, 7, 4), on_hand=20.0, lead_time_days=14.0))
    # 3 days to launch, cover 2 (< 3), lead 14 -> exposure_gap 11
    assert line.verdict == lrj.VERDICT_RED
    assert line.outcome.status == ESCALATED
    assert line.exposure_gap_days == 11.0
    assert line.outcome.escalation.route_to == "marketing campaign owner"
    assert line.outcome.escalation.sla
    assert len(line.outcome.escalation.options) >= 2


def test_red_when_missing_coverage_data():
    inp = lrj.LaunchInput(product_id="ghost", launch_date=date(2026, 7, 31), lift_pct=0.0, has_coverage=False)
    line = _run_one(inp)
    assert line.verdict == lrj.VERDICT_RED
    assert line.outcome.status == ESCALATED
    assert line.days_of_cover is None and line.lead_time_days is None
    assert len(line.outcome.escalation.options) >= 2


def test_red_when_lift_wipes_out_demand_is_not_green():
    line = _run_one(_covered(on_hand=1000.0, lift_pct=-1.0))  # shaped = 0 -> degenerate
    assert line.verdict == lrj.VERDICT_RED
    assert line.outcome.status == ESCALATED


def test_lead_time_variability_raises_the_reorder_point():
    low = _run_one(_covered(demand_std=2.0, lead_time_std=0.0))
    high = _run_one(_covered(demand_std=2.0, lead_time_std=3.0))
    assert high.reorder_point > low.reorder_point
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -q`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError: module 'jobs.launch_readiness_job' has no attribute ...`

- [ ] **Step 3: Write the module (data model + verdict engine + run)**

Create `jobs/launch_readiness_job.py`:

```python
"""Launch Readiness agent job (Kern tool #41): campaign launch dates x real lead
time x projected stock coverage -> green/yellow/red verdict per SKU.

Reads two CSVs with pandas directly (deliberately NOT via jobs/intake.py): a
campaign calendar (product_id, launch_date, optional lift/discount) and an
inventory/lead-time file (product_id, on_hand, daily_demand, lead_time_days,
optional demand_std/lead_time_std). Shapes demand by the campaign lift
(src.sop_engine.demand_plan.price_cut_lift_ratio), folds lead-time variability
into demand-during-lead-time (src.risk_period.demand_over_risk_period), projects
coverage vs the launch date (src.safety_stock.safety_stock), and emits a
protected GuidedOutcome per SKU (EXECUTED green / OPTIONS yellow / ESCALATED red).

SCOPE: this tool does NOT integrate with any marketing tool. There is no Slack /
email / marketing-CRM connector anywhere in Kern. The output is a report/handoff
a human forwards; do not describe it as "communicating with marketing".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, datetime

from src.escalation import OPERATIONAL, escalate
from src.guided import EXECUTED, ExecutionOption, GuidedOutcome, as_executed, as_options
from src.risk_period import demand_over_risk_period
from src.safety_stock import safety_stock
from src.sop_engine.demand_plan import price_cut_lift_ratio

VERDICT_GREEN = "green"
VERDICT_YELLOW = "yellow"
VERDICT_RED = "red"
_VERDICTS = (VERDICT_GREEN, VERDICT_YELLOW, VERDICT_RED)

_LIFT_FLOOR = -1.0
_MAX_SANE_LIFT = 5.0            # expected_lift_pct is a FRACTION; > 5 (=500%) is almost surely a percent typo
_DEFAULT_SERVICE_LEVEL = 0.95
_ROUTE = "marketing campaign owner"
_SLA = "before the campaign go/no-go"


@dataclass(frozen=True)
class LaunchInput:
    """One campaign SKU joined to its inventory row (has_coverage=False => no inventory row)."""

    product_id: str
    launch_date: date
    lift_pct: float                 # resolved & floored at -1.0
    has_coverage: bool
    on_hand: float = 0.0
    daily_demand: float = 0.0
    lead_time_days: float = 0.0
    demand_std: float = 0.0
    lead_time_std: float = 0.0


@dataclass(frozen=True)
class LaunchLine:
    """One SKU's readiness verdict + the protected outcome behind it."""

    product_id: str
    launch_date: str                # ISO string for CSV/deck
    verdict: str                    # green | yellow | red
    lift_pct: float
    shaped_daily_demand: float
    days_until_launch: float
    lead_time_days: float | None    # None for the no-coverage case
    days_of_cover: float | None
    reorder_point: float | None
    exposure_gap_days: float | None
    on_hand: float | None
    outcome: GuidedOutcome
    reason: str


@dataclass(frozen=True)
class LaunchReadinessReport:
    lines: tuple[LaunchLine, ...]
    n_green: int
    n_yellow: int
    n_red: int
    worst_exposure_gap: tuple[str, float]   # (product_id, days); ("n/a", 0.0) if none
    summary: str


def _missing_data_line(inp: LaunchInput, days_until: float) -> LaunchLine:
    reason = "no coverage data for this SKU - cannot assess launch readiness."
    options = [
        ExecutionOption(
            label="Supply coverage data and re-run", score=2.0, recommended=True,
            summary="add the on-hand + real lead-time row for this SKU and re-run launch readiness.",
            action="provide the inventory row (on_hand, daily_demand, lead_time_days) for this SKU",
            tradeoffs="one data step; unblocks a real verdict"),
        ExecutionOption(
            label="Hold the launch decision", score=1.0,
            summary="hold this SKU's go/no-go until coverage data exists.",
            action="defer the launch decision for this SKU",
            tradeoffs="no launch risk taken blind; delays the decision"),
    ]
    outcome = escalate(f"{inp.product_id}: {reason}", OPERATIONAL, reason,
                       route_to=_ROUTE, options=options, sla=_SLA, confidence=0.5)
    return LaunchLine(
        product_id=inp.product_id, launch_date=inp.launch_date.isoformat(), verdict=VERDICT_RED,
        lift_pct=inp.lift_pct, shaped_daily_demand=0.0, days_until_launch=days_until,
        lead_time_days=None, days_of_cover=None, reorder_point=None, exposure_gap_days=None,
        on_hand=None, outcome=outcome, reason=reason)


def _degenerate_line(inp: LaunchInput, shaped: float, days_until: float) -> LaunchLine:
    reason = (f"campaign lift ({inp.lift_pct:+.0%}) wipes out demand (shaped <= 0) - data error, "
              "cannot assess coverage.")
    options = [
        ExecutionOption(
            label="Fix the campaign lift input and re-run", score=2.0, recommended=True,
            summary="the resolved lift drives projected demand to zero or below; correct it and re-run.",
            action="correct expected_lift_pct / discount inputs for this SKU",
            tradeoffs="one data fix; unblocks a real verdict"),
        ExecutionOption(
            label="Hold the launch decision", score=1.0,
            summary="hold this SKU's go/no-go until the lift input is fixed.",
            action="defer the launch decision for this SKU",
            tradeoffs="no launch risk taken blind; delays the decision"),
    ]
    outcome = escalate(f"{inp.product_id}: {reason}", OPERATIONAL, reason,
                       route_to=_ROUTE, options=options, sla=_SLA, confidence=0.4)
    return LaunchLine(
        product_id=inp.product_id, launch_date=inp.launch_date.isoformat(), verdict=VERDICT_RED,
        lift_pct=inp.lift_pct, shaped_daily_demand=shaped, days_until_launch=days_until,
        lead_time_days=inp.lead_time_days, days_of_cover=None, reorder_point=None,
        exposure_gap_days=None, on_hand=inp.on_hand, outcome=outcome, reason=reason)


def _assess_sku(inp: LaunchInput, *, service_level: float, as_of: date) -> LaunchLine:
    days_until = float((inp.launch_date - as_of).days)
    if not inp.has_coverage:
        return _missing_data_line(inp, days_until)

    shaped = inp.daily_demand * (1.0 + inp.lift_pct)
    if shaped <= 0:
        return _degenerate_line(inp, shaped, days_until)

    risk = demand_over_risk_period(shaped, inp.demand_std, inp.lead_time_days, inp.lead_time_std)
    # risk.demand_std is ALREADY aggregated over the risk period -> risk_periods MUST be 1.0.
    ss = safety_stock(demand_std_per_period=risk.demand_std,
                      cycle_service_level=service_level, risk_periods=1.0).safety_stock
    reorder_point = risk.mean_demand + ss
    days_of_cover = inp.on_hand / shaped
    exposure_gap = max(0.0, inp.lead_time_days - days_until)

    common = dict(
        product_id=inp.product_id, launch_date=inp.launch_date.isoformat(), lift_pct=inp.lift_pct,
        shaped_daily_demand=shaped, days_until_launch=days_until, lead_time_days=inp.lead_time_days,
        days_of_cover=days_of_cover, reorder_point=reorder_point, exposure_gap_days=exposure_gap,
        on_hand=inp.on_hand)

    if days_of_cover >= days_until:
        reason = (f"on-hand covers {days_of_cover:.0f} day(s) >= {days_until:.0f} to launch; "
                  "ready without a reorder.")
        return LaunchLine(**common, verdict=VERDICT_GREEN, reason=reason,
                          outcome=as_executed(f"{inp.product_id}: launch-ready. {reason}", confidence=0.9))

    if exposure_gap > 0:
        reason = (f"lead time {inp.lead_time_days:.0f}d exceeds {days_until:.0f}d to launch by "
                  f"{exposure_gap:.0f}d - a reorder cannot land in time.")
        options = [
            ExecutionOption(
                label=f"Delay the launch by ~{exposure_gap:.0f} day(s)", score=2.0, recommended=True,
                summary="push the launch date so a standard replenishment can arrive.",
                action=f"move the launch out by >= {exposure_gap:.0f} day(s)",
                tradeoffs="protects day-one availability; slips the campaign date"),
            ExecutionOption(
                label="Launch with limited allocation", score=1.0,
                summary=f"launch only where the {inp.on_hand:.0f} on-hand can serve (limited channels/stores).",
                action="restrict the launch to the channels current on-hand covers",
                tradeoffs="keeps the date; narrower launch footprint"),
        ]
        outcome = escalate(f"{inp.product_id}: launch at risk. {reason}", OPERATIONAL, reason,
                           route_to=_ROUTE, options=options, sla=_SLA, confidence=0.7)
        return LaunchLine(**common, verdict=VERDICT_RED, outcome=outcome, reason=reason)

    order_now = ExecutionOption(
        label="Place the replenishment order now", score=2.0,
        summary=f"a reorder ({inp.lead_time_days:.0f}d) lands before launch; order to the "
                f"{reorder_point:.0f} reorder point.",
        action="place the replenishment order now", tradeoffs="covers the launch; commits the spend")
    limited = ExecutionOption(
        label="Launch with limited allocation", score=1.0,
        summary=f"on-hand {inp.on_hand:.0f} is below the {reorder_point:.0f} reorder point - launch "
                "narrow while stock rebuilds.",
        action="restrict the launch to the channels current on-hand covers",
        tradeoffs="lower spend now; narrower launch footprint")
    if inp.on_hand >= reorder_point:
        items, conf = [replace(order_now, recommended=True), limited], 0.8
    else:
        items, conf = [replace(limited, recommended=True), order_now], 0.6
    reason = (f"on-hand covers {days_of_cover:.0f}d < {days_until:.0f}d to launch, but lead time "
              f"{inp.lead_time_days:.0f}d fits - a reorder can arrive in time.")
    outcome = as_options(f"{inp.product_id}: orderable before launch. {reason}", items, confidence=conf)
    return LaunchLine(**common, verdict=VERDICT_YELLOW, outcome=outcome, reason=reason)


def run(payload: dict) -> LaunchReadinessReport:
    """Assess every SKU in the payload (sorted by product_id for a deterministic report)."""
    service_level = float(payload.get("target_service_level", _DEFAULT_SERVICE_LEVEL))
    as_of = payload["as_of_date"]
    lines = tuple(sorted(
        (_assess_sku(i, service_level=service_level, as_of=as_of) for i in payload["records"]),
        key=lambda line: line.product_id))
    n_green = sum(1 for line in lines if line.verdict == VERDICT_GREEN)
    n_yellow = sum(1 for line in lines if line.verdict == VERDICT_YELLOW)
    n_red = sum(1 for line in lines if line.verdict == VERDICT_RED)
    gaps = [(line.product_id, line.exposure_gap_days) for line in lines if line.exposure_gap_days]
    worst = max(gaps, key=lambda t: t[1], default=("n/a", 0.0))
    summary = (f"Launch readiness over {len(lines)} SKU(s): {n_green} green, {n_yellow} yellow, "
               f"{n_red} red.")
    return LaunchReadinessReport(lines=lines, n_green=n_green, n_yellow=n_yellow, n_red=n_red,
                                 worst_exposure_gap=worst, summary=summary)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -q`
Expected: PASS (7 tests). If `test_lead_time_variability_raises_the_reorder_point` is off, recompute by hand: with shaped=10, lead=7, `sigma_x = sqrt(7*demand_std^2 + lead_time_std^2*10^2)`, `ss = 1.645*sigma_x`, `reorder = 70 + ss`.

- [ ] **Step 5: Commit**

```bash
git add jobs/launch_readiness_job.py tests/test_launch_readiness_job.py
git commit -m "feat(launch_readiness): per-SKU green/yellow/red verdict engine"
```

---

### Task 2: CSV ingestion (`prepare_records` + `prepare`)

**Files:**
- Modify: `jobs/launch_readiness_job.py` (add ingestion above `run`)
- Test: `tests/test_launch_readiness_job.py` (append)

**Interfaces:**
- Consumes: `pandas`; `LaunchInput` and `price_cut_lift_ratio` from Task 1.
- Produces: `prepare_records(campaigns: pd.DataFrame, inventory: pd.DataFrame, params: dict | None) -> dict` and `prepare(data_path: str, params: dict | None) -> dict`. The payload dict shape is `{"records": list[LaunchInput], "target_service_level": float, "as_of_date": date}` — exactly what `run` consumes.

- [ ] **Step 1: Write the failing ingestion tests**

Append to `tests/test_launch_readiness_job.py`:

```python
import pandas as pd


def _campaigns_df(**over) -> pd.DataFrame:
    d = {"product_id": ["a", "b"], "launch_date": ["2026-07-31", "2026-07-31"]}
    d.update(over)
    return pd.DataFrame(d)


def _inventory_df() -> pd.DataFrame:
    return pd.DataFrame({
        "product_id": ["a", "b"],
        "on_hand": [1000, 50],
        "daily_demand": [10, 10],
        "lead_time_days": [7, 7],
    })


def test_prepare_records_joins_and_defaults_lift_to_zero():
    payload = lrj.prepare_records(_campaigns_df(), _inventory_df(), {"as_of_date": "2026-07-01"})
    assert {r.product_id for r in payload["records"]} == {"a", "b"}
    assert all(r.lift_pct == 0.0 and r.has_coverage for r in payload["records"])
    assert payload["target_service_level"] == 0.95


def test_prepare_records_direct_lift_is_a_fraction_not_a_percent():
    df = _campaigns_df(expected_lift_pct=[0.20, 0.0])
    payload = lrj.prepare_records(df, _inventory_df(), {"as_of_date": "2026-07-01"})
    a = next(r for r in payload["records"] if r.product_id == "a")
    assert a.lift_pct == 0.20  # 1.2x, NOT 21x


def test_prepare_records_derives_lift_from_discount_trio():
    df = _campaigns_df(current_price=[100.0, 0.0], proposed_price=[80.0, 0.0], elasticity=[-2.0, 0.0])
    payload = lrj.prepare_records(df, _inventory_df(), {"as_of_date": "2026-07-01"})
    a = next(r for r in payload["records"] if r.product_id == "a")
    assert a.lift_pct == pytest.approx((80.0 / 100.0) ** -2.0 - 1.0)  # 0.5625


def test_prepare_records_rejects_percent_typo_lift():
    df = _campaigns_df(expected_lift_pct=[20.0, 0.0])  # 20 meaning 20% -> nonsense as a fraction
    with pytest.raises(ValueError, match="fraction"):
        lrj.prepare_records(df, _inventory_df(), {"as_of_date": "2026-07-01"})


def test_prepare_records_keeps_a_campaign_sku_with_no_inventory_row():
    inv = _inventory_df().iloc[[0]]  # only "a" has an inventory row
    payload = lrj.prepare_records(_campaigns_df(), inv, {"as_of_date": "2026-07-01"})
    b = next(r for r in payload["records"] if r.product_id == "b")
    assert b.has_coverage is False


def test_prepare_records_errors_on_missing_required_columns():
    with pytest.raises(ValueError, match="launch_date"):
        lrj.prepare_records(pd.DataFrame({"product_id": ["a"]}), _inventory_df(), {})


def test_prepare_reads_two_csvs(tmp_path):
    camp = tmp_path / "campanas.csv"; _campaigns_df().to_csv(camp, index=False)
    inv = tmp_path / "inv.csv"; _inventory_df().to_csv(inv, index=False)
    payload = lrj.prepare(str(camp), {"inventory_path": str(inv), "as_of_date": "2026-07-01"})
    assert len(payload["records"]) == 2


def test_prepare_requires_inventory_path(tmp_path):
    camp = tmp_path / "campanas.csv"; _campaigns_df().to_csv(camp, index=False)
    with pytest.raises(ValueError, match="inventory_path"):
        lrj.prepare(str(camp), {})
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -k prepare -q`
Expected: FAIL with `AttributeError: module 'jobs.launch_readiness_job' has no attribute 'prepare_records'`

- [ ] **Step 3: Add ingestion to `jobs/launch_readiness_job.py`**

Add `import pandas as pd` to the imports, and insert these helpers/functions immediately above `def run(`:

```python
_PRODUCT_COLS = ("product_id", "sku", "SKU", "item", "Product", "product")
_LAUNCH_COLS = ("launch_date", "launch", "campaign_date", "go_live", "start_date")
_LIFT_COLS = ("expected_lift_pct", "lift_pct", "expected_lift", "lift")
_CURPRICE_COLS = ("current_price", "price", "list_price", "base_price")
_PROPPRICE_COLS = ("proposed_price", "promo_price", "launch_price", "discount_price")
_ELAST_COLS = ("elasticity", "price_elasticity", "elast")
_ONHAND_COLS = ("on_hand", "quantity", "qty", "stock", "units", "On Hand")
_DEMAND_COLS = ("daily_demand", "demand", "demand_rate", "daily_sales", "run_rate")
_LEAD_COLS = ("lead_time_days", "lead_time", "leadtime", "lead")
_DEMANDSTD_COLS = ("demand_std", "demand_sigma", "std_demand", "sigma_d")
_LEADSTD_COLS = ("lead_time_std", "lead_std", "sigma_lead", "sigma_l")


def _pick(df: pd.DataFrame, override: object, candidates: tuple[str, ...]) -> str | None:
    if override:
        return str(override) if str(override) in df.columns else None
    return next((c for c in candidates if c in df.columns), None)


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()


def prepare_records(campaigns: pd.DataFrame, inventory: pd.DataFrame,
                    params: dict | None = None) -> dict:
    """Sniff both files, left-join campaigns->inventory on product_id, resolve lift, bake config."""
    params = params or {}
    c_prod = _pick(campaigns, params.get("product_col"), _PRODUCT_COLS)
    c_launch = _pick(campaigns, params.get("launch_col"), _LAUNCH_COLS)
    missing = [n for n, c in (("product_id", c_prod), ("launch_date", c_launch)) if c is None]
    if missing:
        raise ValueError(
            f"campanas.csv: could not find {', '.join(missing)} "
            f"(columns seen: {list(campaigns.columns)[:10]})")
    c_lift = _pick(campaigns, params.get("lift_col"), _LIFT_COLS)
    c_cur = _pick(campaigns, params.get("current_price_col"), _CURPRICE_COLS)
    c_prop = _pick(campaigns, params.get("proposed_price_col"), _PROPPRICE_COLS)
    c_el = _pick(campaigns, params.get("elasticity_col"), _ELAST_COLS)

    i_prod = _pick(inventory, params.get("product_col"), _PRODUCT_COLS)
    i_on = _pick(inventory, params.get("on_hand_col"), _ONHAND_COLS)
    i_dem = _pick(inventory, params.get("demand_col"), _DEMAND_COLS)
    i_lead = _pick(inventory, params.get("lead_col"), _LEAD_COLS)
    inv_missing = [n for n, c in (("product_id", i_prod), ("on_hand", i_on),
                                  ("daily_demand", i_dem), ("lead_time_days", i_lead)) if c is None]
    if inv_missing:
        raise ValueError(
            f"inventory csv: could not find {', '.join(inv_missing)} "
            f"(columns seen: {list(inventory.columns)[:10]})")
    i_dstd = _pick(inventory, params.get("demand_std_col"), _DEMANDSTD_COLS)
    i_lstd = _pick(inventory, params.get("lead_std_col"), _LEADSTD_COLS)

    inv_by_id = {str(r[i_prod]): r for _, r in inventory.iterrows()}
    records: list[LaunchInput] = []
    bad_lift: list[str] = []
    for _, row in campaigns.iterrows():
        pid = str(row[c_prod])
        launch = _parse_date(row[c_launch])
        lift = 0.0
        if c_lift and pd.notna(row[c_lift]):
            raw = float(row[c_lift])
            if raw > _MAX_SANE_LIFT:
                bad_lift.append(f"{pid} ({raw})")
                continue
            lift = max(_LIFT_FLOOR, raw)
        elif c_cur and c_prop and c_el and all(pd.notna(row[c]) for c in (c_cur, c_prop, c_el)):
            try:
                lift = max(_LIFT_FLOOR,
                           price_cut_lift_ratio(float(row[c_cur]), float(row[c_prop]), float(row[c_el])))
            except ValueError:
                lift = 0.0
        inv = inv_by_id.get(pid)
        if inv is None:
            records.append(LaunchInput(product_id=pid, launch_date=launch, lift_pct=lift, has_coverage=False))
        else:
            records.append(LaunchInput(
                product_id=pid, launch_date=launch, lift_pct=lift, has_coverage=True,
                on_hand=float(inv[i_on]), daily_demand=float(inv[i_dem]), lead_time_days=float(inv[i_lead]),
                demand_std=float(inv[i_dstd]) if i_dstd and pd.notna(inv[i_dstd]) else 0.0,
                lead_time_std=float(inv[i_lstd]) if i_lstd and pd.notna(inv[i_lstd]) else 0.0))
    if bad_lift:
        raise ValueError(
            f"expected_lift_pct must be a fraction (0.20 = +20%); suspicious value(s) > "
            f"{_MAX_SANE_LIFT}: {', '.join(bad_lift)}")
    if not records:
        raise ValueError("no campaign rows found")

    as_of_raw = params.get("as_of_date")
    as_of = _parse_date(as_of_raw) if as_of_raw else date.today()
    return {
        "records": records,
        "target_service_level": float(params.get("target_service_level", _DEFAULT_SERVICE_LEVEL)),
        "as_of_date": as_of,
    }


def prepare(data_path: str, params: dict | None = None) -> dict:
    """Read the campaign CSV (data_path) and the inventory CSV (params['inventory_path'])."""
    params = params or {}
    inv_path = params.get("inventory_path")
    if not inv_path:
        raise ValueError("params['inventory_path'] (the inventory/lead-time CSV) is required")
    return prepare_records(pd.read_csv(data_path), pd.read_csv(inv_path), params)
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add jobs/launch_readiness_job.py tests/test_launch_readiness_job.py
git commit -m "feat(launch_readiness): two-CSV ingestion with lift resolution + left join"
```

---

### Task 3: QA gate (`verify`)

**Files:**
- Modify: `jobs/launch_readiness_job.py` (add `verify` after `run`)
- Test: `tests/test_launch_readiness_job.py` (append)

**Interfaces:**
- Consumes: `src.guided.verify_guided`, `EXECUTED`; `LaunchReadinessReport`/`LaunchLine` from Task 1.
- Produces: `verify(report: LaunchReadinessReport) -> list[str]` (empty == passed).

- [ ] **Step 1: Write the failing verify tests**

Append to `tests/test_launch_readiness_job.py`:

```python
from dataclasses import replace as _replace

from src.guided import as_executed as _as_executed


def _healthy_report():
    return lrj.run({"records": [_covered(on_hand=1000.0)], "as_of_date": AS_OF})


def test_verify_passes_a_healthy_report():
    assert lrj.verify(_healthy_report()) == []


def test_verify_flags_a_red_line_mislabelled_executed():
    rep = lrj.run({"records": [_covered(launch_date=date(2026, 7, 4), on_hand=20.0, lead_time_days=14.0)],
                   "as_of_date": AS_OF})
    broken = _replace(rep.lines[0], outcome=_as_executed("nope"))
    rep = _replace(rep, lines=(broken,))
    assert any("EXECUTED" in m for m in lrj.verify(rep))


def test_verify_flags_an_empty_reason():
    rep = _healthy_report()
    rep = _replace(rep, lines=(_replace(rep.lines[0], reason="  "),))
    assert any("reason" in m for m in lrj.verify(rep))


def test_verify_flags_an_invalid_verdict():
    rep = _healthy_report()
    rep = _replace(rep, lines=(_replace(rep.lines[0], verdict="purple"),))
    assert any("verdict" in m for m in lrj.verify(rep))
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -k verify -q`
Expected: FAIL with `AttributeError: ... has no attribute 'verify'`

- [ ] **Step 3: Add `verify` to `jobs/launch_readiness_job.py`**

Add `from src.guided import ... verify_guided` (extend the existing guided import to include `verify_guided`), then add after `run`:

```python
def verify(report: LaunchReadinessReport) -> list[str]:
    """QA gate. Empty list = passed. Every line's outcome honours the never-unprotected
    contract; counts sum; verdict is enumerated; reason is present; a red line is never
    EXECUTED and always carries >= 2 escalation options (the builders don't enforce that)."""
    issues: list[str] = []
    if not report.lines:
        issues.append("no SKUs to assess")
    if report.n_green + report.n_yellow + report.n_red != len(report.lines):
        issues.append("verdict counts do not sum to the line count")
    for line in report.lines:
        issues.extend(f"{line.product_id}: {m}" for m in verify_guided(line.outcome))
        if line.verdict not in _VERDICTS:
            issues.append(f"{line.product_id}: invalid verdict {line.verdict!r}")
        if not line.reason.strip():
            issues.append(f"{line.product_id}: line has no reason")
        if not math.isfinite(line.days_until_launch):
            issues.append(f"{line.product_id}: non-finite days_until_launch")
        if line.verdict == VERDICT_RED:
            if line.outcome.status == EXECUTED:
                issues.append(f"{line.product_id}: red line reports EXECUTED")
            n_opts = len(line.outcome.escalation.options) if line.outcome.escalation else 0
            if n_opts < 2:
                issues.append(f"{line.product_id}: red line has {n_opts} option(s), need >= 2")
    return issues
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs/launch_readiness_job.py tests/test_launch_readiness_job.py
git commit -m "feat(launch_readiness): QA gate (verify) enforcing the guided contract"
```

---

### Task 4: Deliverables (`write_operational` + `build_deck`)

**Files:**
- Modify: `jobs/launch_readiness_job.py`
- Test: `tests/test_launch_readiness_job.py` (append)

**Interfaces:**
- Consumes: `src.deliverable.{DataSource, Deliverable, Finding, Kpi}`, `src.export.write_summary_csv`, `pathlib.Path`.
- Produces: `write_operational(report, out_dir, client="Client") -> dict[str, Path]` and `build_deck(report, *, client="Client", prepared="", citations=(), confidence=0.8) -> Deliverable`.

- [ ] **Step 1: Write the failing deliverable tests**

Append:

```python
from pathlib import Path as _Path

from src.deliverable import Deliverable as _Deliverable


def test_write_operational_renders_na_for_missing_coverage(tmp_path):
    inp = lrj.LaunchInput(product_id="ghost", launch_date=date(2026, 7, 31), lift_pct=0.0, has_coverage=False)
    rep = lrj.run({"records": [inp], "as_of_date": AS_OF})
    out = lrj.write_operational(rep, tmp_path, client="Acme")
    text = _Path(out["csv"]).read_text(encoding="utf-8")
    assert "ghost" in text and "N/A" in text and "red" in text


def test_build_deck_is_an_ascii_deliverable():
    rep = lrj.run({"records": [_covered(on_hand=1000.0)], "as_of_date": AS_OF})
    deck = lrj.build_deck(rep, client="Acme", citations=("Chopra & Meindl, Ch.7",), confidence=0.8)
    assert isinstance(deck, _Deliverable)
    md = deck.to_markdown()
    assert md.isascii()
    assert "Launch Readiness" in md and "## Coverage & handoff" in md
    assert "does NOT communicate" in md.replace("does not", "does NOT")  # scope statement present
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -k "operational or deck" -q`
Expected: FAIL with `AttributeError: ... 'write_operational'`

- [ ] **Step 3: Add deliverables to `jobs/launch_readiness_job.py`**

Add imports at the top: `from pathlib import Path`, `from src.deliverable import DataSource, Deliverable, Finding, Kpi`, `from src.export import write_summary_csv`. Then add:

```python
def write_operational(report: LaunchReadinessReport, out_dir, client: str = "Client") -> dict[str, "Path"]:
    """One row per SKU: verdict, timing, coverage, and the recommended action. N/A for missing fields."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)

    def fmt(v):
        return "N/A" if v is None else round(v, 1)

    rows = [
        {
            "product_id": line.product_id,
            "launch_date": line.launch_date,
            "verdict": line.verdict,
            "days_until_launch": round(line.days_until_launch, 1),
            "lead_time_days": fmt(line.lead_time_days),
            "days_of_cover": fmt(line.days_of_cover),
            "reorder_point": fmt(line.reorder_point),
            "exposure_gap_days": fmt(line.exposure_gap_days),
            "recommended_action": line.reason,
        }
        for line in report.lines
    ]
    return {"csv": write_summary_csv(rows, d / "launch_readiness.csv")}


def build_deck(report: LaunchReadinessReport, *, client: str = "Client", prepared: str = "",
               citations: tuple[str, ...] = (), confidence: float = 0.8) -> Deliverable:
    """Compose the launch-readiness study: which SKUs are ready, orderable, or at risk."""
    worst_id, worst_gap = report.worst_exposure_gap
    summary = (f"Launch readiness over {len(report.lines)} SKU(s): {report.n_green} green, "
               f"{report.n_yellow} yellow, {report.n_red} red.")
    findings = [
        Finding("Red - not ready for launch",
                f"{report.n_red} SKU(s) cannot be available for their launch date as planned.",
                impact="route to the marketing campaign owner before the go/no-go"),
        Finding("Yellow - orderable in time",
                f"{report.n_yellow} SKU(s) need a reorder or a limited launch to make the date.",
                impact="place the replenishment now or launch narrow"),
    ]
    if worst_gap > 0:
        findings.append(Finding(
            f"Worst lead-time exposure: {worst_id}",
            f"a standard reorder lands {worst_gap:.0f} day(s) after launch.",
            impact="the single biggest date risk - address this first"))
    kpis = (
        Kpi("SKUs", f"{len(report.lines)}", rationale="Campaign SKUs assessed"),
        Kpi("Green (ready)", f"{report.n_green}", target="maximize", rationale="On-hand covers to launch"),
        Kpi("Yellow (orderable)", f"{report.n_yellow}", target="minimize",
            rationale="Needs a reorder or a limited launch"),
        Kpi("Red (at risk)", f"{report.n_red}", target="0", rationale="Cannot be ready as planned"),
        Kpi("Worst exposure gap", f"{worst_id}: {worst_gap:.0f}d", target="0",
            rationale="Largest lead-time-vs-launch shortfall"),
    )
    data_sources = (
        DataSource("Campaign launch dates + expected lift", "marketing calendar", "per campaign"),
        DataSource("On-hand, baseline demand, real lead time", "WMS / ERP + supplier records", "weekly"),
    )
    recommendations = (
        "Route every red SKU to the marketing campaign owner before the go/no-go.",
        "Place the recommended reorders for the yellow SKUs now, or launch them with limited allocation.",
        "Re-run once launch dates or lead times change; the verdict can flip.",
    )
    return Deliverable(
        title="Launch Readiness", client=client, summary=summary, findings=tuple(findings),
        kpis=kpis, data_sources=data_sources, recommendations=recommendations,
        citations=tuple(citations), confidence=confidence,
        residual="This is a report a human forwards - Kern does NOT communicate with any marketing "
                 "tool (no Slack / email / CRM connector exists). Confirm launch dates and lead times, "
                 "and route red SKUs to whoever controls the campaign calendar.",
        prepared=prepared)
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_job.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs/launch_readiness_job.py tests/test_launch_readiness_job.py
git commit -m "feat(launch_readiness): operational CSV + exec deck (scope-capped residual)"
```

---

### Task 5: Run-level aggregation (`launch_readiness_options`)

**Files:**
- Modify: `scm_agent/tool_options.py`
- Test: `tests/test_launch_readiness_tool.py` (create — aggregation section)

**Interfaces:**
- Consumes: `LaunchReadinessReport` from Task 1; `src.escalation.{OPERATIONAL, escalate}`, `src.guided.{ExecutionOption, GuidedOutcome, as_executed}`, `dataclasses.replace`.
- Produces: `scm_agent.tool_options.launch_readiness_options(report) -> GuidedOutcome`.

- [ ] **Step 1: Write the failing aggregation tests**

Create `tests/test_launch_readiness_tool.py`:

```python
"""Tests for the launch_readiness aggregation + agent-tool wiring (Kern tool #41)."""

from datetime import date

import pandas as pd

from jobs import launch_readiness_job as lrj
from scm_agent import intent, llm, tool_options, tools
from scm_agent.orchestrator import Orchestrator
from src.guided import ESCALATED, EXECUTED, OPTIONS

AS_OF = date(2026, 7, 1)


def _covered(**kw):
    base = dict(product_id="sku", launch_date=date(2026, 7, 31), lift_pct=0.0, has_coverage=True,
                on_hand=200.0, daily_demand=10.0, lead_time_days=7.0, demand_std=0.0, lead_time_std=0.0)
    base.update(kw)
    return lrj.LaunchInput(**base)


def _report(inputs):
    return lrj.run({"records": inputs, "as_of_date": AS_OF})


def test_aggregate_escalates_when_any_sku_is_red():
    rep = _report([
        _covered(product_id="ok", on_hand=1000.0),
        _covered(product_id="late", launch_date=date(2026, 7, 4), on_hand=20.0, lead_time_days=14.0),
    ])
    out = tool_options.launch_readiness_options(rep)
    assert out.status == ESCALATED
    assert out.escalation.route_to == "marketing campaign owner"
    assert out.escalation.sla and out.escalation.reason
    assert len(out.options) >= 2  # options carried at the top level too


def test_aggregate_is_options_when_yellow_but_no_red():
    rep = _report([_covered(product_id="y", on_hand=200.0)])  # yellow
    out = tool_options.launch_readiness_options(rep)
    assert out.status == OPTIONS


def test_aggregate_is_executed_when_all_green():
    rep = _report([_covered(product_id="g", on_hand=1000.0)])
    out = tool_options.launch_readiness_options(rep)
    assert out.status == EXECUTED
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_tool.py -k aggregate -q`
Expected: FAIL with `AttributeError: module 'scm_agent.tool_options' has no attribute 'launch_readiness_options'`

- [ ] **Step 3: Add the aggregator to `scm_agent/tool_options.py`**

At the top of `scm_agent/tool_options.py`, extend the imports:
- change `from src.escalation import maybe_escalate_data_quality` to `from src.escalation import OPERATIONAL, escalate, maybe_escalate_data_quality`
- change `from src.guided import ExecutionOption, GuidedOutcome, Residual, as_handoff, as_options` to add `as_executed`: `from src.guided import ExecutionOption, GuidedOutcome, Residual, as_executed, as_handoff, as_options`

Then add (anywhere among the other `*_options` builders):

```python
def launch_readiness_options(report: object) -> GuidedOutcome:
    """Aggregate the per-SKU launch verdicts into one run-level outcome.

    Any red SKU -> ESCALATED (routed to the campaign owner), bundling every red into one
    packet and carrying those options at the top level too (mirrors src.escalation._maybe_
    escalate's "nothing silently vanishes"). Else any yellow -> the worst-margin yellow SKU's
    own OPTIONS outcome. Else all green -> EXECUTED.
    """
    reds = [line for line in report.lines if line.verdict == "red"]
    if reds:
        reason = f"{len(reds)} SKU(s) at launch risk: " + "; ".join(
            f"{line.product_id} - {line.reason}" for line in reds)
        options = [
            ExecutionOption(
                label="Route the red SKUs to the campaign owner", score=2.0, recommended=True,
                summary=f"{len(reds)} SKU(s) cannot be ready for their launch date as planned.",
                action="send the red-SKU handoff to the marketing campaign owner",
                tradeoffs="protects day-one availability; needs a calendar/allocation decision"),
            ExecutionOption(
                label="Proceed only with the launch-ready SKUs", score=1.0,
                summary=f"launch the {report.n_green} green SKU(s) on schedule; hold the rest.",
                action="launch green SKUs only; defer yellow/red",
                tradeoffs="keeps the date for what is ready; narrows the launch"),
        ]
        outcome = escalate(report.summary, OPERATIONAL, reason, route_to="marketing campaign owner",
                           sla="before the campaign go/no-go", options=options, confidence=0.7)
        return replace(outcome, options=list(outcome.escalation.options))
    yellows = [line for line in report.lines if line.verdict == "yellow"]
    if yellows:
        return min(yellows, key=lambda line: (line.days_of_cover or 0.0) - line.days_until_launch).outcome
    return as_executed(f"All {len(report.lines)} SKU(s) are launch-ready.", confidence=0.9)
```

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_tool.py -k aggregate -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scm_agent/tool_options.py tests/test_launch_readiness_tool.py
git commit -m "feat(launch_readiness): run-level guided aggregation (any-red -> escalate)"
```

---

### Task 6: Wire the Tool + citation anchors + registry (registration lands with its anchor + count bump)

**Files:**
- Modify: `scm_agent/tools.py` (adapters + `launch_readiness_tool()` + register + import)
- Modify: `scm_agent/citation_gate.py` (`TOOL_CONCEPTS` + `EXCLUDED_CONCEPTS`)
- Modify: `tests/test_price_watch_tool.py:159-161` (count 40 -> 41 + rename)
- Test: `tests/test_launch_readiness_tool.py` (append routing + e2e), `tests/test_citation_gate.py` (append false-friend)

**Interfaces:**
- Consumes: `launch_readiness_job` (Tasks 1-4), `tool_options.launch_readiness_options` (Task 5), `Tool`, `Prepared`, `Produced`, `replace`.
- Produces: `scm_agent.tools.launch_readiness_tool() -> Tool` registered in `build_default_registry()`; `TOOL_CONCEPTS["launch_readiness"]` + `EXCLUDED_CONCEPTS["launch_readiness"]`.

> **Why these land together:** `tests/test_citation_gate.py:58` asserts `registered == set(TOOL_CONCEPTS)`, and `tests/test_price_watch_tool.py:161` asserts `len(reg.list()) == 40`. Registering the 41st tool breaks both unless the anchor entry and the count bump land in the same commit.

- [ ] **Step 1: Write the failing routing + e2e + false-friend tests**

Append to `tests/test_launch_readiness_tool.py`:

```python
def test_registry_registers_launch_readiness():
    reg = tools.build_default_registry()
    assert "launch_readiness" in {t.key for t in reg.list()}


def test_brief_routes_to_launch_readiness():
    reg = tools.build_default_registry()
    res = intent.classify(
        "launch readiness check: will these SKUs be in stock for the campaign launch date given lead time",
        reg, llm.RulesFallback())
    assert res.job_type == "launch_readiness"


def test_end_to_end_orchestrator_run(tmp_path):
    camp = tmp_path / "campanas.csv"
    pd.DataFrame({"product_id": ["a", "b"], "launch_date": ["2026-07-31", "2026-07-04"]}).to_csv(camp, index=False)
    inv = tmp_path / "inv.csv"
    pd.DataFrame({"product_id": ["a", "b"], "on_hand": [1000, 20],
                  "daily_demand": [10, 10], "lead_time_days": [7, 14]}).to_csv(inv, index=False)
    orch = Orchestrator(tools.build_default_registry(), llm.RulesFallback(), clients_root=None)
    res = orch.run("launch readiness for the marketing campaign launch dates", data_path=str(camp),
                   job_type="launch_readiness", params={"inventory_path": str(inv), "as_of_date": "2026-07-01"},
                   out_dir=str(tmp_path / "out"))
    assert res.status == "ok"
    assert res.guided is not None and res.guided.status == "escalated"  # b is red
```

Append to `tests/test_citation_gate.py` (mirrors the real-KB integration tests at the bottom of that file; reuses its `_cite` helper):

```python
def test_launch_readiness_drops_offtopic_pricing_and_capacity_citations():
    """The launch_readiness anchors sit 3 hops from the Chopra book hub, so off-topic
    discount/pricing nodes fall outside MAX_HOPS; the two in-radius magnets
    (facility_location, capacity_planning) are dropped by EXCLUDED_CONCEPTS. Guards the
    false-friend risk documented in the design spec (2026-07-18)."""
    kb = KnowledgeBase()
    offtopic = [
        _cite("knowledge::dynamic_pricing"),
        _cite("knowledge::all_unit_quantity_discount"),
        _cite("knowledge::facility_location"),
        _cite("knowledge::capacity_planning"),
    ]
    result = filter_citations(kb, "launch_readiness", offtopic)
    assert result.kept == ()
    joined = " ".join(result.omitted)
    assert "facility_location" in joined and "capacity_planning" in joined
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_tool.py tests/test_citation_gate.py -k "launch_readiness or routes or registers or end_to_end" -q`
Expected: FAIL (tool not registered; `launch_readiness` not in TOOL_CONCEPTS).

- [ ] **Step 3a: Add the citation anchors**

In `scm_agent/citation_gate.py`, add to `TOOL_CONCEPTS` (after the `price_watch` entry):

```python
    # promotion_timing was rejected as an anchor: it is 1 hop from the Chopra & Meindl
    # book hub, so at MAX_HOPS=2 the whole Chopra book self-validates (2-hop closure
    # 330 -> 650 nodes, pulling in 39 off-topic discount/pricing/capacity magnets - the
    # shared-book-hub loophole EXCLUDED_CONCEPTS exists for). These three anchors are each
    # 3 hops from that hub; their combined closure is 330 nodes with 4 mild magnets, two of
    # which are excluded below. Verified by graph BFS 2026-07-18.
    "launch_readiness": ("new_product_forecasting", "risk_period", "lead_time_gap"),
```

and add to `EXCLUDED_CONCEPTS`:

```python
    # The two in-radius mild magnets from the launch_readiness anchors' 2-hop closure
    # (facility_location, capacity_planning) - unrelated to a stock-coverage-for-launch
    # check. Both verified to exist in the graph (test_every_excluded_concept_exists).
    "launch_readiness": ("facility_location", "capacity_planning"),
```

- [ ] **Step 3b: Wire the Tool in `scm_agent/tools.py`**

Add `launch_readiness_job,` to the `from jobs import (` block (keep it alphabetical — after `landed_cost_job,`). Then add the adapters + factory (place near `risk_tool`, following its shape exactly):

```python
# ---- launch_readiness (campaign launch date vs lead time & coverage) ----------

def _launch_readiness_prepare(request: JobRequest, provider: LLMProvider) -> Prepared:
    if not request.data_path:
        return Prepared(status="needs_data",
                        messages=["a campaign CSV (product_id, launch_date) is required"])
    if not request.params.get("inventory_path"):
        return Prepared(status="needs_data",
                        messages=["params['inventory_path'] (the inventory/lead-time CSV) is required"])
    try:
        payload = launch_readiness_job.prepare(request.data_path, request.params)
    except (ValueError, FileNotFoundError) as exc:
        return Prepared(status="needs_data", messages=[str(exc)])
    return Prepared(status="ok", payload=payload)


def _launch_readiness_run(payload: object, params: dict) -> Produced:
    report = launch_readiness_job.run(payload)
    return Produced(report=report, summary=report.summary)


def launch_readiness_tool() -> Tool:
    return Tool(
        key="launch_readiness",
        title="Launch Readiness",
        description="Cross a campaign launch-date list against real supplier lead time and "
                    "campaign-shaped stock coverage, returning a green/yellow/red readiness verdict "
                    "per SKU with ranked actions - a report a human forwards; no marketing-tool "
                    "integration.",
        intent_keywords=(
            "launch readiness", "campaign launch date", "marketing launch check",
            "will the sku be in stock for launch", "product ready for launch",
            "campaign stock coverage", "launch date lead time",
        ),
        requires_data=True,
        prepare=_launch_readiness_prepare,
        run=_launch_readiness_run,
        qa=lambda report: launch_readiness_job.verify(report),
        deliver=lambda report, out_dir, client: launch_readiness_job.write_operational(report, out_dir, client),
        deck=lambda report, out_dir, client, citations, confidence, options: replace(
            launch_readiness_job.build_deck(report, client=client, citations=tuple(citations),
                                            confidence=confidence),
            options=tuple(options),
        ).write_all(out_dir),
        # The verdict IS a set of ranked, executable choices -> surface them as the guided outcome.
        options=tool_options.launch_readiness_options,
    )
```

In `build_default_registry()`, add after `reg.register(price_watch_tool())`:

```python
    reg.register(launch_readiness_tool())
```

- [ ] **Step 3c: Bump the tool-count assertion**

In `tests/test_price_watch_tool.py`, change line 161 `assert len(reg.list()) == 40` to `== 41`, rename the function `test_registry_now_has_40_tools` to `test_registry_now_has_41_tools`, and update its docstring text ("the 40th" -> "the 41st", the count references -> 41).

- [ ] **Step 4: Run the affected suites to verify they pass**

Run: `PYTHONPATH=. python -m pytest tests/test_launch_readiness_tool.py tests/test_citation_gate.py tests/test_price_watch_tool.py -q`
Expected: PASS (routing, e2e, false-friend, `test_registry_now_has_41_tools`, `test_every_registered_tool_has_a_concept_map`, `test_every_excluded_concept_exists_in_the_real_graph`).

- [ ] **Step 5: Run the full suite to catch any other count/coverage surface**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: PASS. If `tests/test_mcp_server.py` fails on the `== 33` pin, STOP — launch_readiness must NOT be on the MCP surface for v1 (spec §8); the failure means a stray MCP registration crept in. Otherwise fix any newly-surfaced count assertion the same way as the price_watch one.

- [ ] **Step 6: Commit**

```bash
git add scm_agent/tools.py scm_agent/citation_gate.py tests/test_launch_readiness_tool.py tests/test_citation_gate.py tests/test_price_watch_tool.py
git commit -m "feat(launch_readiness): register tool #41 + citation anchors + false-friend guard"
```

---

### Task 7: Update the prose/count surfaces

**Files:**
- Modify: `CLAUDE.md:18`, `README.md:9` and `README.md:66`, `scm_agent/README.md:8`, `documentation/KERN_NIVEL_REFERENCIA_SCM.md:17`

**Interfaces:** none (docs only).

- [ ] **Step 1: Bump every prose tool count 40 -> 41**

- `CLAUDE.md:18` — "**40 agent-routable tools**" -> "**41 agent-routable tools**" (and add "launch readiness" to the parenthetical capability list).
- `README.md:9` — "**40 agent-routable capabilities**" -> "**41 agent-routable capabilities**".
- `README.md:66` — "The full list, by area (40 tools)" -> "(41 tools)"; add a `launch_readiness` bullet under the relevant area.
- `scm_agent/README.md:8` — currently a STALE "**39 registered tools**"; set it to "**41 registered tools**".
- `documentation/KERN_NIVEL_REFERENCIA_SCM.md:17` — table cell "**40** (`scm_agent/tools.py`, 40 `register()`)" -> "**41** (`scm_agent/tools.py`, 41 `register()`)".

- [ ] **Step 2: Verify no test references the prose counts**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: PASS (docs are prose; this confirms nothing regressed).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md scm_agent/README.md documentation/KERN_NIVEL_REFERENCIA_SCM.md
git commit -m "docs: bump tool count 40 -> 41 for launch_readiness"
```

---

### Task 8: Draft PR

**Files:** none (git/gh only).

- [ ] **Step 1: Re-check for concurrent-session collisions**

Run: `git -C C:/Users/Gamer/Music/scm/.wt-launch-readiness status --short && git fetch origin && git log --oneline origin/main -1`
Confirm `origin/main` is still `801a73b` (the branch base). If it moved, rebase `feat/launch-readiness` onto the new `origin/main` and re-run the full suite before pushing.

- [ ] **Step 2: Run the full suite one final time**

Run: `PYTHONPATH=. python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 3: Lint (CI scope)**

Run: `ruff check src tests examples`
Expected: no new findings in touched files.

- [ ] **Step 4: Push and open a draft PR**

```bash
git push -u origin feat/launch-readiness
gh pr create --draft --title "feat: launch_readiness (tool #41) - campaign launch-date readiness verdict" \
  --body "Implements the launch_readiness capability per docs/superpowers/specs/2026-07-18-launch-readiness-design.md and docs/superpowers/plans/2026-07-18-launch-readiness.md. Green/yellow/red per-SKU verdict crossing campaign launch dates against real lead time + campaign-shaped coverage; reuse-only (no new math); report/handoff, no marketing-tool integration. Spec adversarially audited (15 fixes). Tests: tests/test_launch_readiness_job.py, tests/test_launch_readiness_tool.py, + citation false-friend guard in tests/test_citation_gate.py."
```

- [ ] **Step 5: Confirm CI is green on py3.11/3.12/3.13, then request review** (squash-merge only after green — never straight to `main`).

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- §3 reuse map → Tasks 1-4 (each function used exactly as mapped). ✓
- §4.1 lift resolution (fraction, floor -1, >5 reject, trio, none) → Task 2. ✓
- §4.2 inventory CSV via `params["inventory_path"]` → Task 2 (`prepare`). ✓
- §4.3 params baked in `prepare` → Task 2. ✓
- §4.4 missing-coverage SKU (own line, N/A, distinct options) → Task 1 (`_missing_data_line`), Task 4 (N/A CSV). ✓
- §5 pipeline incl. `risk_periods=1.0` + degenerate guard → Task 1 (`_assess_sku`). ✓
- §6 verdict order (green→red→yellow) + protection-not-by-construction → Task 1 + Task 3 (`verify` asserts red ≥2 options). ✓
- §7.1 job functions → Tasks 1-4. ✓
- §7.2 aggregation (ESCALATED-with-carried-options) → Task 5. ✓
- §7.3 adapters + tool + `build_default_registry` (not `build_registry`) + required `description` + 6-arg deck → Task 6. ✓
- §7.4 anchors (drop promotion_timing) + EXCLUDED_CONCEPTS → Task 6. ✓
- §8 tests + count/prose bumps + MCP-not-exposed → Tasks 1-7. ✓
- §9 prod-boot leaf imports → Global Constraints + Task 1 imports (no `jobs.qa`). ✓

**2. Placeholder scan:** no "TBD"/"add error handling"/"similar to" — every code and test step shows complete content. ✓

**3. Type consistency:** `LaunchInput`/`LaunchLine`/`LaunchReadinessReport`, `run(payload: dict)`, `prepare(data_path, params)`, `verify(report)`, `write_operational(report, out_dir, client)`, `build_deck(report, *, ...)`, `launch_readiness_options(report)`, `launch_readiness_tool()` — names/signatures identical across Tasks 1-7. Verdict strings `"green"/"yellow"/"red"` used consistently (Task 5 uses literals matching the Task 1 constants). ✓
