# Minimal end-to-end example (ILLUSTRATIVE — not a formal case result)

This walkthrough uses a synthetic 3-page mock paper. Every output shown is a
示意 (illustration) of shape, not real case content.

## 0. Inputs

```
/input/case.json      {"case_id": "demo-001", "output_contract": ["deck", "evidence_map"]}
/input/mock_paper.pdf (3 pages: abstract w/ "accuracy of 92.3% on the XYZ dataset",
                       "2. Method" heading, Figure 1 loss plot, Table 1 statistics)
```

## 1. PASS 1 — extract

```bash
python3 /skills/weekly-skill/scripts/extract_evidence.py \
    --pdf /input/mock_paper.pdf --outdir /app/work
# stdout (示意): {"status":"ok","pages":3,"sections":2,"figures":1,"tables":1,
#                 "fact_pool_sentences":4,"rendered_pages":3,...}
```

`evidence_index.json` now contains (示意):

```json
{"figures": [{"id":"1","caption":"Figure 1: Convergence of loss over 200 epochs","page":2,"heuristic":true}],
 "tables":  [{"id":"1","caption":"Table 1: Dataset statistics","page":3,"heuristic":true}],
 "fact_pool":[{"page":1,"sentence":"Our method achieves an accuracy of 92.3% on the XYZ dataset.","heuristic":true}]}
```

Open `/app/work/pages/page-2.png` → confirm Figure 1 is a plotted curve
(= data figure), not a schematic.

## 2. PASS 2 — plan + gate

`/app/work/slide_plan.json` (示意, one good and one mutated bullet):

```json
{"slides":[{"id":"s2","kind":"results",
  "claim":"92.3% accuracy on XYZ.",
  "bullets":[
    {"text":"92.3% accuracy on the XYZ dataset",
     "quote":"Our method achieves an accuracy of 92.3% on the XYZ dataset.",
     "locator":{"page":1},"status":"supported"},
    {"text":"93.2% accuracy on the XYZ dataset",
     "quote":"Our method achieves an accuracy of 93.2% on the XYZ dataset.",
     "locator":{"page":1},"status":"supported"}],
  "figure_ref":"Figure 1","figure_class":"data","notes":"","evidence":[]}]}
```

```bash
python3 /skills/weekly-skill/scripts/check_plan.py --plan /app/work/slide_plan.json \
    --index /app/work/evidence_index.json --paper /app/work/paper.txt
# -> plan_check: FAIL (2 findings) ... exit 1
# findings: bullet[1] quote_not_verbatim + unbacked_number ('93.2 %')
```

Fix bullet[1] back to `92.3%` with the verbatim quote → re-run → `PASS`, exit 0.

## 3. BUILD + AUDIT

Build `deck.pptx` (python-pptx or stdlib). Suppose the deck accidentally
contains "93.2%" on slide 2 and a fabricated `Figure 4`:

```bash
python3 /skills/weekly-skill/scripts/audit_deck.py --deck /app/output/deck.pptx \
    --index /app/work/evidence_index.json --paper /app/work/paper.txt \
    --report /app/output/audit_report.json --plan /app/work/slide_plan.json
# -> audit: FAIL -- 2 finding(s), 2 unresolved ... exit 1
# F001 slide 2 unbacked_number '93.2 %' ; F002 slide 3 unknown_ref 'Figure 4'
```

Repair: correct the number to `92.3%`, change the citation to `Figure 1` →
re-audit → `PASS`, exit 0. If a finding must be accepted (rare), add a
disposition with a reason and re-run with `--dispositions`.

## 4. Deliver

```
/app/output/deck.pptx            editable deck
/app/output/deck.pdf, preview-*.png
/app/output/evidence_map.json    per-slide claim -> locator + verbatim quote + status
/app/output/audit_report.json    verdict: pass
/app/output/result.json          case_id + output_contract fields + status/uncertainty
```

```bash
python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json \
    --out /app/output/result.json --status complete \
    --uncertainty "Table 1 caption is heuristic; confirmed visually on page-3.png" \
    --note "audit passed, delivered"
```
