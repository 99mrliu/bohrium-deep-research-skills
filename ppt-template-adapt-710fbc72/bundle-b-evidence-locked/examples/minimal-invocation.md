# Minimal invocation example (illustrative — NOT an official case result)

## Input (synthetic)

- `paper.pdf` — a 12-page paper with 4 figures and 3 tables.
- `template.pptx` — organizer template.
- Task: "10 slides, 12 minutes, journal club."

## Invocation

"Turn paper.pdf into a 10-slide deck with the evidence-locked-deck skill."

```bash
S=/skills/weekly-skill/scripts
python3 $S/extract_source.py --pdf /input/paper.pdf --out /app/work/source_index.json
# agent reads the index, drafts /app/work/claims.json (15 claims)
python3 $S/verify_anchors.py --index /app/work/source_index.json \
    --claims /app/work/claims.json --out /app/work/claims.verified.json --fuzzy
# -> verified: 13/15 ; 2 claims rewritten or dropped
# agent writes /app/work/plan.json using only verified claims
python3 $S/build_deck.py --template /input/template.pptx \
    --plan /app/work/plan.json --out /app/output/deck.pptx \
    --evidence-map /app/output/evidence_map.json --report /app/output/build_report.json
python3 $S/check_numbers.py --deck /app/output/deck.pptx \
    --index /app/work/source_index.json --out /app/output/numbers_check.json --allow "10"
python3 $S/export_render.py /app/output/deck.pptx /app/output/export.pdf \
    --previews /app/output/previews --out /app/output/export_report.json
# agent writes /app/output/result.json, then:
python3 $S/contract_check.py --case /input/case.json \
    --result /app/output/result.json --deck /app/output/deck.pptx \
    --evidence-map /app/output/evidence_map.json --base /app \
    --out /app/output/contract_check.json
```

## Illustrative output (example only)

```json
{"slide": 6, "title": "Results on WMT 2014",
 "sources": [{"kind": "table", "ref": "Table 2", "pdf_page": 8,
              "anchor": "Transformer (big)  28.4", "status": "verified"}]}
```

Gate refusal (what a hallucinated claim looks like):

```
GATE: slide 5 has unverified evidence: ['Table 3'] — every content slide
needs verified evidence (see verify_anchors.py)
```
