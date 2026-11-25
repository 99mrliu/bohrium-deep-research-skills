# Operations Playbook — policies, exception taxonomy, recovery

This reference is the detailed policy companion to SKILL.md's runbook.

## 1. Action vocabulary

The plan contains exactly two action types; anything else a case demands
(e.g. "merge these two notes") is decided by the Agent and journaled
manually — never improvised inside the scripts.

| action | effect on apply | decision basis |
|-|-|-|
| `register_duplicate_group` | canonical member copied to `canonical/`; aliases recorded in `ALIASES.json`, originals untouched | identical sha256; canonical = fewest copy markers → shortest name → earliest mtime |
| `register_version_chain` | latest copied to `canonical/`, older members to `versions/<stem>/`; chain recorded in `VERSIONS.json` | explicit admin note if present, else version markers → mtime |

## 2. Safety invariants (check these, do not assume them)

1. Destination tree is never inside the source tree (apply refuses).
2. No `os.remove`, `os.rename`, or truncate-write ever targets a source path.
3. Every copy is verified by re-hashing the destination before the journal
   entry is written with `ok: true`.
4. Journal entries are hash-chained: `chain_n = sha256(chain_{n-1} +
   canonical_json(entry_n))`. `verify` recomputes the chain from genesis.
5. Rollback removes a copy only when its current hash equals the journal
   hash; drifted files are kept and reported.

## 3. Exception taxonomy and required dispositions

| exception | detection | disposition |
|-|-|-|
| unreadable file (permission) | `os.access R_OK` false / OSError on open | survey `readable:false`, apply `skip`, list in result failures |
| symlink | `os.path.islink` | recorded, content not followed |
| truncated/corrupt file | magic sniff ≠ extension expectation | copy as-is, flag in `uncertainty` |
| duplicate content, different names | shared sha256 | alias edge; never delete the alias original |
| same stem, different content | version-suspect cluster | chain ordering; `needs_review` unless an admin note asserts the order |
| admin note names a missing file | `unmatched_notes_rules` non-empty | surface as conflict in result.json |
| destination path exists | apply pre-check | skip + journal error; do not overwrite |
| hash drift after copy | verify mismatch | report conflict; propose rollback, do not silently re-copy |
| journal chain break | verify recompute | report tampering; freeze further mutations |

## 4. Recovery patterns

- **Interrupted apply**: the journal is append-only and each entry is
  written after its action completes, so the last entry is the exact
  resume point. Re-run `verify`; either continue with a fresh plan into a
  fresh destination or `rollback` the partial run.
- **Wrong canonical pick discovered later**: do not patch files. Append a
  corrective plan (new canonical, old canonical becomes alias) and apply
  it; the journal then shows decision → correction, which is the audit
  trail reviewers want.
- **Conflicting admin notes** (two notes disagree on which version is
  current): keep both statements in `VERSIONS.json.notes_rules`, set
  `needs_review: true`, and state the conflict in result.json instead of
  picking one silently.

## 5. What to write into result.json change_records

One entry per executed phase: `{phase, tool, artifact, journal_seq_range,
status}`. Skips and conflicts get their own entries with the file path and
the OS/verification message verbatim.
