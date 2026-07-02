# Linchpin — Session Handoff

**Date:** 2026-07-02 · **Repo:** `esstipi-debug/linchpin` · **Branch:** `main` @ `58ff12f` (PRs up to **#83**)
**Purpose:** pick up Linchpin work in a fresh session without re-deriving context.
**Resume here:** a world-class audit (10 sections, multi-agent + adversarial verification) scored the repo **~6.25/10**, weakest section **connectors/writeback 4.5/10**. All confirmed P0 (trust/safety) + P1 (engine correctness) findings are fixed and merged (**PR #82, #83**). **One HIGH finding was missed and is not yet fixed** (see §3). A second finding (idempotency race) is being worked in a **separate, currently-running session** — do not duplicate it; check `git log`/open PRs for a branch named like `fix/writeback-idempotency*` before starting similar work.

> A new Claude Code session in this repo also auto-loads memory: `MEMORY.md` →
> [[linchpin-project]], [[linchpin-verified-audit]], [[linchpin-coverage-roadmap]],
> [[linchpin-audit-fixes-2026-07]] (the audit + fixes below, in full detail).
> This file is the human-readable, in-repo consolidation — memory has the play-by-play.

---

## 1. What Linchpin is

Agentic supply-chain AI: a deterministic Python engine (EOQ, safety stock,
(s,Q)/(R,S), multi-echelon GSM, DDMRP, ABC-XYZ, newsvendor, queuing, scheduling,
facility location, DRP, transportation, FEFO, financial KPIs, supplier
scorecards, MCDM sourcing, landed cost, cost-to-serve, S&OP, reverse logistics,
warehouse layout, voice doc-reader) + an orchestrator agent, grounded in an
**L3 knowledge graph** (24 SCM books/sources) and packaged through a
**client-ready deliverable generator** (md + xlsx, cited). Where it can't act
itself, it hands off a ready-to-execute packet (the "never unprotected" Guided
Execution Layer, `src/guided.py`). Live **Odoo ERP connector** (`src/connectors/odoo.py`)
reads/writes through the safe-staging plane (`src/writeback.py`).
Positioned to win Upwork inventory + SCM gigs (human sells, Linchpin produces 10x)
— see [[linchpin-project]] for the current go-to-market thread (Upwork Project
Catalog packaging, Odoo Apps Store, MCP-server-with-paywall exploration).

---

## 2. Current state (verified 2026-07-02)

- **Tests:** 1128 passing, 13 skipped (`PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -q`). `ruff check src tests examples` clean.
- **Agent surface: 34 tools** (verify with `build_default_registry()` — do not trust any doc's number, including this one, without re-running that check; it has drifted before). Full list: `abc_xyz, acceptance_sampling, cost_to_serve, cycle_count, data_quality, ddmrp, dea, drp, earned_value, excess_obsolete, facility_location, fefo, financial_kpis, forecast, inventory_optimization, landed_cost, leadership_chain, learning_curve, multi_echelon, newsvendor, odoo_replenishment, pricing, queuing, reconciliation, returns, risk, scheduling, simulation, slotting, sop, sourcing, transportation, warehouse_layout, whatif`.
- **L3 graph** (`knowledge/scm-books/graph.json`): ~1847 nodes, 24 sources. Queried via `scm_agent/knowledge.py`. **Just changed:** `ground_citations()` now re-ranks by IDF weight (not raw token count) and `advise()` gates its method-rule triggers to the active tool's own keyword domain — re-verify these numbers didn't shift if you touch `knowledge.py` again.
- **Writeback safety plane** (`src/writeback.py`): `Approval` now requires a `content_hash` match **and** an HMAC-SHA256 `signature` (env `LINCHPIN_APPROVAL_SECRET`, empty = unsigned/dev). `now` defaults to the real clock. New `src/writeback_store.py::SqliteAuditLedger` gives persistent (survives-restart) audit/idempotency, wired as an optional `ledger=` param into `InMemoryStore` and both Odoo write paths via `writeback.AuditBookkeeping`.
- **Odoo connector** (`src/connectors/odoo.py`): read + both write paths (reorder points, draft POs) route through the writeback plane; `OdooClient` has a bounded timeout + retry-with-backoff for read-only ORM methods only. **Still needs**: validation against a REAL Odoo instance (user has none yet — do not treat this as urgent unless they say they have one).
- **README.md**: still describes the product as "3-4 capabilities" (the original 3 routed tools + warehouse_layout) when the registry has 34 — **known-stale, not yet fixed** (see §3).

---

## 3. Immediate next steps, in priority order

### Not fixed — pick these up first

1. **[HIGH, missed this session] Partial-failure mid-apply leaves unaudited, un-rolled-back state.**
   `src/connectors/odoo.py::_ReorderRuleStore.commit()` and `_DraftPoStore.commit()` both loop over `changeset.changes`, writing each one to Odoo (`_write_field` / `execute_kw("create")`) as they go, and only build+record the `AuditEntry` **after the loop finishes**. If change 3 of 5 raises, changes 1-2 are already live in Odoo but nothing is recorded — no audit trail, no way to know what succeeded, no rollback possible. Fix: wrap the write loop so that on any exception, everything written so far in *this* `commit()` call is rolled back before re-raising (a local compensating-transaction pattern — you already have the per-item `restore` values collected as you go, just use them on the failure path instead of discarding them). Add a test that fails write N of M partway through (a fake RPC/store that raises on the Nth call) and asserts the system ends up back in its pre-`commit()` state, not half-applied. This is the same *class* of finding as the idempotency race another session is fixing, but a different mechanism (single-call atomicity, not cross-call concurrency) — they can be fixed independently.

2. **[HIGH, cheap] `safety_stock()` survives a sign-flip mutation test.**
   The audit's mutation testing flipped a sign inside `src/safety_stock.py`'s core formula and it was NOT caught by that file's own dedicated unit tests — only two distant integration tests happened to catch it. Read `src/safety_stock.py` and `tests/test_safety_stock.py`, find the weak spot (likely an assertion that checks direction/shape but not the exact numeric output against a known book example), and add a tight numeric regression test anchored to a textbook value (Vandeput's own worked examples are already used elsewhere in this codebase — follow that pattern). Should take under an hour; the value is disproportionate to the effort (a silently-wrong safety-stock formula is about as bad as this codebase's bugs get).

3. **[HIGH, business-relevant] README/agent-README understate the product.**
   `README.md` and `scm_agent/README.md` describe 3-4 capabilities; the real registry has 34. Anyone evaluating the repo (including a prospective Upwork client) sees a much smaller product than exists. Rewrite the capability table(s) to reflect the current tool list (source of truth: `build_default_registry()`, not any doc). Also check `documentation/CAPABILITY_EXPANSION_PLAN.md`'s "Hoy" column and `CHANGELOG.md` (abandoned for roughly the last 10 shipped tools per the audit) while in this area — same root cause (docs not updated alongside a fast-moving loop of tool-adding PRs).

### Backlog — real but lower urgency (full detail in [[linchpin-audit-fixes-2026-07]] and the original audit transcript if still available)

- **Jobs layer:** `_pick_column`/column-sniffing boilerplate duplicated verbatim across ~19 `jobs/*_job.py` files (extract a shared helper); two coexisting deliverable-builder generations for inventory/pricing with a visible drift artifact; generic deck XLSX is unstyled/chartless (below the "client-grade" bar the project claims); deck `confidence` values are hardcoded constants in some tools, not computed.
- **Webapp:** only `POST /api/jobs` is authenticated/rate-limited; other compute-doing endpoints (`/api/portfolio`, `/api/warehouse`, etc.) are not. `/console` prototype is unusable once the recommended production auth is on. No app-level body-size limit (proxy-only).
- **Test suite:** CI coverage gate excludes the orchestrator/jobs/webapp layers (engine-only); `jobs/qa.py` (the QA gate itself) is the least-covered core module at 76%.
- **Engine nits:** `DEA` silently emits NaN on LP solver failure instead of raising; an invalid Incoterm string is unreachable dead code in `landed_cost.py`; `AutoETS`'s default season length is `min(52, n_periods//2)` (arbitrary, should derive from frequency); Croston's error-stat initialization leaks a future value into pre-first-demand periods; the inverse-normal-loss polynomial (`fill_rate.py`) is unguarded below ~5e-4 targets.
- **Docs:** book-count claims disagree across README (17) / CLAUDE.md (23) / the graph's own numbers (24); `documentation/GRAPH_LESSONS.md` and other docs may have similarly drifted — spot-check before trusting any specific number in prose.

### Not code — the product/business gap (see [[linchpin-project]] for the live thread)

The audit's product-value section (5/10) found: zero real-world validation (every case study runs on public sample data), the Odoo connector has never touched a real Odoo instance, and there's no commercial shell (accounts, persistence, multi-tenant). None of this is fixable by writing more engine code — it needs real pilot clients. This is exactly what the in-progress Upwork/Contra/Odoo-Apps-Store go-to-market conversation is for; see [[linchpin-project]] memory for where that stands. Don't let "the code isn't done" block starting outreach — per the audit's own read, the Inventory/Demand-Planner slice (~82%) is genuinely sellable today.

---

## 4. How to run (conventions)

- **Python 3.11+**, `.venv` is uv-managed (no pip): `uv pip install --python .venv/Scripts/python.exe <pkg>`.
- **Tests:** `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -q`. **Lint** (matches CI): `ruff check src tests examples`. ASCII-only in console prints (Windows cp1252 — em dashes break it; markdown files written utf-8 are fine).
- **Workflow:** feature branch → draft PR → CI green (3.11/3.12/3.13) → squash-merge. Never push straight to `main`.
- **graphify:** `graphify update .` refreshes the **code** graph (AST-only, gitignored `graphify-out/`). The **books** graph lives in `knowledge/scm-books/` (committed, needs an LLM backend to rebuild).
- **New agent-tool recipe** (unchanged, still the pattern): `jobs/<x>_job.py` with a pandas-only `prepare()` (reads its own CSV, not `intake.py`) → `run`/`verify`/`build_deck` → a `Tool` in `scm_agent/tools.py` with distinctive multi-word `intent_keywords` → an `options` builder in `scm_agent/tool_options.py` (a system-wide invariant test asserts every tool has one) → add its key to `tests/test_scm_agent.py::test_build_default_registry_tools`.

---

## 5. Gotchas / warnings (read before committing)

- **Worktree recipe that works reliably on this repo (Windows):** `git worktree add -b <branch> C:/Users/<you>/Music/scm/.wt-<x> origin/main` → edit/test with the **main repo's** `.venv/Scripts/python.exe`, cwd = worktree, `PYTHONPATH=<absolute worktree path>` (a *relative* `PYTHONPATH=.` silently breaks if your shell's cwd didn't actually follow you into the new worktree — always double check `pwd` after creating one) → commit → push → `gh pr create --draft` → wait for CI → `gh pr merge --squash --delete-branch`.
- **`gh pr merge --delete-branch` reliably fails to delete the LOCAL branch** if a worktree still references it ("cannot delete branch ... used by worktree") — **the remote merge still succeeds regardless**; verify with `gh pr view N --json state,mergedAt`, don't assume failure. Clean up after: `git worktree remove --force <path>` (can still hit Windows `Permission denied` even run from outside the worktree — fall back to PowerShell `Remove-Item -Recurse -Force`, then `git worktree prune`), then `git push origin --delete <branch>` manually since the aborted local delete also skips the remote delete.
- **No live parallel autonomous loop was detected as of 2026-07-02** (checked: `jobs/intake.py`, `src/batch.py`, `tests/test_batch.py`, `tests/test_jobs.py` were all clean/unmodified). Earlier sessions' notes about a "parallel loop" owning those files may no longer apply — re-check `git status` yourself before assuming either way, since this can change session to session if the user restarts one.
- **Never read or surface PII** — some datasets (e.g. DataCo) carry customer PII; analysis is aggregate-only.
- **Don't paste secrets** into chat or commits. New in this area: `LINCHPIN_APPROVAL_SECRET` (signs writeback approvals) joins `LINCHPIN_API_KEY` as a real secret — see `.env.example`/`SECURITY.md`.
- `.env`, `data/`, `graphify-out/`, `deliverables/` are gitignored.

---

## 6. Key files (updated)

- Writeback safety: `src/writeback.py` (`AuditBookkeeping`, `Approval` w/ HMAC signature, `ABSENT` sentinel — now public), `src/writeback_store.py` (`SqliteAuditLedger`, new this session).
- Odoo connector: `src/connectors/odoo.py` (`OdooClient` w/ timeout+retry, `_ReorderRuleStore`, `_DraftPoStore` — **the partial-failure gap in §3 is here**), `jobs/odoo_job.py`.
- Agent routing/grounding: `scm_agent/registry.py` (`_keyword_matches`, word-boundary + plural tolerance), `scm_agent/intent.py` (LLM-failure fallback), `scm_agent/knowledge.py` (IDF-weighted `ground_citations`, domain-gated `advise`).
- Engine math fixed this session: `src/eoq.py` (`compute_eoq_volume_discount`), `src/multi_echelon.py` (`simulate_serial_gsm`), `src/newsvendor.py` (both optimizers), `src/pricing.py` + `jobs/pricing.py` (`confident` logic).
- Agent: `scm_agent/{orchestrator,registry,intent,knowledge,modes,tools,tool_options,guided_bridge,llm,types}.py`
- Deliverable: `src/deliverable.py`, `jobs/deliverables.py`, `jobs/*_deliverable.py`
- Engines: `src/*.py` (34 tools' worth — run `ls src/` or `build_default_registry()`, don't trust a static list in any doc, including this one)
- Knowledge: `knowledge/scm-books/` (L3 books graph, committed), `graphify-out/` (code graph, gitignored)
- Tests: `tests/test_*.py` (1128 passing) · Plan: `documentation/CAPABILITY_EXPANSION_PLAN.md` (has its own staleness issues, see §3)
