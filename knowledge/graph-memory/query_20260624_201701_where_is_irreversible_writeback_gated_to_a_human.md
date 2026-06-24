---
type: "query"
date: "2026-06-24T20:17:01.745509+00:00"
question: "Where is irreversible writeback gated to a human?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["apply()", "Approval", "Changeset"]
---

# Q: Where is irreversible writeback gated to a human?

## Answer

src/writeback.py apply() raises WritebackRefused unless an Approval bound to the changeset idempotency_key is valid (900s TTL). Tier 'irreversible' always needs explicit approval; 'reversible' unless auto_apply; 'read' never.

## Outcome

- Signal: useful

## Source Nodes

- apply()
- Approval
- Changeset