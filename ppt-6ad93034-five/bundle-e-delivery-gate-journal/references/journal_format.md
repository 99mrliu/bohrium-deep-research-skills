# Journal format & result.json contract

## journal.jsonl — append-only hash chain

One JSON object per line, written with `json.dumps(..., sort_keys=True,
separators=(",", ":"))` (canonical form). Located at `work/journal.jsonl`
(copy it to `/app/output/journal.jsonl` at delivery time).

Every entry:

```json
{
  "seq": 0,                       // monotonically increasing, gap-free
  "kind": "init|command|gate|note",
  "ts_utc": "ISO-8601 UTC",
  "inputs":  {"<path>": "<sha256 hex>" | null},   // file bytes at log time
  "outputs": {"<path>": "<sha256 hex>" | null},
  "prev_hash": "<hash of previous entry>" | null,  // null only for seq 0
  "hash": "sha256(canonical_json(entry without 'hash'))"
}
```

- **Entry 0 (`init`)** additionally carries:
  - `inputs`: sha256 of EVERY file under the input dir, keyed by path relative to it.
  - `tools`: `{pdftotext, pdftoppm, soffice, python3}` → version string or `null`.
- **`log` entries** may add `cmd` and `note`. A listed file that does not exist
  is recorded as `null` plus a stderr warning — it is never silently skipped.
- File paths are stored exactly as passed; pass paths relative to a stable
  working directory if you want copies of the tree to re-verify in place.

### Verification (`journal.py verify`)

For each entry: recompute `hash` from the entry body; check `prev_hash`
linkage; re-hash every recorded file that still exists. Per-entry status:

- `ok` — hashes and linkage all match.
- `missing` — a recorded file no longer exists (a fact, not an automatic failure).
- `tampered` — entry hash mismatch, broken linkage, or a file whose current
  bytes differ from the recorded hash. **Exit code 1.**

If verification reports tampering: investigate. Do not delete or rewrite the
journal — that destroys the evidence and is itself detectable.

## result.json contract (owned by watchdog.py)

Written BEFORE any real work (`watchdog.py init`) and atomically replaced
(`tmp` + `os.replace`) after every stage, so any kill point leaves a valid file.

- `case_id`: from `case.json` key `case_id` or `id` (never invented).
- Every root field of `case.json`'s `output_contract`, with type-correct
  placeholders until real values exist (strings → `null`, lists → `[]`,
  objects → `{}`, booleans → `false`). If the case has no `output_contract`,
  use the defaults: `status`, `editable_source`, `export_artifact`,
  `content_map`, `compliance_checks`, `exceptions`.
- `status` ∈ `success | partial | unable_to_determine | refused`.
  It is `partial` from init until finalize; `partial` states limits precisely
  in `exceptions`.
- `synthetic_example`: passed through unchanged when present in `case.json`.
- `stage`, `updated_utc`, `finalized_utc`: bookkeeping added by the watchdog.
- `advance` REFUSES to record paths in `editable_source`, `export_artifact`,
  or `content_map` that do not exist on disk.
- `finalize --status success` is REFUSED unless `gate-plan.json`,
  `gate-build.json` and `gate-render.json` all exist with `verdict: PASS`.
