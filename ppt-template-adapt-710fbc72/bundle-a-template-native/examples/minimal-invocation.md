# Minimal invocation example (illustrative — NOT an official case result)

## Input (synthetic)

- `paper.pdf` — a 12-page research paper.
- `lab_template.pptx` — organizer template with a title layout, a
  title+content layout and a picture-with-caption layout.
- Task: "10 slides, 12 minutes, group seminar, English deck."

## Invocation

Tell the agent: "Adapt paper.pdf into lab_template.pptx using the
template-native-deck skill: 10 slides, 12 minutes, with speaker notes, PDF
export and previews." The agent then runs, in order:

```bash
S=/skills/weekly-skill/scripts
python3 $S/template_map.py /input/lab_template.pptx --out /app/work/template_map.json
pdftotext -layout /input/paper.pdf /app/work/paper.txt
# agent writes /app/work/plan.json (10 slides, layout names from the map)
python3 $S/build_deck.py --template /input/lab_template.pptx \
    --plan /app/work/plan.json --out /app/output/deck.pptx \
    --report /app/output/build_report.json
python3 $S/audit_deck.py /app/output/deck.pptx --template /input/lab_template.pptx \
    --min-slides 10 --max-slides 10 --duration-minutes 12 --out /app/output/audit.json
python3 $S/export_check.py /app/output/deck.pptx /app/output/export.pdf \
    --expect "Scaling Widgets" --expect "Fig. 2" --theme-fonts "Calibri,Calibri" \
    --previews /app/output/previews --out /app/output/export_check.json
# agent writes evidence_map.json + result.json, then:
python3 $S/check_result.py --case /input/case.json \
    --result /app/output/result.json --base /app --out /app/output/result_check.json
```

## Illustrative output (example, not a real case artifact)

`audit.json`:

```json
{"status": "pass", "slides": 10,
 "findings": [{"level": "warn", "slide": 6,
   "msg": "image effective dpi 92 < 96"}]}
```

`result.json` (shape only):

```json
{"case_id": "example-01", "status": "success",
 "artifacts": {"pptx": "/app/output/deck.pptx",
               "pdf": "/app/output/export.pdf",
               "previews": "/app/output/previews"},
 "change_log": ["slide 6 figure re-rendered at 200 dpi after dpi warning"]}
```
