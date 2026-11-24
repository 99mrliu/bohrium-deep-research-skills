---
name: retrieval-gate
description: >-
  Retrieval entry and pre-delivery quality gate for precipitated reading
  knowledge. Use when the user needs 后续检索 / 知识沉淀检索 (theme, tag, entity,
  source, or time retrieval over annotations and notes with explicit no-hit and
  召回 / low-recall handling) or 质量门控 / 交付前检查 (machine-checking the whole
  result — contract completeness, evidence verification rates, known-item
  retrieval smoke tests, replay determinism — and forcing status=partial when
  any check fails).
---

# Retrieval Gate (检索入口与交付门控)

Gives precipitated knowledge (annotations + notes + file metadata produced by
earlier extraction/note work) a real query interface, and acts as the
pre-delivery quality gate that machine-checks the whole result before it ships.

## When to use

- The user wants to retrieve precipitated knowledge by theme, tag, entity,
  source file, or time range — with an explicit answer when nothing matches.
- Before delivering any reading-annotation result: verify the contract is
  satisfied, artifacts are intact, evidence verification met its thresholds,
  known items are actually retrievable, and the index replays byte-for-byte.
- Whenever an unfinished result must be prevented from masquerading as complete.

## Inputs & runtime contract

- Inputs arrive at `/input/case.json` + `/input/task.md` + real materials.
  Intermediate text artifacts (annotations.jsonl, notes.jsonl,
  files_inventory.json) come from earlier extractor/note-composer work; all are
  optional but at least one is required to build an index.
- Work under `/app/work`; deliverables under `/app/output`.
- `/app/output/result.json` MUST contain the original `case_id` and every field
  named by the case's `output_contract` — read the contract from case.json
  dynamically, never hardcode field names.
- Honesty: write a partial `result.json` EARLY and improve it in place; status
  ∈ {complete, partial, failed}; record sources, uncertainty, change_records,
  and any skips/failures/conflicts/recoveries. Never fabricate.
- Budget: 64 model requests / 900 s. The scripts are deterministic stdlib-only
  Python — prefer running them over re-deriving results by hand.

## Workflow

All scripts live under `/skills/weekly-skill/scripts/`.

1. Build the index (records input paths + sha256 in meta for later replay):

   ```
   python3 /skills/weekly-skill/scripts/build_index.py \
     --annotations /app/work/annotations.jsonl \
     --notes /app/work/notes.jsonl \
     --inventory /app/work/files_inventory.json \
     --out /app/output/index.json
   ```

2. Answer retrieval requests; always log so a reviewer can replay every search:

   ```
   python3 /skills/weekly-skill/scripts/query.py --index /app/output/index.json \
     --q "增量学习" --since 2026-01-01 --log /app/work/query_log.jsonl
   ```

   Zero hits → a structured no-hit report names the facet that eliminated
   everything and suggests relaxations. Max score below the threshold →
   `low_confidence: true`. Report both honestly in result.json.

3. Ship known-item smoke queries (`smoke.json`: `[{q, must_find_id}, ...]`;
   `must_find_id: null` = negative control expecting zero hits).

4. Run the gate last, after all other deliverables exist:

   ```
   python3 /skills/weekly-skill/scripts/gate.py \
     --case /input/case.json --output-dir /app/output \
     --index /app/output/index.json --smoke-queries /app/work/smoke.json \
     --out /app/output/gate_report.json
   ```

   Exit 0 → all checks pass. Exit 3 → at least one check failed AND the gate
   has already rewritten `result.json` to `status: "partial"` with the failed
   check names appended to its uncertainty/limitations field. Fix the cause
   (see `references/gate_checklist.md`) and re-run; only deliver on exit 0.

## Outputs

- `index.json` — deterministic inverted index with full source locators.
- `query_log.jsonl` — seq-numbered, wall-clock-free replay log of every query.
- `gate_report.json` — `{checks:[{name,pass,detail}], verdict, failed}`.
- A `result.json` whose `status` can be trusted: the gate forces `partial`
  whenever any check fails.

## Failure handling

- Missing index/inputs/case: scripts exit 2 with a stderr message; fix the path.
- No-hit retrieval is a normal answer (exit 0): surface the no-hit report's
  eliminating facet and suggestions; record the miss in result.json uncertainty.
- Gate failure is not the end: read `gate_report.json`, fix per
  `references/gate_checklist.md`, re-run the gate. Never hand-set
  `status: "complete"` to bypass a failing check — the replay-determinism and
  artifact-hash checks are designed to catch stale or hand-edited outputs.

## Boundaries

- NOT an extractor and NOT a note author: it indexes and audits what others
  produced. It never reads PDFs, never creates or edits annotations/notes.
- NOT a version migrator: it validates current artifacts; it does not upgrade
  old schemas.
- Retrieval is literal term matching (latin words + CJK bigrams), not semantic
  search; low-recall risk is surfaced via `low_confidence`, not hidden.

## Minimal example

See `examples/` (synthetic data): build an index over 6 annotations + 4 notes +
2-file inventory, run an English query, a CJK query (matched via bigrams), a
no-hit query with facet-elimination diagnosis, then the gate — including a
seeded contract violation showing exit 3 and `result.json` rewritten to
`status: "partial"`. Exact commands in `examples/README.md`, real observed
output in `examples/EXPECTED.md`.
