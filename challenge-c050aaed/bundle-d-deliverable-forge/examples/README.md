# Examples — SYNTHETIC fixtures for deliverable-forge

Everything in this directory is **synthetic**: `sources/demo_paper/` is
hand-written fixture text (labeled synthetic inside the files), not a real
paper. `annotations.jsonl` simulates an extractor's output (5 annotations:
highlights / underline / margin note, with colors). `drafts.jsonl` holds
5 valid typed drafts (one per note type) plus **1 deliberately bad draft**
(`n-bad-1`) whose quote does not occur on the cited page.

All commands assume you run them from this `examples/` directory with
`S=../scripts` (or `S=/skills/weekly-skill/scripts` in the eval env).
Observed real outputs are recorded in `EXPECTED.md`.

## 1. Full run including the bad draft — gate must fail (exit 3)

```bash
python3 $S/compose_notes.py --annotations annotations.jsonl \
    --sources-dir sources --drafts drafts.jsonl --out /tmp/notes_all.jsonl
# -> exit 0: all 6 drafts are structurally valid (the bad quote is
#    resolvable as a locator; badness is semantic, caught by verify)

python3 $S/verify_claims.py --notes /tmp/notes_all.jsonl \
    --sources-dir sources --out /tmp/claims_all.json
# -> exit 3: UNVERIFIED note n-bad-1: quote_not_found
```

## 2. Valid-only run — full pipeline passes (exit 0)

```bash
head -n 5 drafts.jsonl > /tmp/drafts_valid.jsonl
python3 $S/compose_notes.py --annotations annotations.jsonl \
    --sources-dir sources --drafts /tmp/drafts_valid.jsonl --out /tmp/notes.jsonl
python3 $S/verify_claims.py --notes /tmp/notes.jsonl \
    --sources-dir sources --out /tmp/claims_report.json
# -> exit 0, verified_rate 1.0
```

## 3. Render deliverables

```bash
python3 $S/render_deliverables.py --notes /tmp/notes.jsonl \
    --claims-report /tmp/claims_report.json --sources-dir sources \
    --out-dir /tmp/deliverables --example
# -> /tmp/deliverables/{notebook.md, index.html, manifest.json}
```

## 4. Human-edit retention: snapshot / edit / diff

```bash
python3 $S/render_deliverables.py --out-dir /tmp/deliverables --snapshot before-edit
# ... edit /tmp/deliverables/notebook.md by hand (change one line) ...
python3 $S/render_deliverables.py --out-dir /tmp/deliverables --snapshot after-edit
python3 $S/render_deliverables.py --out-dir /tmp/deliverables --diff before-edit after-edit
# -> /tmp/deliverables/change_records/diff-before-edit-to-after-edit.diff
```

## 5. Negative test: structurally invalid draft (compose exit 3)

```bash
printf '%s\n' '{"note_id":"n-invalid","note_type":"summary","claim":"x","evidence":[]}' \
    > /tmp/drafts_invalid.jsonl
python3 $S/compose_notes.py --annotations annotations.jsonl \
    --sources-dir sources --drafts /tmp/drafts_invalid.jsonl --out /tmp/notes_inv.jsonl
# -> exit 3, INVALID n-invalid: note_type 'summary' not in [...], evidence empty
```
