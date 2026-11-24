---
name: provenance-forensics
description: >-
  Establish a tamper-evident, replayable record of input research materials
  (sha256 inventory, magic-byte and PDF /Encrypt sniffing, duplicate and
  version-suspect clustering) plus an append-only hash-chained audit log.
  Trigger at the START of any reading/annotation task when the user asks to
  盘点 / 取证 / 哈希 / 版本关系 / 审计日志 / 复跑核对 the materials, or before any
  downstream annotation work on files whose authenticity matters.
---

# Provenance Forensics (上游取证)

## When to use

Use this skill **first**, before any reading, annotation, or knowledge-
deposition work, whenever the authenticity of the upstream input materials
matters: 盘点 (inventory), 取证 (forensics), 哈希 (hashing), 版本关系
(version relationships), 审计日志 (audit log), 复跑核对 (replay check).
It answers one question only: *what exactly are the input files, and can a
reviewer later confirm nothing silently changed?*

## Inputs & runtime contract

- Case inputs live at `/input/case.json` and `/input/task.md`; real research
  materials are at the paths the case names. Work under `/app/work`.
- Final deliverables go under `/app/output`, including `result.json` which
  MUST contain the original `case_id` and **every field named by the case's
  `output_contract`** — read `output_contract` from `case.json` dynamically
  at runtime; never hardcode field names.
- Honesty contract: write a **partial `result.json` early** (right after the
  first concrete step, e.g. the inventory) and improve it in place. `status`
  ∈ {complete, partial, failed}. Include sources, uncertainty, and
  change_records; record every skip, failure, conflict, and recovery. Never
  fabricate content or scores. No prepared answers.
- Budget: 64 model requests / 900 s. Run the scripts below once, capture
  their output, and move on.

## Workflow

All scripts are at `/skills/weekly-skill/scripts/` and are Python 3 stdlib
only. Suggested sequence (paths are examples; use the case's real paths):

```bash
SCRIPTS=/skills/weekly-skill/scripts
MATERIALS=/input/materials          # whatever the case names
WORK=/app/work/provenance
mkdir -p "$WORK"

# 1. Forensic inventory: hashes, magic sniff, encrypted-PDF detection,
#    duplicate groups, version-suspect clusters.
python3 "$SCRIPTS/forensic_inventory.py" --dir "$MATERIALS" \
    --out "$WORK/manifest.json"

# 2. Record the step in the append-only audit log.
python3 "$SCRIPTS/audit_log.py" append --log "$WORK/audit.jsonl" \
    --op inventory --detail tool=forensic_inventory.py \
    --detail out="$WORK/manifest.json"

# 3. Record every classification decision, skip, conflict, and recovery
#    the same way (see references/authenticity_playbook.md), e.g.:
python3 "$SCRIPTS/audit_log.py" append --log "$WORK/audit.jsonl" \
    --op recovery --detail file=locked.pdf \
    --detail action=skipped_encrypted --detail reason=no_password_provided

# 4. Write / refresh the honest partial result.json under /app/output NOW.

# 5. At the end (and anytime in between), prove nothing changed and the
#    log is intact. Both exit 0 when clean, 3 on any break.
python3 "$SCRIPTS/replay_check.py" --manifest "$WORK/manifest.json" \
    --dir "$MATERIALS" --out "$WORK/replay_report.json"
python3 "$SCRIPTS/audit_log.py" verify --log "$WORK/audit.jsonl"
```

A reviewer re-runs steps 5 with the delivered `manifest.json` and
`audit.jsonl` to confirm the materials and the record are unchanged.

## Outputs

- `manifest.json` — deterministic inventory (format:
  `references/manifest_schema.json`): per-file relpath, sha256, size,
  mtime, permission bits, readability, sniffed type vs. extension-mismatch
  flag, PDF /Encrypt flag, empty flag, classification ∈ {readable,
  encrypted, unreadable, permission_denied, empty, mismatched_extension};
  plus duplicate_groups (byte-identical) and version_suspect_groups.
- `audit.jsonl` — append-only hash-chained operation log (seq, op, details,
  prev_sha256, entry_sha256; no wall-clock time).
- `replay_report.json` — added / removed / changed(hash) / renamed-suspect
  diff of a re-run against the saved manifest.
- Facts from these artifacts feed the case's `result.json` fields per its
  `output_contract`.

## Failure handling

- Encrypted PDF, permission denied, unreadable, empty, or extension-
  mismatched files are **not** fatal: they are classified in the manifest
  and handled per `references/authenticity_playbook.md`. Record the
  decision and any recovery as an audit-log entry (`--op skip` /
  `--op recovery` with reasons), and reflect it in `result.json`'s
  uncertainty/change_records. Never silently drop a file.
- `replay_check.py` or `audit_log.py verify` exiting 3 means tampering or
  corruption: stop, record `--op conflict`, and report status partial/failed
  rather than guessing.

## Boundaries (what this skill does NOT do)

- No annotation extraction, no note-taking, no summarization, no retrieval.
- No judgement of content quality or relevance; it never merges, renames,
  deletes, or "fixes" input files (version suspects are flagged, never
  merged silently).
- It does not decrypt encrypted files or bypass permissions; it only
  records the condition and the chosen handling.

## Minimal example

A complete synthetic worked example with fixtures, exact commands, and the
real observed output is in `examples/` (see `examples/README.md` and
`examples/EXPECTED.md`).
