# Authenticity Playbook

Policies for handling non-clean findings from `forensic_inventory.py`.
Every decision MUST be recorded in the audit log (`audit_log.py append`)
with `--op` and `--detail` pairs giving the file, the action, and the
reason, and MUST be reflected in `result.json`'s uncertainty /
change_records. Never silently drop, merge, rename, or "fix" an input
file.

## Encrypted PDF (`classification: encrypted`)

- Detection: sniffed `pdf` and raw `/Encrypt` marker in the first 64 KiB.
- Policy: do NOT attempt to crack or bypass. If the case supplies a
  password and a permitted tool, decryption is a *recovery action*: record
  `--op recovery --detail file=... --detail action=decrypted --detail
  reason=password_provided_in_case`. Otherwise record `--op skip --detail
  action=skipped_encrypted --detail reason=no_password_provided` and mark
  the corresponding uncertainty in `result.json`.

## Permission denied / unreadable

- Retry once after confirming the path is correct (typo is a recovery:
  record it). If still denied, classify stays `permission_denied` /
  `unreadable`; record `--op skip` with the OS error string from the
  manifest's `error` field. Do not chmod or elevate privileges on input
  materials — that would itself be a modification of upstream evidence.

## No text layer (image-only PDF)

- The inventory does not OCR. A readable PDF that downstream steps find
  has no extractable text is recorded as `--op skip --detail
  action=no_text_layer` by the downstream step; provenance only guarantees
  the bytes are unchanged.

## Byte-identical duplicates (`duplicate_groups`)

- Choose ONE canonical copy for downstream work by this rule, in order:
  1. the path explicitly named in the case instructions (`case.json` /
     `task.md`), if any member is named;
  2. else the shortest relpath (ties broken lexicographically).
- Record the choice: `--op dedup_decision --detail
  canonical=<path> --detail duplicates=<p1,p2> --detail rule=<named_in_case|shortest_path>`.
- Keep ALL copies on disk untouched; only the *processing* is deduplicated.

## Version suspects (`version_suspect_groups`)

- NEVER merge silently. Files like `report.pdf` and `report (1).pdf` with
  different hashes are related but distinct versions.
- If the case or task text names one as authoritative, use it and record
  `--op version_decision --detail chosen=... --detail
  reason=named_in_case`. If nothing names one, carry BOTH forward (or the
  one the downstream step can justify) and state the ambiguity in
  `result.json`'s uncertainty. Record either way.

## Extension mismatch (`classification: mismatched_extension`)

- The file's bytes do not match its extension (e.g. plain text named
  `.pdf`). Do not rename it. Downstream steps must parse by the SNIFFED
  type, not the extension. Record `--op classify --detail file=...
  --detail sniffed=utf8_text --detail action=parse_as_sniffed_type`.

## Recording recovery actions

- Conventional ops: `inventory`, `classify`, `dedup_decision`,
  `version_decision`, `skip`, `recovery`, `conflict`, `replay_check`,
  `result_write`.
- Every recovery entry needs: `file` (relpath), `action` (what was done),
  `reason` (why it was justified). If a step fails and is retried
  differently, log BOTH the failure and the recovery.
- If `replay_check.py` or `audit_log.py verify` exits 3, treat it as a
  conflict: log `--op conflict`, stop downstream claims about the affected
  files, and set `result.json` status to `partial` or `failed` with the
  evidence paths.
