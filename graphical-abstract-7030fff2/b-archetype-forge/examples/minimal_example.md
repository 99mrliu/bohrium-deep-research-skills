# Minimal example (EXAMPLE — not a formal case result)

Bundle B loop on a synthetic cell-biology snippet, using `hub-mechanism`.

## Input material (`material.txt`)

```
We treated HeLa cells with 5 uM staurosporine for 6 h and observed caspase-3 activation.
Cell viability decreased from 100% to 42% after treatment, measured by CCK-8 assay.
Apoptosis was confirmed by Annexin V staining.
```

## Calls

```bash
: > /app/work/source_pool.txt && cat /input/material.txt >> /app/work/source_pool.txt
python3 scripts/write_result.py --case /input/case.json --outdir /app/output \
    --status early-partial --milestone "pool ready"
python3 scripts/forge_svg.py --archetype hub-mechanism \
    --params /app/work/params.json --out /app/output/graphical_abstract.svg \
    --pool /app/work/source_pool.txt
python3 scripts/canvas_audit.py --svg /app/output/graphical_abstract.svg \
    --json /app/work/audit_report.json
python3 scripts/export_preview.py --svg /app/output/graphical_abstract.svg \
    --outdir /app/output --report /app/work/export_report.json
python3 scripts/write_result.py --case /input/case.json --outdir /app/output \
    --status complete --milestone "forged + audited + exported"
```

## params.json (hub-mechanism)

```json
{"title": "Staurosporine induces apoptosis in HeLa cells",
 "canvas": {"w": 691, "h": 320},
 "center": {"label": ["HeLa cells"]},
 "satellites": [
  {"label": ["Staurosporine", "5 uM, 6 h"], "role": "intervention",
   "angle_deg": 180, "edge": "in", "edge_label": "treatment"},
  {"label": ["Caspase-3", "activation"], "role": "process",
   "angle_deg": 60, "edge": "out"},
  {"label": ["Apoptosis", "Annexin V+"], "role": "outcome",
   "angle_deg": -60, "edge": "out"},
  {"label": ["Viability 42%", "(CCK-8)"], "role": "condition",
   "angle_deg": 0, "edge": "out", "edge_label": "readout"}],
 "sources": [
  {"locator": "material.txt line 1",
   "quote": "We treated HeLa cells with 5 uM staurosporine for 6 h and observed caspase-3 activation."},
  {"locator": "material.txt line 2",
   "quote": "Cell viability decreased from 100% to 42% after treatment, measured by CCK-8 assay."},
  {"locator": "material.txt line 3",
   "quote": "Apoptosis was confirmed by Annexin V staining."}],
 "legend": [{"color_token": "intervention", "label": "treatment"},
            {"color_token": "outcome", "label": "phenotype"}]}
```

## Expected output (verified during authoring)

- `forge_svg.py`: `forged: true`, 3 anchored sources. A tampered quote
  (`5 μM` for `5 uM`) makes it exit 1 with `anchor_problems`.
- `canvas_audit.py`: PASS. During development it caught three real defects
  in earlier skeleton revisions (hub text contrast 1.00:1, satellite/hub
  collision at small canvas heights, dark text on a dark stack layer) —
  all fixed in the shipped builders; that is the audit doing its job.
- `export_preview.py`: on machines with rsvg-convert/inkscape/soffice it
  produces `graphical_abstract.pdf` + 300-dpi PNG and records the tool; in a
  bare environment it reports `status: failed` honestly and the SVG + audit
  remain the deliverable.

The same material re-cast as `compare-split` and `data-panel` also passes
the audit (params sketches in the git history of the repo in
GITHUB_URL.txt).
