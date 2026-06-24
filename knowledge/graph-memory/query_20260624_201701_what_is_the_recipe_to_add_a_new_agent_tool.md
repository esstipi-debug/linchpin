---
type: "query"
date: "2026-06-24T20:17:01.975924+00:00"
question: "What is the recipe to add a new agent tool?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Tool", "build_default_registry()"]
---

# Q: What is the recipe to add a new agent tool?

## Answer

Add jobs/<x>_job.py with a pandas-only prepare() that reads its OWN csv (not intake.py), plus run/verify; then register a Tool in scm_agent/tools.py with distinctive multi-word intent_keywords. No routing edits.

## Outcome

- Signal: useful

## Source Nodes

- Tool
- build_default_registry()