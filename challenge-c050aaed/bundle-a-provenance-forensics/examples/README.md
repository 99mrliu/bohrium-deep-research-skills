# Synthetic example

A small, fully synthetic worked example (no real research content). All
fixtures are tiny text files; the "PDFs" are text files that merely start
with the `%PDF-` magic. Nothing here is a real document.

## Fixture tree (`fixtures/`, 8 files)

```
fixtures/
  notes/a.txt            plain UTF-8 text note
  notes/b.txt            plain UTF-8 text note
  archive/a-backup.txt   byte-identical DUPLICATE of notes/a.txt
  paper.pdf              fake PDF: text starting with "%PDF-1.4"
  locked.pdf             fake ENCRYPTED PDF: starts "%PDF-1.5", contains the string "/Encrypt"
  report.pdf             fake PDF, "version 1" content
  report (1).pdf         fake PDF, different "version 2" content -> VERSION SUSPECT of report.pdf
  data.pdf               EXTENSION MISMATCH: plain UTF-8 text named .pdf (does not start with %PDF-)
```

## Exact commands

```bash
SKILL=/skills/weekly-skill            # or the path of this bundle
T=$(mktemp -d)
cp -R "$SKILL/examples/fixtures" "$T/materials"
mkdir -p "$T/work"

# 1. Forensic inventory
python3 "$SKILL/scripts/forensic_inventory.py" \
    --dir "$T/materials" --out "$T/work/manifest.json"

# 2. Audit-log the step, the encrypted-file skip, and the dedup decision
python3 "$SKILL/scripts/audit_log.py" append --log "$T/work/audit.jsonl" \
    --op inventory --detail tool=forensic_inventory.py \
    --detail out=work/manifest.json
python3 "$SKILL/scripts/audit_log.py" append --log "$T/work/audit.jsonl" \
    --op skip --detail file=locked.pdf \
    --detail action=skipped_encrypted --detail reason=no_password_provided
python3 "$SKILL/scripts/audit_log.py" append --log "$T/work/audit.jsonl" \
    --op dedup_decision --detail canonical=notes/a.txt \
    --detail duplicates=archive/a-backup.txt --detail rule=shortest_path

# 3. Verify the audit chain
python3 "$SKILL/scripts/audit_log.py" verify --log "$T/work/audit.jsonl"

# 4. Replay check: others can re-run and confirm nothing changed
python3 "$SKILL/scripts/replay_check.py" \
    --manifest "$T/work/manifest.json" --dir "$T/materials" \
    --out "$T/work/replay_report.json"
```

## Negative tests (expected to FAIL verification, exit 3)

```bash
# Flip one hex digit of an entry_sha256 in a COPY of the log, then:
python3 "$SKILL/scripts/audit_log.py" verify --log "$T/work/audit_bad.jsonl"
#   -> exit 3, "entry_sha256 re-computation mismatch" + "prev_sha256 mismatch"

# Modify one fixture file, then:
python3 "$SKILL/scripts/replay_check.py" \
    --manifest "$T/work/manifest.json" --dir "$T/materials" \
    --out "$T/work/replay_bad.json"
#   -> exit 3, changed=["notes/b.txt"]
```

See `EXPECTED.md` for the real observed output of every command above,
produced by actually running them (Python 3, macOS arm64).
