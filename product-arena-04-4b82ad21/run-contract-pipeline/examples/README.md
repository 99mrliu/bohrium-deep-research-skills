# Examples — run-contract-pipeline

> **SYNTHETIC EXAMPLE — interface demonstration only.**
> Every manuscript fact, reference, author, journal, DOI and number in
> `synthetic-case/` is **invented**. This example exists to demonstrate the
> skill's pipeline and file interfaces. It is **not** an answer to any
> platform case, and nothing here may be submitted for the organizers' fixed
> cases.

## What the example shows

A full miniature run of the five-stage operating loop against
`synthetic-case/case.json` (case id `synthetic-intro-demo-0001`, an
introduction + related-work writing task):

1. **init_run** — parses the case, writes `plan.json`, `contract_map.json`
   and `skeleton_result.json` into the work directory.
2. **checkpoint "read"** — snapshots the case and task files.
3. **draft** — the synthetic draft `synthetic-case/filled/introduction.md`
   (pre-authored, grounded only in the synthetic material) and the claim
   table `synthetic-case/filled/claims.json` are snapshotted at checkpoint
   "draft". In a real run the agent writes these; here they are committed so
   the demo is reproducible.
4. **assemble_result (pass 1)** — builds `result.json`; verification is
   `not_run` at this point.
5. **contract_check (pass 1)**, then **assemble_result (pass 2)** embedding
   the verification report, then a **final contract_check** whose report
   lands next to `result.json`.

Expected outcome: `result.json` carries `case_id` `synthetic-intro-demo-0001`
plus all six `output_contract` fields, `status` is `complete`, `limits` is
empty, and the final `contract_check` exits 0 (all constraint checks pass;
two prose subfields of the `verification` descriptor are reported
`not_verifiable`, which is the designed behaviour for unparseable descriptor
fragments).

## Exact commands

```bash
cd <skill-dir>/examples
bash run_example.sh
```

Or step by step:

```bash
SKILL=<skill-dir>
CASE=$SKILL/examples/synthetic-case/case.json
TASK=$SKILL/examples/synthetic-case/task.md
WORK=$SKILL/examples/sample-output/work
OUT=$SKILL/examples/sample-output/output
FILLED=$SKILL/examples/synthetic-case/filled

python3 $SKILL/scripts/init_run.py --case $CASE --task $TASK --work $WORK --output $OUT
python3 $SKILL/scripts/checkpoint.py --work $WORK --stage read \
  --note "case, task, material read" --snapshot $CASE --snapshot $TASK
python3 $SKILL/scripts/checkpoint.py --work $WORK --stage draft \
  --note "draft + claims written" \
  --snapshot $FILLED/introduction.md --snapshot $FILLED/claims.json
python3 $SKILL/scripts/assemble_result.py --case $CASE --work $WORK --output $OUT \
  --draft $FILLED/introduction.md --claims $FILLED/claims.json
python3 $SKILL/scripts/contract_check.py --case $CASE --result $OUT/result.json \
  --draft $FILLED/introduction.md --out $WORK/verification_report.json
python3 $SKILL/scripts/assemble_result.py --case $CASE --work $WORK --output $OUT \
  --draft $FILLED/introduction.md --claims $FILLED/claims.json \
  --verification $WORK/verification_report.json
python3 $SKILL/scripts/contract_check.py --case $CASE --result $OUT/result.json \
  --draft $FILLED/introduction.md --out $OUT/contract_report.json
```

## Layout

- `synthetic-case/` — the demo case (copied verbatim from staging), plus
  `filled/introduction.md` and `filled/claims.json`, the pre-authored
  synthetic answer artefacts used by the demo run.
- `run_example.sh` — the end-to-end driver (`set -euo pipefail`, paths
  relative to the script's own directory; regenerates `sample-output/` from
  scratch on every run).
- `sample-output/` — real outputs produced by actually running
  `run_example.sh`:
  - `work/plan.json`, `work/contract_map.json`, `work/skeleton_result.json`
  - `work/checkpoints.jsonl` and `work/snapshots/{read,draft}/`
  - `work/verification_report.json` (embedded into result.json in pass 2)
  - `output/result.json` (status `complete`) and `output/contract_report.json`

## Negative-path check (not part of the bundle outputs)

Deleting (or never providing) the draft makes `assemble_result.py` emit
`status: blocked` with `limits: ["no_draft", ...]`, and `contract_check.py`
exit 1 with `draft:file_present` failed. This was verified outside the bundle
(in `/tmp`) so the shipped `sample-output/` shows only the good path.
