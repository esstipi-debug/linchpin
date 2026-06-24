---
type: "query"
date: "2026-06-24T20:17:01.822434+00:00"
question: "What are the four never-unprotected outcomes?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["GuidedOutcome", "ExecutionOption", "HandoffPacket"]
---

# Q: What are the four never-unprotected outcomes?

## Answer

GuidedOutcome.status is one of EXECUTED, OPTIONS, HANDOFF, ESCALATED (src/guided.py). The last three need a human; verify_guided rejects a consequential result with none of options/handoff/escalation.

## Outcome

- Signal: useful

## Source Nodes

- GuidedOutcome
- ExecutionOption
- HandoffPacket