---
type: "query"
date: "2026-06-24T20:17:01.666707+00:00"
question: "How does the orchestrator route a brief to a tool?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Orchestrator", "Tool", "build_default_registry()"]
---

# Q: How does the orchestrator route a brief to a tool?

## Answer

intent.classify scores the brief against each Tool's multi-word intent_keywords; registry.get(tool) returns the winner; then prepare->run->qa->deliver runs. 'QA fails => no deliverable' is enforced once in the orchestrator.

## Outcome

- Signal: useful

## Source Nodes

- Orchestrator
- Tool
- build_default_registry()