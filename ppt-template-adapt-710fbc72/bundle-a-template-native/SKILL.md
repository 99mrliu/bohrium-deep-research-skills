---
name: template-native-deck
description: Build an academic slide deck that genuinely inherits a given PowerPoint template (master/layout/placeholder level), with an explainable font-size ladder, overflow-by-splitting discipline, batch-consistent footers and slide numbers, and verified PDF/PNG export. Use when a paper or research material must be fitted into a fixed .pptx template with binding slide-count, audience, or time constraints.
---

# Template-native deck building (模板套用 + 版式约束方向)

This skill specializes in ONE problem: making the organizer's template genuinely
applied — real master/layout/placeholder inheritance, content fitted inside the
layout's geometry with an explainable size ladder, and the whole deck (not just
the first pages) batch-consistent — then proving it with structural audits and a
verified export. Content selection itself follows the paper; this skill owns the
*typography-and-template* half of the task.

## Contract first

1. Read `/input/case.json` and `task.md`. `output_contract` controls result
   field names; the task's fixed **audience, duration and slide count are
   binding**. Work in `/app/work`; final artifacts (deck, PDF, previews,
   reports, `result.json` with original `case_id`) go to `/app/output`.
   Save a valid partial result early, then improve. Never fabricate paper
   content or check results.
2. Probe the environment once, up front, and record findings in the change
   log: `python3 -c "import pptx"` (else `pip install python-pptx`; if that
   fails too, report `partial` and edit template XML per
   `references/pptx-recipes.md` §4), a renderer (`soffice`/`libreoffice` or
   the runtime office-renderer tool), `pdftotext`/`pdftoppm`, and CJK font
   availability (`fc-list :lang=zh` or the font-discovery tool).

## Workflow (scripts live under /skills/weekly-skill/scripts/)

### 1. Map the template before writing anything

```
python3 scripts/template_map.py <template.pptx> --out /app/work/template_map.json
```

The map is the ONLY authoritative source for layout choice: slide size, theme
fonts (latin + East Asian), theme colors, and each layout's name, index and
placeholders (`idx`, type, geometry, `inherits_position`). Never hand-build a
layout or recreate the theme. If a starting deck is supplied instead, map it
the same way and pass `--keep-existing` only when the task says to edit it.

### 2. Extract paper mainline and write the page plan

Extract text (`pdftotext -layout`, keep page breaks) and inspect any figure
you will cite on the rendered page (`pdftoppm -png -r 150 -f N -l N`).
Form the mainline: question → method → results (each anchored to a figure/
table/section) → limitations. Allocate the fixed slide count: cover, outline
(optional), background/question, method, one results page per key figure or
table, limitations, conclusion. Write `/app/work/plan.json` in the schema of
`scripts/build_deck.py`'s docstring: per slide the **layout name from the
map**, title, bullets (nested lists for level-2), optional images with
caption + source anchor, optional native table, footer text, and speaker
notes (~240 Chinese chars or 140 English words per minute of the slot).

Rules while planning:
- Choose layouts by function: cover → the title layout; figure+commentary →
  a picture/caption layout if the map has one; two-column comparisons → the
  two-content layout. Do not force everything into one layout.
- Plan one claim per slide. If content needs a font below 12 pt to fit,
  split it into two slides instead (slide-count permitting).
- Every figure cites its paper location in the caption
  (`Fig. 3 stays Fig. 3`); extract figures at native resolution — render the
  PDF page region at 200–300 dpi, never upscale small rasters.

### 3. Build inside the real template

```
python3 scripts/build_deck.py --template <template.pptx> \
    --plan /app/work/plan.json --out /app/output/deck.pptx \
    --report /app/output/build_report.json
```

The builder opens the template file itself (inheritance is real), fills
placeholders by `idx`/type, fits images with aspect ratio preserved (effective
dpi ≥ 96 or it warns), applies the body ladder 18→16→14→12 pt and flags — not
hides — remaining overflow, instantiates footer and slide-number placeholders
on every content slide by cloning the layout's placeholder XML (real
inheritance, not floating text boxes), and writes notes. **Read every warning
in the build report and resolve it** (shorten, split, pick a better layout);
unresolved warnings must be justified in the change log.

Geometry rule the builder enforces and you must keep in any manual edit: set
**all four of left/top/width/height or none** — a partial xfrm zeroes the
inherited values and overlaps the title band.

### 4. Structural audit

```
python3 scripts/audit_deck.py /app/output/deck.pptx \
    --template <template.pptx> --min-slides N --max-slides M \
    --duration-minutes T --out /app/output/audit.json
```

Checks: slide count in range; each slide's layout part really exists in the
template package; non-empty titles at one consistent position; no font below
12 pt; estimated overflow; image distortion and effective dpi; footer and
slide-number placeholders on every content slide; notes volume vs the talk
budget. Fix all `fail`; fix or explicitly justify every `warn`.

### 5. Export and verify the rendering

```
python3 scripts/export_check.py /app/output/deck.pptx /app/output/export.pdf \
    --expect "<deck title>" --expect "<one figure caption>" \
    --theme-fonts <major,minor from template_map> \
    --previews /app/output/previews --out /app/output/export_check.json
```

The script drives LibreOffice headless with a private profile (auto-retry on
`DeploymentException`), checks PDF page count == slide count, expected strings
present, theme fonts visible in the PDF (substitution = warning to record),
and renders PNG previews. **Open at least the first, the densest, and the
last preview** and look at them — overlaps and wrapped titles are only
visible in rendering. If the theme font is missing in the export environment,
pick a metric-compatible installed fallback (font-discovery / `fc-list`),
note the substitution in the change log; do not silently accept tofu.

### 6. Evidence mapping and honest result

Write `/app/output/evidence_map.json`: one entry per slide —
`{"slide": n, "claim": "...", "sources": [{"kind": "figure|table|section|text",
"ref": "Fig. 3", "pdf_page": 7, "quote": "short verbatim anchor"}]}` — and a
change log of placeholder substitutions, splits, font fallbacks, and export
retries. Assemble `/app/output/result.json` with the original `case_id`,
every `output_contract` field, honest `status`
(`success`/`partial`/`unable_to_determine`), artifact paths, sources with
exact locations, and uncertainty. Prove the contract:

```
python3 scripts/check_result.py --case /input/case.json \
    --result /app/output/result.json --base /app \
    --out /app/output/result_check.json
```

## Failure handling

| Situation | Action |
|-|-|
| Template missing/unreadable | `partial`; build on nearest available template only if the task allows; record |
| Needed placeholder missing in best layout | Pick another layout from the map; else the builder substitutes an aligned text box and logs it |
| Body overflows at 12 pt floor | Split the slide (slide-count permitting) or cut content; never shrink below floor |
| Long title | Shorten to ≤ 2 lines at the layout's title size |
| Font missing at export | Metric-compatible fallback + re-export + change-log entry |
| LibreOffice crashes (`DeploymentException`) | Already retried with private profile; if it still fails deliver pptx + diagnostics as `partial` |
| PDF page count ≠ slide count | Inspect for hidden/blank slides; rebuild |
| python-pptx unavailable | `pip install`; else `partial` with XML route per references §4 |

## Minimal invocation example (illustrative, not an official case result)

Input: `paper.pdf`, `lab_template.pptx`, task "10 slides, 12 min, group
seminar". Steps: `template_map.py` → plan 10 slides → `build_deck.py` →
`audit_deck.py --min-slides 10 --max-slides 10 --duration-minutes 12` →
`export_check.py --expect "<title>"` → evidence map → `result.json` →
`check_result.py`. Illustrative output: `deck.pptx` whose results slide uses
the template's picture layout with the page-7 plot at native aspect ratio,
`audit.json` reporting `pass`, and a 10-page PDF whose fonts match the theme.

## Limits

Scripts check structure, not science — verify content against the source
yourself. The line-count overflow estimator is a heuristic; the rendered
previews are the final arbiter. The builder supports title/bullets/images/
tables/notes; free-form diagrams should be pre-rendered to images and cited.
