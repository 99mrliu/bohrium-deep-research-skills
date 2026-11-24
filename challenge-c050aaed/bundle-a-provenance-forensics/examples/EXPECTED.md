# EXPECTED — real observed output

Everything below was actually produced by running the commands in
`README.md` against `fixtures/` (Python 3 stdlib, macOS arm64, 2026-11-24).
`$T` is a fresh `mktemp -d` directory. Hash values are deterministic
functions of the fixture bytes, so the sha256 values and audit-log
entry hashes below must reproduce exactly on any machine; only paths and
mtime values vary.

## 1. Inventory

```
$ python3 scripts/forensic_inventory.py --dir $T/materials --out $T/work/manifest.json
inventory written: $T/work/manifest.json
total_files=8 readable=6 encrypted=1 empty=0 mismatched_extension=1 unreadable_or_denied=0 duplicate_groups=1 version_suspect_groups=1
exit=0
```

Per-file classifications observed in `manifest.json`:

| relpath | classification | sniffed | ext | mismatch | pdf_encrypted | size |
|---|---|---|---|---|---|---|
| archive/a-backup.txt | readable | utf8_text | .txt | false | false | 64 |
| data.pdf | mismatched_extension | utf8_text | .pdf | true | false | 99 |
| locked.pdf | encrypted | pdf | .pdf | false | true | 139 |
| notes/a.txt | readable | utf8_text | .txt | false | false | 64 |
| notes/b.txt | readable | utf8_text | .txt | false | false | 61 |
| paper.pdf | readable | pdf | .pdf | false | false | 111 |
| report (1).pdf | readable | pdf | .pdf | false | false | 78 |
| report.pdf | readable | pdf | .pdf | false | false | 56 |

Duplicate group (1 group, 2 members, sha256 starts `412eec3f8a4b`):

```json
{"sha256": "412eec3f8a4b2a3d7cd591769adf10fd981e9e49a40599bceb7d1d6543f8db85",
 "size": 64,
 "members": ["archive/a-backup.txt", "notes/a.txt"]}
```

Version-suspect group (1 group, normalized stem `report`, 2 distinct hashes):

```json
{"normalized_stem": "report",
 "members": [
   {"relpath": "report (1).pdf", "sha256": "c41f9c935857e30a4609fa35298fca2000e6bed22461a559583648e91ee7f4a7"},
   {"relpath": "report.pdf",     "sha256": "c58397a5041925dfa3834db6bfd19df22b4aeb99ad9d2d655ceb581da1242aeb"}]}
```

Manifest summary block:

```json
{"total_files": 8,
 "classification_counts": {"encrypted": 1, "mismatched_extension": 1, "readable": 6},
 "duplicate_groups": 1, "version_suspect_groups": 1,
 "encrypted_files": 1, "empty_files": 0,
 "extension_mismatch_files": 1, "unreadable_or_denied_files": 0}
```

## 2. Audit log appends (3 entries) and verify

```
$ python3 scripts/audit_log.py append --log $T/work/audit.jsonl --op inventory --detail tool=forensic_inventory.py --detail out=work/manifest.json
{"seq": 1, "op": "inventory", "details": {"tool": "forensic_inventory.py", "out": "work/manifest.json"}, "prev_sha256": "0000000000000000000000000000000000000000000000000000000000000000", "entry_sha256": "261ec74046108c73406625ce264cfb16dfb0d6ce19a8ec74987dd6af96c9aa65"}
exit=0

$ python3 scripts/audit_log.py append --log $T/work/audit.jsonl --op skip --detail file=locked.pdf --detail action=skipped_encrypted --detail reason=no_password_provided
{"seq": 2, "op": "skip", "details": {"file": "locked.pdf", "action": "skipped_encrypted", "reason": "no_password_provided"}, "prev_sha256": "261ec74046108c73406625ce264cfb16dfb0d6ce19a8ec74987dd6af96c9aa65", "entry_sha256": "e6530f4b2e76e3ccc50d7a01ce4e7a22e4951a9d51b4afa12d166139b3b5f01b"}
exit=0

$ python3 scripts/audit_log.py append --log $T/work/audit.jsonl --op dedup_decision --detail canonical=notes/a.txt --detail duplicates=archive/a-backup.txt --detail rule=shortest_path
{"seq": 3, "op": "dedup_decision", "details": {"canonical": "notes/a.txt", "duplicates": "archive/a-backup.txt", "rule": "shortest_path"}, "prev_sha256": "e6530f4b2e76e3ccc50d7a01ce4e7a22e4951a9d51b4afa12d166139b3b5f01b", "entry_sha256": "2acd9fcf91f2125a36447c8eaf5862c5cd38e05c280c1c915f828a8ad3e554fd"}
exit=0

$ python3 scripts/audit_log.py verify --log $T/work/audit.jsonl
VERIFY OK: 3 entries, chain intact ($T/work/audit.jsonl)
exit=0
```

Note: the audit-log entry hashes above are fully deterministic (no
wall-clock time), so byte-identical `--detail` arguments reproduce these
exact `entry_sha256` values.

## 3. Replay check on untouched materials

```
$ python3 scripts/replay_check.py --manifest $T/work/manifest.json --dir $T/materials --out $T/work/replay_report.json
replay_check: CLEAN (added=0 removed=0 changed=0 renamed_suspects=0) report=$T/work/replay_report.json
exit=0
```

## 4. Negative test A — corrupted audit log

One hex digit flipped in the seq=1 `entry_sha256` of a copy of the log:

```
$ python3 scripts/audit_log.py verify --log $T/work/audit_bad.jsonl
VERIFY FAILED: 2 problem(s) in $T/work/audit_bad.jsonl
  - entry 1 (line 1): entry_sha256 re-computation mismatch
  - entry 2 (line 2): prev_sha256 mismatch (expected 261ec74146108c73..., got 261ec74046108c73...)
exit=3
```

Appending to a corrupt log is also refused with exit 3.

## 5. Negative test B — tampered fixture file

After appending one line to `notes/b.txt`:

```
$ python3 scripts/replay_check.py --manifest $T/work/manifest.json --dir $T/materials --out $T/work/replay_bad.json
replay_check: DIFFERENCES FOUND (added=0 removed=0 changed=1 renamed_suspects=0) report=$T/work/replay_bad.json
exit=3
```

Report content: `changed = ["notes/b.txt"]`, `added = []`, `removed = []`.

## 6. Negative test C — renamed file

After renaming an otherwise unmodified `notes/a.txt` to `notes/a-moved.txt`:

```
replay_check: DIFFERENCES FOUND (added=1 removed=1 changed=0 renamed_suspects=1)
exit=3
renamed_suspects = [{"from": "notes/a.txt", "to": "notes/a-moved.txt",
                     "sha256": "412eec3f8a4b2a3d7cd591769adf10fd981e9e49a40599bceb7d1d6543f8db85"}]
```

## 7. Determinism check

Running `forensic_inventory.py` twice on the same directory produced
byte-identical manifests (`cmp` clean). Exit codes summary: success = 0,
usage error = 2 (e.g. nonexistent `--dir`, malformed `--detail`), chain
break / differences found = 3.
