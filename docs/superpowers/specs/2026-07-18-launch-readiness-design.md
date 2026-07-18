# launch_readiness — Design Spec

> Status: approved for planning (2026-07-18). Next step: writing-plans → implementation on a feature branch → draft PR → CI green (py3.11/3.12/3.13) → squash-merge. Never straight to `main`.
>
> This spec was adversarially audited against the live codebase (4-dimension verification pass, 2026-07-18): 31 claims checked, 15 corrected inline below. Notably, the citation-anchor set was changed after a graph BFS proved the original `promotion_timing` anchor pulled the entire Chopra & Meindl book into the 2-hop citation blast radius (§7.4).

## 1. Problem & value

Marketing schedules a campaign launch date. The product is not physically available on day one because the real supplier lead time, plus the demand lift the campaign itself creates, was never cross-checked against projected stock coverage. The launch stalls from the first day.

`launch_readiness` is a new agent-routable tool (#41) that crosses a list of SKUs + campaign launch dates against **the real lead time** and **projected stock coverage**, and returns a **green / yellow / red** verdict per SKU via the existing `GuidedOutcome` contract, so a human can act before the go/no-go.

## 2. Scope boundary (explicit — do not over-promise)

**This tool does NOT integrate with any marketing tool.** There is no Slack / email / marketing-CRM connector anywhere in the repo (verified by grep, 2026-07-18). The output is a **report / handoff that a human forwards**, exactly like every other Kern tool today. The module docstring MUST state this in words, so no one can sell it as "Kern talks to marketing on its own."

The tool is a **decision/design layer**, consistent with the atlas finding that Kern never issues POs, never runs MRP/BOM explosion, never drives a live WMS/TMS. It reads two CSVs and produces a verdict + recommended action; a human executes.

**No new math.** Every quantitative step reuses an existing engine function (§5). This tool composes them; it does not invent a formula.

## 3. Reuse map (the contract this respects)

| Concern | Existing module reused | Exact function |
|---|---|---|
| Promotional demand lift | `src/sop_engine/demand_plan.py` | `price_cut_lift_ratio(current_price, proposed_price, elasticity)` → returns a **fraction** `(p1/p0)**e − 1`; raises `ValueError` if either price ≤ 0 |
| Lead-time exposure (stochastic lead time folded into demand-during-lead-time) | `src/risk_period.py` | `demand_over_risk_period(mean_demand_per_period, demand_std_per_period, mean_lead_time, lead_time_std=0.0, review_period=0.0)` → `RiskPeriodStats(mean_demand, demand_std, risk_periods, …)` where `mean_demand = mu_d·tau` (demand-during-lead-time) and `demand_std = sigma_x` (already aggregated over the risk period) |
| Safety stock / projected coverage | `src/safety_stock.py` | `safety_stock(demand_std_per_period, cycle_service_level, risk_periods=1.0)` → `SafetyStockResult(safety_stock, …)`. **See §5 step 3 for the risk_periods=1.0 trap.** |
| Days-of-cover shape | (same formula as) `src/excess_obsolete.py` | `on_hand / daily_demand` |
| Reorder-point shape | (same formula as) `jobs/inventory_optimization.py` | `reorder = mu_x + safety_stock` |
| Exposure-gap shape | (same shape as) `src/risk.py` | `max(0, TTR − TTS)` → here `max(0, lead_time − days_until_launch)` |
| Verdict outcome | `src/guided.py` | `as_executed` / `as_options` / `as_escalation` |
| Red-SKU routing | `src/escalation.py` | `escalate(summary, OPERATIONAL, reason, route_to="marketing campaign owner", options=[...], sla="before the campaign go/no-go")` — positional `summary, trigger, reason` then keyword-only extras (see the real signature: `escalate(summary, trigger, reason, *, route_to=None, recommendation="", options=None, citations=None, sla=None, confidence=1.0)`) |
| QA gate | `jobs/qa.py` | `coverage_gate(outcome)` per line — rejects an escalation with empty `route_to`/`sla`/`reason` |
| Deck | `src/deliverable.py` + `src/export.py` | `Deliverable`/`Finding`/`Kpi`/`DataSource`, `write_summary_csv` |
| Citation anchoring | `scm_agent/citation_gate.py` | `TOOL_CONCEPTS["launch_readiness"]` + `EXCLUDED_CONCEPTS["launch_readiness"]` (§7.4) |

**Why compose `risk_period` + `safety_stock` directly rather than call `jobs/inventory_optimization.py::run()`** (decided with the user): `run()` forecasts demand itself from a full demand-history CSV and has no hook to inject an externally campaign-shaped demand number — which is the entire point of this tool. We reuse the *formula* (`mu_x + z·sigma_x`), not the pipeline. Units are consistent in **days** throughout: `daily_demand`, `lead_time_days`, `days_of_cover`, `days_until_launch` all share the same period, so `demand_over_risk_period(daily_demand, …, lead_time_days)` returns demand-during-lead-time in day units. (`safety_stock` pulls `scipy.stats.norm`; the `demand_plan` subtree pulls `numpy` — both are core deps, see §9.)

## 4. Inputs

Two CSVs, sniffed for column aliases the way `jobs/excess_obsolete_job.py::_pick_column` does (pandas-only `prepare()`, **not** `jobs/intake.py`).

### 4.1 `campanas.csv` — primary, via `JobRequest.data_path`
- `product_id` (required)
- `launch_date` (required; ISO `YYYY-MM-DD`)
- `expected_lift_pct` (optional) — a **fraction**: `0.20` means +20%. `prepare()` MUST reject / flag a value implying a nonsense multiplier (e.g. `> 5.0`) so a user who types `20` meaning "20%" does not silently get 21× demand. OR
- `current_price` + `proposed_price` + `elasticity` (optional trio) — a launch discount, from which the lift is derived via `price_cut_lift_ratio` (also a fraction; same unit as `expected_lift_pct`).

**Lift resolution priority** (decided with the user):
1. `expected_lift_pct` if present.
2. Else the discount trio via `price_cut_lift_ratio` if all three present and both prices > 0. `prepare()` catches `price_cut_lift_ratio`'s `ValueError` (price ≤ 0) and treats that row's lift as unresolved → rule 3.
3. Else **lift = 0.0** — mirrors `sop_engine/demand_plan.py`'s own `NO_SHIFT_SOURCE` / `demand_shift_pct = 0.0` contract: no signal ⇒ no shift, never a fabricated number. The line's reason states "no lift signal for this campaign; base coverage used as-is."

**Lift floor (data-quality guard):** the resolved lift is floored at `-1.0`. A mis-entered negative `expected_lift_pct` or a discount trio with a perverse elasticity can otherwise drive `1 + lift ≤ 0`, making `shaped_daily_demand ≤ 0`, `days_of_cover = inf`, and a garbage input silently reported GREEN (the opposite of the tool's purpose — see §6). Any row whose resolved `shaped_daily_demand ≤ 0` is reported as a data-quality residual, not GREEN.

### 4.2 Inventory / lead-time CSV — via `params["inventory_path"]`
The `Tool.prepare` signature carries only one `data_path`; a second CSV path rides in `params`, exactly like `price_watch_tool`'s `catalog_path` (verified: `scm_agent/types.py::JobRequest` has `data_path` + `params` + `client`).
- `product_id` (required)
- `on_hand` (required)
- `daily_demand` (required) — the pre-campaign baseline daily demand
- `lead_time_days` (required) — the **real** observed supplier lead time
- `demand_std` (optional, default 0.0)
- `lead_time_std` (optional, default 0.0)

Optional stds default to 0.0 (deterministic; never fabricated). With both stds 0.0, `demand_over_risk_period` degrades to `mu_x = daily_demand·lead_time_days`, `sigma_x = 0`, and safety stock is 0 — an honest "no variability information" result, not a hidden assumption.

### 4.3 Params
- `inventory_path` (required — the §4.2 CSV)
- `target_service_level` (optional, default 0.95) — the cycle service level for the projected reorder point
- `as_of_date` (optional, default today) — anchors `days_until_launch`; passed explicitly so tests are deterministic

`prepare()` reads `target_service_level` and `as_of_date` from `params` and **bakes both into the payload** (the same pattern `jobs/excess_obsolete_job.py::prepare` uses for `target_cover_days`/`dead_threshold_days`), so `run(payload)` needs no params of its own (§7.1).

### 4.4 SKU present in `campanas.csv` but absent from the inventory CSV
Never silently dropped (Golden Rule 14). It becomes its own line with a **RED / ESCALATED** outcome, but with a **distinct, computable option set** (the exposure-gap options in §6 need `lead_time_days`/`on_hand`, which are missing here):
- `days_of_cover`, `reorder_point`, `exposure_gap_days` are reported as **N/A** (not 0).
- Escalation options: (a) "supply the on-hand + real lead-time row for this SKU and re-run" (recommended), (b) "hold the launch decision until coverage data exists."
- Routed identically (`OPERATIONAL`, "marketing campaign owner", SLA), reason: "no coverage data for this SKU — cannot assess launch readiness."

## 5. Per-SKU pipeline

For each campaign row (in `product_id` order for a deterministic, diffable report):

1. **Shape demand**: `shaped_daily_demand = daily_demand · (1 + lift_pct)`, with `lift_pct` floored at `-1.0` (§4.1). If `shaped_daily_demand ≤ 0`, short-circuit to a data-quality residual (not GREEN).
2. **Lead-time exposure**: `risk = demand_over_risk_period(shaped_daily_demand, demand_std, lead_time_days, lead_time_std)`. This is the one engine function that folds lead-time **variability** into the demand-during-lead-time uncertainty (`sigma_x = sqrt(tau·sigma_d² + sigma_L²·mu_d²)`).
3. **Projected reorder point**: `ss = safety_stock(demand_std_per_period=risk.demand_std, cycle_service_level=target_service_level, risk_periods=1.0).safety_stock`.
   > **risk_periods MUST be 1.0 here.** `risk.demand_std` is *already* `sigma_x`, aggregated over the risk period. `safety_stock()` multiplies by `sqrt(risk_periods)`, so any value other than 1.0 double-counts the risk period. This yields `z·sigma_x` — the **same number** `src/policies.py::continuous_review_sq` produces, but policies.py reaches it via a *different* function (`src/demand_variability.py::safety_stock_risk_period`, which ignores `risk_periods` in the normal case and is fed the already-aggregated std). Do **not** "align with policies.py" by passing `risk.risk_periods` (= tau) into `safety_stock()` — that path would give `z·sigma_x·sqrt(tau)`, wrong.

   `reorder_point = risk.mean_demand + ss`.
4. **Projected days of cover**: `days_of_cover = on_hand / shaped_daily_demand` (only reached when `shaped_daily_demand > 0`, per step 1).
5. **Days until launch**: `days_until_launch = (launch_date − as_of_date).days`.
6. **Exposure gap**: `exposure_gap_days = max(0, lead_time_days − days_until_launch)` — a positive value means a standard replenishment ordered today physically cannot land before launch.

## 6. Verdict → GuidedOutcome (evaluated in this order)

Per SKU:

1. **GREEN → `as_executed`** — `days_of_cover >= days_until_launch` **and** `shaped_daily_demand > 0`: on-hand alone survives to the launch date; nothing to do. Reason cites the cover-vs-launch margin. (The `shaped_daily_demand > 0` guard is what stops the §5-step-1 degenerate case from masquerading as GREEN.)
2. **RED → `as_escalation`** via `escalate(...)` — `exposure_gap_days > 0` (a normal reorder cannot arrive in time no matter the stock math), or the §4.4 no-coverage-data case. Built via `escalate(summary, OPERATIONAL, reason, route_to="marketing campaign owner", options=[...], sla="before the campaign go/no-go")` — routing through `escalate()` guarantees `route_to`/`sla`/`reason` are non-empty so `coverage_gate` passes. Options (exposure-gap case): (a) **delay the launch by `exposure_gap_days`** (recommended), (b) **launch with limited allocation** to the channels/stores current on-hand already covers. (No-coverage-data case uses the §4.4 option set instead.)
3. **YELLOW → `as_options`** — everything else (lead time physically fits, but on-hand alone won't reach the launch date). Two ranked options:
   - **Place the replenishment order now** — recommended when `on_hand >= reorder_point`.
   - **Launch with limited allocation** — recommended instead when `on_hand < reorder_point` (already below the everyday reorder trigger); the outcome carries a lower `confidence` but stays `OPTIONS`, not `ESCALATED`, because the lead time genuinely fits.

**Protection is NOT fully by-construction — verify() must enforce the RED ≥2-options rule.** `as_options` raises on empty options, but `as_escalation`/`escalate()` do **not** reject an escalation with zero options (an empty-options `EscalationPacket` still passes `verify_guided`, because `_has_executable_path` returns True whenever `escalation is not None`). Therefore the "≥2 ranked options per red SKU" guarantee is asserted explicitly in `verify()` (§7.1), not assumed.

## 7. Module layout

Follows the exact repo recipe (CLAUDE.md "New agent tool recipe").

### 7.1 `jobs/launch_readiness_job.py`
- `prepare(data_path, params) -> dict` (payload) — reads `campanas.csv` (`data_path`) + the inventory CSV (`params["inventory_path"]`) with pandas directly, sniffs columns, **left-joins** campaigns→inventory on `product_id` (a campaign SKU with no inventory row is kept as a §4.4 line, never inner-join-dropped), resolves lift per §4.1, and **bakes `target_service_level` + `as_of_date` into the payload** (§4.3). Raises `ValueError` (→ `needs_data`) listing any missing required columns.
- `run(payload) -> LaunchReadinessReport` — runs §5–§6 per SKU (all config already in the payload). Report carries: `lines: tuple[LaunchLine, ...]` (each with `product_id`, `launch_date`, `verdict` ∈ {green, yellow, red}, `days_until_launch`, `lead_time_days`, `days_of_cover`, `reorder_point`, `exposure_gap_days`, `outcome: GuidedOutcome`, `reason: str`), plus counts `n_green/n_yellow/n_red`, `worst_exposure_gap: tuple[str, float]`, and `summary`.
- `verify(report) -> list[str]` — QA gate: (1) loops `coverage_gate` over every line's `outcome`; (2) asserts `n_green + n_yellow + n_red == len(lines)`; (3) asserts each `line.verdict ∈ {green, yellow, red}` (enum check, like `verify_price_watch`); (4) asserts each `line.reason` is non-empty (like `verify_price_watch`); (5) asserts no red line's outcome is status `EXECUTED`; (6) asserts every red line's escalation carries **≥2 options** (the §6 rule not enforced by the builders); (7) asserts finite non-negative day values.
- `write_operational(report, out_dir, client) -> {"csv": Path}` — one row per SKU (product_id, launch_date, verdict, days_until_launch, lead_time_days, days_of_cover, reorder_point, exposure_gap_days, recommended_action) via `write_summary_csv`. N/A fields (§4.4) render as `"N/A"`, not 0.
- `build_deck(report, *, client, prepared, citations, confidence) -> Deliverable` — Findings on the red/yellow counts + the worst exposure gap; KPIs (SKUs, red/yellow counts, worst gap days); DataSources (campaign calendar; on-hand + real lead time); a residual stating the human forwards this to the campaign owner and that Kern does not talk to marketing tools. Mirrors `jobs/risk_job.py::build_deck`.

### 7.2 `scm_agent/tool_options.py::launch_readiness_options(report) -> GuidedOutcome`
`Tool.options` must return **one** outcome for the whole run. The aggregation follows the **ESCALATED-with-carried-options** pattern of `src/escalation.py::_maybe_escalate` (re-route to `as_escalation` while carrying the routine options at the outcome's top level via `replace(...)` — the "nothing silently vanishes" contract). *(Note: this is NOT `price_watch_options`' R5 path, which emits `HANDOFF` for a pending ceiling-raise; a red launch SKU is a routed-to-a-named-human-with-SLA case, i.e. `ESCALATED`.)*
- If **any** line is RED → top-level outcome is **ESCALATED**, built via `escalate(..., trigger=OPERATIONAL, route_to="marketing campaign owner", sla="before the campaign go/no-go", reason=<lists every red SKU>)` so the bundled packet's `route_to`/`sla`/`reason` are guaranteed non-empty for `coverage_gate`; the routine green/yellow next steps travel at the outcome's top level.
- elif any YELLOW → **OPTIONS** surfacing the worst-margin yellow SKU's ranked choices (same "surface the top one" precedent as `risk_job`).
- else → **EXECUTED** ("all N SKU(s) are launch-ready").

### 7.3 `scm_agent/tools.py`
Add an adapter pair + tool factory, following `_risk_prepare`/`_risk_run`/`risk_tool` exactly:
- `_launch_readiness_prepare(request, provider) -> Prepared` — bridges `JobRequest` → `launch_readiness_job.prepare(request.data_path, request.params)`; returns `needs_data` on `ValueError`/`FileNotFoundError` or missing `inventory_path`.
- `_launch_readiness_run(payload, params) -> Produced` — calls `launch_readiness_job.run(payload)`, returns `Produced(report=..., summary=report.summary)`.
- `launch_readiness_tool() -> Tool` with **all required fields** (note `description` is required — no default; omitting it is a `TypeError`):
```
key="launch_readiness"
title="Launch Readiness"
description="Cross a campaign launch-date list against real supplier lead time and campaign-shaped "
            "stock coverage, returning a green/yellow/red readiness verdict per SKU with ranked "
            "actions - a report a human forwards; no marketing-tool integration."
intent_keywords=(
  "launch readiness", "campaign launch date", "marketing launch check",
  "will the sku be in stock for launch", "product ready for launch",
  "campaign stock coverage", "launch date lead time",
)
requires_data=True
prepare=_launch_readiness_prepare
run=_launch_readiness_run
qa=lambda report: launch_readiness_job.verify(report)
deliver=lambda report, out_dir, client: launch_readiness_job.write_operational(report, out_dir, client)
deck=lambda report, out_dir, client, citations, confidence, options: replace(
    launch_readiness_job.build_deck(report, client=client, citations=tuple(citations), confidence=confidence),
    options=tuple(options),
).write_all(out_dir)     # deck is a 6-arg callback (report,out_dir,client,citations,confidence,options)
options=tool_options.launch_readiness_options
```
Registered with one `reg.register(launch_readiness_tool())` call in **`build_default_registry()`** (`scm_agent/tools.py`, append after `price_watch_tool()`, ~line 2260) — *not* `build_registry` (that lives in `modes.py` and only filters an already-built registry). No routing edits.

### 7.4 `scm_agent/citation_gate.py`
```
TOOL_CONCEPTS["launch_readiness"] = (
    "new_product_forecasting", "risk_period", "lead_time_gap",
)
```
**`promotion_timing` was removed after a graph BFS** (2026-07-18): it sits 1 hop from the `book_chopra_meindl` mega-hub, so at `MAX_HOPS=2` it drags the entire Chopra book into the citation blast radius — the 2-hop closure jumps from **330 → 650 nodes**, adding 39 off-topic pricing/discount/capacity-allocation self-validators (`all_unit_quantity_discount`, `dynamic_pricing`, `capacity_allocation`, `price_optimization`, `cost_of_overstocking`, …), the exact shared-book-hub loophole `EXCLUDED_CONCEPTS` was created for. Swapping to `short_term_price_promotion` does **not** help (also 1 hop from the hub). The three retained anchors are each 3 hops from the Chopra hub; their combined 2-hop closure is 330 concept nodes with only 4 mild magnets (`capacity_planning`, `facility_location`, `forecast_for_capacity_execute_against_demand`, `price_deflation`), none strongly matching the tool's keywords.

Belt-and-suspenders, add:
```
EXCLUDED_CONCEPTS["launch_readiness"] = ("facility_location", "capacity_planning")
```
and a dedicated test (§8) proving no off-topic node survives the gate for a "launch discount / limited allocation" brief. The three anchors are verified to exist in `knowledge/scm-books/graph.json` (2026-07-18); `tests/test_citation_gate.py::test_every_anchor_concept_exists` will enforce that going forward.

## 8. Testing (`tests/test_launch_readiness_job.py`, per CONTRIBUTING.md)

Numeric, worked examples with hand-checkable arithmetic:
- **Green**: on-hand covers past launch → `EXECUTED`, no options.
- **Yellow, order-now**: cover < launch, lead time fits, `on_hand >= reorder_point` → `OPTIONS`, "place order now" recommended.
- **Yellow, limited-allocation**: cover < launch, lead time fits, `on_hand < reorder_point` → `OPTIONS`, "limited allocation" recommended, lower confidence.
- **Red, exposure gap**: `lead_time_days > days_until_launch` → `ESCALATED`, routed to "marketing campaign owner", SLA present, ≥2 options.
- **Red, no coverage data** (§4.4): SKU in campaigns, absent from inventory → `ESCALATED`, N/A day fields, the §4.4 option set (not the exposure-gap options).
- **Lift paths**: (a) `expected_lift_pct` direct → `0.20` gives `1.2×`, **not** `21×`; (b) discount trio → `price_cut_lift_ratio` matches a hand-computed `(p1/p0)**e − 1`; (c) neither → lift 0.0, base coverage used.
- **Negative/degenerate lift**: a lift ≤ −1 (or a perverse discount trio) does **not** produce GREEN — it produces a data-quality residual.
- **Lead-time variability**: non-zero `lead_time_std` raises the reorder point vs. the deterministic case.
- **QA gate**: `verify` returns `[]` on a healthy report; flags (a) a hand-broken line whose red outcome is mislabelled `EXECUTED`, (b) a red line whose escalation carries <2 options, (c) an empty `reason`, (d) an invalid `verdict`.
- **Aggregation**: `launch_readiness_options` escalates when any red present (bundled packet has non-empty route_to/sla/reason); otherwise options/executed.
- **Citation false-friend** (`tests/test_citation_gate.py`): a brief mentioning "launch discount / limited allocation" yields **none** of `{all_unit_quantity_discount, dynamic_pricing, capacity_allocation, price_optimization, cost_of_overstocking, facility_location}` surviving the gate for `launch_readiness`.
- **Determinism**: fixed `as_of_date`; ASCII-only console strings; output rows in `product_id` order.
- **Registry**: the tool registers via `build_default_registry()`, is matchable by its keywords, and round-trips `prepare→run→qa→deliver`.

**Count/prose surfaces to update in the same PR (registering #41):**
- `tests/test_price_watch_tool.py:161` — `assert len(reg.list()) == 40` → `== 41`, and rename `test_registry_now_has_40_tools` → `...41...`.
- Prose: `CLAUDE.md:18` ("40 agent-routable tools"), `README.md:66` ("40 tools"), `scm_agent/README.md:8` (currently a **stale** "39 registered tools" → set to 41), `documentation/KERN_NIVEL_REFERENCIA_SCM.md:17` ("40").
- **MCP exposure decision (v1):** launch_readiness ships **orchestrator/webapp-only, NOT on the read-only MCP surface** for v1 (keeps scope minimal; avoids touching `EXPECTED_TOOL_NAMES` + the `== 33` pin in `tests/test_mcp_server.py:104` + a `linchpin_*` tool spec). Exposing it on MCP is an explicit follow-up (mirrors how guided-parity was a deliberate later PR). No MCP files change in this PR.

Existing suite must stay green.

## 9. Risks / watch-items
- **Prod-boot safety**: `launch_readiness_job` imports stdlib + numpy/scipy/pandas/openpyxl (all **core** deps) + pure `src/` modules. `src/sop_engine/demand_plan.py` is **not** a leaf module — it transitively imports `src.liquidation` + `src.price_optimizer` (reaching `src.elasticity_batch`/`src.pricing`/`src.constraints`/`src.excess_obsolete`, and — under `TYPE_CHECKING` only — `src.pricing_intel.ledger`, the package where the optional-extra deps `extruct`/`price-parser`/`bs4` live). This subtree is **already on the prod-boot chain** via the registered `markdown_liquidation_job` and is covered by `tests/test_pricing_intel_boot_safety.py`, so launch_readiness adds **no new** optional-extra exposure. The standing rule holds: never add a module-level optional-extra import anywhere on that subtree, and keep the `pricing_intel.ledger` import in `price_optimizer` under its `TYPE_CHECKING` guard.
- **Citation false-friend**: REAL, not hypothetical (§7.4). Mitigated by dropping the `promotion_timing` anchor, a small `EXCLUDED_CONCEPTS` entry, and a dedicated gate test — not by assuming absence.
- **safety_stock risk_periods trap**: `risk_periods=1.0` is mandatory (§5 step 3); the numeric equivalence to policies.py hides that the two use different functions.
- **Two-CSV join**: a `product_id` in one file but not the other is handled explicitly via a left join + the §4.4 line, never a silent inner-join drop.
- **Concurrent sessions**: this repo runs parallel worktrees; re-check `git status` + `HANDOFF.md` immediately before finalizing, per project convention. (An unrelated pricing-doc change is already uncommitted in `HANDOFF.md` — leave it untouched.)
