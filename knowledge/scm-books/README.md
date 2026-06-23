# SCM Books Knowledge Graph (L3 domain knowledge)

A graphify knowledge graph built from **22 supply-chain books** (forecasting,
pricing, revenue management, supply chain management, inventory optimization,
manufacturing planning & control, logistics & operations strategy, sustainable
logistics, **and supply-chain leadership**). This is the **domain knowledge**
layer for the agent — distinct from the repo's `graphify-out/`, which graphs the *code*.

- `graph.json` — 1383 nodes · 2539 edges · 100 communities (GraphRAG-ready)
- `graph.html` — interactive visual (open in a browser)
- `GRAPH_REPORT.md` — communities, god nodes, surprising cross-book connections

## What's inside

Forecasting (Boylan & Syntetos, Gilliland, Hyndman FPP3, Box-Jenkins),
pricing (Nagle, Simon, Phillips), revenue management (Gallego & Topaloglu,
Talluri & van Ryzin), supply chain (Chopra & Meindl, Operations & SCM),
inventory optimization (Vandeput), manufacturing planning & control (Vollmann),
global supply chain & operations (Ivanov), logistics strategy (Christopher),
sustainable logistics (Grant, Trautrims & Wong), supply-chain leadership
(Palamariu & Alicke, *From Source to Sold*), plus 4 arXiv papers on dynamic/RL pricing.

The inventory concepts this repo's `src/` engine implements (EOQ, reorder
point, safety stock, (s,Q)/(R,S) policies, fill rate, cost/service-level
optimization, gamma demand, multi-echelon GSM, newsvendor, discrete demand,
simulation optimization) are attributed to **Vandeput** — the source the code
actually follows, chapter by chapter — so the agent's L3 citations and the
`bridge()` (theory ↔ code) point at the right book. Prior cross-book coverage
is kept as graph edges.

The **leadership layer** (Palamariu & Alicke, *From Source to Sold*, 2022) adds
~312 concept nodes drawn from 26 supply-chain-leader interviews, plus the book's
**CHAIN model** as explicit citable nodes — `chain_model` and its five
dimensions `chain_collaborative` / `chain_holistic` / `chain_adaptable` /
`chain_influential` / `chain_narrative`. This is the L3 source that grounds the
`leadership_chain` capability (`jobs/leadership.py`); the model is bridged to
`supply_chain_strategy` so leadership links to the quantitative layer.

The **operations/strategy/sustainability layer** adds ~640 concept nodes across
four authoritative sources: **Vollmann** *Manufacturing Planning & Control*
(S&OP, MPS, MRP, DRP, capacity, JIT — the planning/manufacturing spine the graph
previously lacked), **Ivanov** *Global Supply Chain & Operations* (sourcing,
network design, risk & resilience, digital SC / Industry 4.0), **Christopher**
*Logistics & SCM* (agility, lead-time, network competition, 3PL/4PL), and
**Grant, Trautrims & Wong** *Sustainable Logistics & SCM* (green logistics,
reverse logistics, circular economy, sustainable procurement). Shared concepts
merge by canonical label into cross-book bridges.

Concept node IDs are canonical
(`bullwhip_effect`, `crostons_method`, `dynamic_pricing`), so the same concept
across books merges into one node — that's what forms the cross-book bridges.

## Intended use (L3)

`scm_agent` should query this graph for domain grounding: definitions, which
method applies to a demand pattern, and which book/chapter to cite. The
graph's `source_location` carries chapter references for citations.

## Honest gaps

- **Box-Jenkins**: the source PDF was an OCR watermark scan with no text layer
  — present only as an isolated source node, no extracted concepts.
- **Hyndman FPP3**: extraction capped at the decomposition chapters; later
  chapters (ARIMA, ETS, regression) are not yet in the graph.
- **Chase (Demand-Driven Forecasting)**: image-only scan, excluded.
- **Ivanov (Global SC & Operations)**: partial (~70 nodes) — extraction was
  truncated by the Kimi backend's daily-token / concurrency limits; the strategy,
  risk and digital chapters are covered but not exhaustively.
- **Extraction backends**: forecasting/pricing/inventory books were built earlier;
  leadership + Christopher + Grant were extracted via host subagents (no API key),
  Vollmann + Ivanov via the Kimi backend. Mixed provenance, single canonical graph.
- **Leadership clustering**: the leadership concepts are genuinely distinct (no
  duplicate merging), but cross-chapter semantic bridges are sparse, so they
  split into many per-theme communities (each labeled by its dominant concept,
  e.g. *CHAIN Leadership Model*, *Talent and Leadership Development*, *Supply
  Chain Resilience*) rather than one block. Citations/grounding are unaffected.

Regenerate / extend with `/graphify` over the book PDFs, then refresh these files.
