---
type: "query"
date: "2026-07-20T22:23:10.661684+00:00"
question: "Can hat_tension/hat_settlement reuse inventory_optimization's citation anchors safely?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["safety_stock", "service_level", "working_capital_efficiency"]
---

# Q: Can hat_tension/hat_settlement reuse inventory_optimization's citation anchors safely?

## Answer

Yes with exclusions: tension anchors (safety_stock, service_level, cycle_service_level) have a 646-node 2-hop closure containing reverse_auction + procurement_auction (PR #164 false-friend class) -> EXCLUDED_CONCEPTS[hat_tension]; settlement anchors (safety_stock, service_level, working_capital_efficiency) closure is 386 nodes and clean.

## Outcome

- Signal: useful

## Source Nodes

- safety_stock
- service_level
- working_capital_efficiency