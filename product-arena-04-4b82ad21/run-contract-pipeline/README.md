# run-contract-pipeline

A self-contained agent **Skill bundle** for scientific-writing competition
cases (introduction / related-work writing) executed by an agent under a
harness. Its center of gravity is the **runtime contract and process quality
control**: staged checkpoints so partial work is never lost, disciplined
reading of the case contract, assembly of a `result.json` that mirrors the
case's `output_contract` exactly, honest `complete` / `partial` / `blocked`
status, and budget-aware execution (64 model requests / 900 s / 16384 tokens
per response).

The skill does **not** write the science. It guarantees the process and the
contract: nothing is lost, nothing is fabricated, and what you submit is
exactly what the case asked for.

## Layout

```
SKILL.md                        the graded skill definition (start here)
README.md                       this file
GITHUB_URL.txt                  upstream repository location
scripts/
  init_run.py                   parse case.json -> plan.json, contract_map.json, skeleton_result.json
  checkpoint.py                 append-only JSONL checkpoints + file snapshots per stage
  assemble_result.py            fill the skeleton from artefacts that actually exist -> result.json
  contract_check.py             type-check result.json vs the contract; verify constraints vs the draft
references/
  runtime_contract.md           the execution contract explained for writers
  failure_modes.md              failure modes: recognition, disposal steps, copyable open_items wording
examples/
  README.md                     what the example shows + exact commands
  run_example.sh                end-to-end miniature run (set -euo pipefail, relative paths)
  synthetic-case/               SYNTHETIC demo case (all content invented)
  sample-output/                real outputs produced by actually running run_example.sh
```

## Quick start

```bash
python3 scripts/init_run.py --case /input/case.json --task /input/task.md \
  --work /app/work --output /app/output
# ... read material, draft under /app/work, checkpoint after each milestone ...
python3 scripts/assemble_result.py --case /input/case.json --work /app/work \
  --output /app/output --draft /app/work/draft/introduction.md \
  --claims /app/work/claims.json
python3 scripts/contract_check.py --case /input/case.json \
  --result /app/output/result.json --draft /app/work/draft/introduction.md \
  --out /app/output/contract_report.json
```

See `SKILL.md` for the full operating loop, the budget policy and the
failure-mode table, and `examples/README.md` for a runnable end-to-end demo
(`bash examples/run_example.sh`).

## Guarantees and non-goals

- Pure Python 3 standard library; every script takes explicit path arguments
  (nothing hardcoded to `/input` or `/app`); exit codes 0 ok / 1 check
  failures / 2 usage error.
- The bundled example is **synthetic**: it demonstrates the interface only.
  Never submit precomputed answers for the organizers' fixed cases, and never
  invent scores or benchmark numbers.
- The checks are mechanical (types, counts, keyword presence). They prove
  contract and constraint compliance, not semantic writing quality.
