---
name: library-repair-ops
description: >-
  Repair a messy research document library (real files, aliases, duplicate
  downloads, administrative version notes) with plan-before-touch discipline:
  read-only forensic survey, conservative repair plan, copy-only journaled
  execution, post-run verification, and full rollback. Trigger when the task
  asks to 整理/修复/盘点 a document library, 保留版本关系, resolve 重复/别名
  files, or produce an auditable 操作记录/恢复方案 for file operations.
---

# Library Repair Ops (变更操作安全与可恢复性)

The center of gravity of this skill is **operational safety**: every change
to a document library is planned before it is executed, executed as
copy-only journaled operations, verified afterwards, and reversible.
It does NOT build search indexes or write reading notes — its product is a
repaired library layout plus evidence that lets a third party replay and
audit every step.

## When to use / not use

Use when the case materials are a real file tree with duplicate downloads
(`paper (1).pdf`), alias names, version suspects (`notes v1`, `notes v2`),
administrative notes (行政说明, README) stating what supersedes what, and the
task demands organization that preserves version relationships.

Do not use for: content extraction from PDFs, semantic note writing,
search-index construction, literature retrieval. Pair with a cataloging
skill if the case also demands a searchable deliverable.

## Runtime contract (platform)

1. Read `/input/case.json` and `/input/task.md` first. Resolve material
   paths exactly as the case names them; never assume content from labels.
2. Work under `/app/work`; final deliverables under `/app/output`.
3. `/app/output/result.json` MUST contain the case's `case_id` and **every
   field named in the case's `output_contract`** — read the contract
   dynamically at runtime, never hardcode field names. Write an honest
   **partial result.json early** (right after the survey) and improve it
   in place: `status` ∈ {complete, partial, failed}, plus `sources`,
   `uncertainty`, and `change_records`.
4. Budget: 64 model requests / 900 s. Each script call below runs in
   seconds; do not re-implement them ad hoc.
5. Honesty: record every skip, failure, conflict and recovery. Never
   fabricate a file, hash, or completion state.

## Operating principles

- **Originals are sacred.** Never delete, move, overwrite, or rename a
  source file. Organization is produced as verified copies in a
  destination tree (normally under `/app/output/organized_library/`).
- **Plan before touch.** No mutation happens without a written plan that a
  reviewer can inspect and reject.
- **Journal everything.** Every executed action is appended to a
  hash-chained journal with before/after sha256; a broken chain means
  tampering and must be reported, not repaired silently.
- **Ambiguity is flagged, not guessed.** Anything the heuristics cannot
  resolve confidently gets `needs_review: true` with its basis stated.
- **Explicit administrative statements beat heuristics.** A note saying
  "v2 替代 v1" overrides version-marker ordering, and the note's line is
  quoted as evidence.

## Runbook

`$K` = this skill's directory (normally `/skills/weekly-skill`).
All scripts are Python 3 stdlib only (3.8+), no installation needed.

```bash
K=/skills/weekly-skill
SRC=<materials dir named by the case>          # e.g. /input/materials
WORK=/app/work/repair
OUT=/app/output
mkdir -p "$WORK" "$OUT"

# 0. Write the first honest partial result.json NOW (case_id + contract
#    skeleton + status=partial), then improve it after each step.

# 1. Read-only forensic survey: sha256, magic sniff, readability,
#    duplicate groups, version-suspect clusters. Mutates nothing.
python3 "$K/scripts/librepair.py" survey --root "$SRC" \
    --out "$WORK/manifest.json"

# 2. Conservative repair plan. Pass any administrative note files the
#    case provides so explicit statements override heuristics.
python3 "$K/scripts/librepair.py" plan --manifest "$WORK/manifest.json" \
    --notes "$SRC"/行政说明* "$SRC"/README* \
    --out "$WORK/plan.json"
#    Inspect plan.json yourself: confirm every action, check
#    unmatched_notes_rules (admin statements matching no file must be
#    reported in result.json, never dropped).

# 3. Copy-only journaled execution into the organized layout.
python3 "$K/scripts/librepair.py" apply --plan "$WORK/plan.json" \
    --root "$SRC" --dest "$OUT/organized_library" \
    --journal "$WORK/journal.jsonl"

# 4. Post-run verification: re-hash every copy, check the journal
#    hash-chain, confirm every source hash is represented or aliased.
python3 "$K/scripts/librepair.py" verify --dest "$OUT/organized_library" \
    --journal "$WORK/journal.jsonl" --manifest "$WORK/manifest.json" \
    --out "$OUT/verify_report.json"

# 5. Only if the task asks to undo, or verification reveals a bad run:
python3 "$K/scripts/librepair.py" rollback --dest "$OUT/organized_library" \
    --journal "$WORK/journal.jsonl"
```

Copy the journal and plan into `/app/output/` as operation evidence:
`cp "$WORK/manifest.json" "$WORK/plan.json" "$WORK/journal.jsonl" "$OUT/"`
(unless the contract wants them elsewhere — the contract wins).

## Deliverables map

| Artifact | Content | Contract role |
|-|-|-|
| `organized_library/canonical/` | one verified copy per distinct content | 资料结果 |
| `organized_library/versions/<stem>/` | older versions, chain preserved | 版本关系 |
| `organized_library/ALIASES.json` | duplicate groups with canonical pick + basis | 别名/重复关系 |
| `organized_library/VERSIONS.json` | version chains + admin-note evidence | 版本关系 |
| `journal.jsonl` | hash-chained operation log | 操作证据 |
| `verify_report.json` | re-hash audit, lost-source check | 可核验性 |
| `result.json` | case_id + all output_contract fields, honest status | 交付 |

## Failure and exception handling

- **Unreadable / permission-denied file**: survey records it with
  `readable: false`; apply logs a `skip`; result.json lists it under
  failures with the OS error. Never retry in a loop.
- **Symlink in materials**: recorded, not followed for hashing; flagged.
- **Truncated / corrupt file** (magic sniff disagrees with extension):
  copied as-is (bytes are evidence), flagged in `uncertainty`.
- **Admin note mentions a file that does not exist**: kept in
  `unmatched_notes_rules` and surfaced in result.json as a conflict.
- **Destination exists**: apply refuses to overwrite and logs the skip;
  pick a fresh destination or rollback first.
- **Verify finds hash drift**: report as conflict; do not re-copy over it
  silently — decide with the task text whether rollback is required.
- **Out of budget mid-run**: the partial result.json written at step 0
  plus the journal already on disk are an honest partial deliverable;
  state the last completed step in `change_records`.

## Self-check before finishing

1. `verify` exits 0 (no problems) — if not, every problem is named in
   result.json.
2. Every `output_contract` field is present in result.json and backed by
   a real artifact path.
3. Journal chain intact; file counts: survey == copies + aliases + skips.
4. No original file was modified: spot-check one source hash against the
   survey manifest.

## Minimal runnable example

`examples/` contains a **synthetic** fixture (fabricated small text files,
not real research data) and `run_example.sh`, which executes
survey → plan → apply → verify → rollback end-to-end and prints each
artifact. Run it with:

```bash
bash "$K/examples/run_example.sh"
```

See `examples/minimal_example.md` for the expected output shape. The
example demonstrates interface and flow only; it is not an official case
and produces no official answers.
