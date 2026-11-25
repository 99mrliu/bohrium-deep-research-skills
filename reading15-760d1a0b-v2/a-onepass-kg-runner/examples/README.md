# SYNTHETIC example for a-onepass-kg-runner

> **SYNTHETIC example, not real papers.** Every file under `synthetic/` is
> invented demo data (clearly marked SYNTHETIC). The committed outputs in
> `synthetic/output/` are synthetic pipeline products for reviewer
> inspection — **they are NOT formal answers to any real challenge case**.

## What it simulates

The official runtime layout `/input → /app/work → /app/output`, driven by the
bundle's own scripts only:

- `synthetic/input/` — shaped exactly like the real runtime contract:
  `case.json` (case_id + 7-key `output_contract` + exactly 3 `query_specs` +
  root bibliographic metadata of the **primary** paper only), `task.md`,
  `material.json` (aggregate index), `primary-material.json` (P1),
  `secondary-material.json` (S1), `corpus-manifest.json` (role/doi/title/
  authors/sha256/license).
- `synthetic/_work/` (created at run time, not committed) — checkpoints,
  the seeded model artifact, intermediate graph files.
- `synthetic/output/` — committed deliverables.

The single model-written artifact is simulated by seeding
`synthetic/extractions.seed.jsonl` into `_work/extractions.jsonl` (via
`kg_run.py all --seed`), exactly where the harness agent would write
`/app/work/extractions.jsonl`.

## The 6 required fixtures (all SYNTHETIC)

1. **Cross-paper alias pair**: "methylammonium lead iodide" (P1) vs "MAPbI3" (S1)
   → 1 justified `merge` (normalized_key + reason).
2. **Abbreviation at first mention**: "power conversion efficiency (PCE)" (P1 p1).
3. **Cross-paper numeric conflict under different conditions**: PCE 21.1% at
   1-sun initial (P1) vs 18.7% retained after 500 h damp-heat (S1) — kept as
   **two separate claim nodes** + a `contradicts` edge with
   `resolution=preserved` + an explicit `nonmerge` (never merged into one claim).
4. **Same-name-different-object trap**: "TiO2" in both papers = compact ETL (P1)
   vs 20 nm mesoporous scaffold (S1) → explicit `nonmerge`.
5. **Unreported item**: hysteresis index not reported (P1 p6) → `unreported` op.
6. **`case.json` with `output_contract` and exactly 3 `query_specs`**:
   neighborhood / by-relation / conflict-check.

The seed file also contains **2 intentionally bad lines** (malformed JSON,
unknown op) to demonstrate the tolerant parser, and **1 op with a fabricated
quote** to demonstrate quarantine: it is rejected with
"quote is NOT an exact substring of P1/p2", so the verifier's quote-precision
is 18/19 = 94.74% — the honest, expected number for this demo.

## How to run

```bash
python3 scripts/run_example.py          # from the bundle root
# or
sh examples/run_example.sh
# add --force to ignore checkpoints and recompute every stage
```

## Expected console output

```
=== a-onepass-kg-runner SYNTHETIC example ===
(SYNTHETIC example, not real papers; outputs are demo data, not formal case answers)
[discover] sources=2 paragraphs=20 warnings=0 (…)
[all] seeded model artifact …/extractions.seed.jsonl -> work/extractions.jsonl
[all] early partial result.json written to …/output
[apply] lines=22 accepted=20 skipped=2 (…)
  skip line 21: malformed JSON: …
  skip line 22: unknown op 'hallucinate' (known: node/edge/merge/nonmerge/unreported/note)
[verify] accepted=19 rejected=1 quote_precision=94.74% (…)
  reject line 20 (node n_bad_quote_demo): quote is NOT an exact substring of P1/p2
[build] nodes=10 edges=14 merges=1 nonmerges=2 conflicts=1 (…)
[query] specs=3 executed=3 answered=3 (…)
[assemble] status=success result keys=12 -> …/output (…)
[all] done in …s; budget used ~1 model artifact + 6 script stages
```

Exit code 0.

## Output files (committed under `synthetic/output/`)

| file | content |
| --- | --- |
| `result.json` | case_id + all 7 contract keys mirrored; 10 nodes / 14 edges inline; 3 executed queries with evidence + undetermined lists; merge_ledger (1), nonmerge_registry (2), preserved conflict, unreported (1), uncertainty, status=success |
| `graph.json` | deterministic graph (sorted), nodes with verbatim quotes + merged_from provenance |
| `graph.dot` | Graphviz DOT preview |
| `graph.svg` | deterministic layered SVG preview (stdlib-generated, no graphviz) |
| `verify_report.json` | mechanical verification: quote stats (18/19 = 94.74%), per-item quarantine |
| `run_report.json` | signature artifact: per-stage timings under `run_meta` only, JSONL line-acceptance stats, 7-item budget checklist |

## Inspecting results

```bash
python3 - <<'EOF'
import json
r = json.load(open('examples/synthetic/output/result.json'))
print(r['status'], r['graph']['node_count'], r['graph']['edge_count'])
for q in r['queries']:
    print(q['query_id'], q['type'], q['status'],
          len(q['result_subgraph']['nodes']), 'nodes')
EOF
```

Re-running the example is byte-deterministic for every output except
`run_report.json`'s `run_meta` timings block.
