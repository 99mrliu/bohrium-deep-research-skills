# citation-coverage-auditor

An agent Skill bundle for auditing **citation coverage and bibliography metadata**
in scientific introduction / related-work writing.

The skill's center of gravity:

- **Bibliography reconciliation** — every cited work traceable to the provided
  bibliography, with consistent metadata across the structured (`references.json`)
  and human-readable (`references.md`) representations.
- **Vancouver numbering** — references numbered strictly by first appearance;
  marker syntax `[1]`, `[1,2]`, `[1-3]` checked and, on request, repaired.
- **Coverage auditing** — the closest works, representative works per route,
  recent progress, mandated topics, and minimum distinct-citation counts are all
  checked; decorative citations are linted.
- **Claim-to-citation correspondence** — every `[n]` marker bound to a sentence
  backed by a claim record; no orphan citations, no unsupported clusters, no
  claim records disconnected from the draft.

## Contents

| path | what it is |
|---|---|
| `SKILL.md` | the graded skill definition (purpose, workflow, runtime contract, doctrine) |
| `scripts/bib_parse.py` | normalize `references.json` → `bib.json`; cross-check against `references.md` |
| `scripts/numbering_check.py` | verify (and with `--fix`, repair) Vancouver numbering by first appearance |
| `scripts/coverage_ledger.py` | coverage ledger: topics, closest works, recency, decorative-citation lint |
| `scripts/claimcite_check.py` | claim-to-citation correspondence, orphan detection in both directions |
| `references/coverage_policy.md` | what must be covered and why; worked synthetic table; anti-patterns |
| `references/vancouver_rules.md` | numbering, marker syntax, placement, renumbering procedure |
| `examples/` | runnable **SYNTHETIC EXAMPLE** demonstrating the full pipeline |

All scripts are pure Python 3 standard library, take explicit path arguments via
argparse, and exit `0` (pass) / `1` (findings) / `2` (usage error).

## Quick start

```bash
cd examples
bash run_example.sh        # runs all four scripts on the bundled synthetic case
ls sample-output/          # bib.json, xcheck_report.*, numbering_report.json,
                           # coverage_ledger.*, claimcite_report.json
```

See `examples/README.md` for the exact per-step commands.

## Provenance notice

The bundled example case is **entirely synthetic** (invented manuscript,
invented references, invented DOIs). It demonstrates the interface only. Never
treat its content as real scientific fact, and never submit precomputed answers
for an organizer's fixed cases.
