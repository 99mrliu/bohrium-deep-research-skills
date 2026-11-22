# Minimal invocation example (illustrative — NOT an official case result)

## Input (synthetic)

- `paper.pdf` — 12-page paper.
- `template.pptx` — organizer template.
- Task: "10 slides, 12 minutes, lab meeting."

## Invocation

"Build the deck with the render-proof-deck skill and prove the export."

```bash
S=/skills/weekly-skill/scripts
pdftotext -layout /input/paper.pdf /app/work/paper.txt
# agent reads the paper, writes /app/work/plan.json (10 slides, body_pt 18)
python3 $S/build_deck.py --template /input/template.pptx \
    --plan /app/work/plan.json --out /app/output/deck.pptx \
    --report /app/output/build_report.json
python3 $S/render_loop.py /app/output/deck.pptx /app/output/export.pdf \
    --previews /app/output/previews --workdir /app/work \
    --out /app/output/render_report.json --max-iter 3
python3 $S/consistency_audit.py /app/output/deck.pptx --pdf /app/output/export.pdf \
    --duration-minutes 12 --out /app/output/consistency.json
# agent writes evidence_map.json + result.json, then:
python3 $S/final_check.py --case /input/case.json \
    --result /app/output/result.json \
    --render-report /app/output/render_report.json --base /app \
    --out /app/output/final_check.json
```

## Illustrative output (example only)

```
iter 1: 2 findings, 1 repairs   # slide 7 text_lost -> fonts -2 pt
iter 2: 0 findings, 0 repairs
render_loop: pass after 2 iteration(s)
```

and in `render_report.json`:

```json
{"iterations": [
  {"iteration": 1, "pdf_sha256": "…", "repairs": [
    {"slide": 7, "action": "shrink fonts -2 pt", "runs_changed": 6}]},
  {"iteration": 2, "pdf_sha256": "…", "findings": []}],
 "status": "pass"}
```

A run that cannot converge ends honestly:

```json
{"status": "fail",
 "deviation_table": [{"slide": 7, "issues": ["text_lost"]}],
 "notes": ["final render still has findings; deliver as partial …"]}
```
