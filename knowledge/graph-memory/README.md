# graph-memory/ — cross-session memory for the code graph

The **persistent** half of the graphify feedback loop. The SessionStart hook keeps
the code graph (`graphify-out/`) fresh, but that directory is gitignored and
rebuilt every session — so anything worth remembering across sessions lives
**here**, versioned.

Each `*.md` file is one answered structural question about this codebase, with a
signal (`useful` / `dead_end` / `corrected`) and the graph nodes it came from.
`graphify reflect` aggregates them into a deterministic lessons doc that an agent
reads at session start: **[`documentation/GRAPH_LESSONS.md`](../../documentation/GRAPH_LESSONS.md)**.

## The loop

```bash
# 1. You asked the graph something and the answer proved useful (or was a dead
#    end, or you had to correct it). Record it — this is what persists.
graphify save-result --memory-dir knowledge/graph-memory \
  --type query --outcome useful \
  --question "How does the orchestrator route a brief to a tool?" \
  --answer  "intent.classify -> registry.get(tool) -> prepare/run/qa/deliver; QA fails => no deliverable." \
  --nodes   "Orchestrator" "Tool" "build_default_registry()"

# 2. Regenerate the lessons doc from all committed memories (deterministic, no LLM).
graphify reflect --memory-dir knowledge/graph-memory \
  --out documentation/GRAPH_LESSONS.md --graph graphify-out/graph.json

# 3. Commit the new entry + the regenerated lessons in your PR.
```

`--outcome dead_end` (the path didn't lead anywhere) and `--outcome corrected`
(`--correction "what was actually true"`) are as valuable as `useful`: they stop
the next session from repeating a wrong turn.

## Conventions

- **Keep entries true and verified.** A memory is an assertion the next agent will
  trust for orientation; verify against the code before saving.
- **Prune stale memories** when the code they describe changes — or mark a fresh
  entry `corrected`. `reflect` half-lifes old signals (30 days) but can't know the
  code moved.
- **Paths:** the store is `knowledge/graph-memory/` (here, committed); the graph is
  `graphify-out/graph.json` (gitignored, rebuilt by the hook). The reflect header
  prints a generic `graphify-out/memory/` string — the real store is this folder.
