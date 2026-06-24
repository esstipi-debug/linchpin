---
type: "query"
date: "2026-06-24T20:17:01.899124+00:00"
question: "How does a deliverable cite the chapter AND the code function (the L3 bridge)?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["KnowledgeBase", "Deliverable"]
---

# Q: How does a deliverable cite the chapter AND the code function (the L3 bridge)?

## Answer

scm_agent/knowledge.py KnowledgeBase.bridge() searches the books graph (theory) and code graph (impl); implements() resolves the src/ function for a concept with an IDF-weighted, rationale-aware token match.

## Outcome

- Signal: useful

## Source Nodes

- KnowledgeBase
- Deliverable