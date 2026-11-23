---
name: ga-archetype-forge
description: >-
  Forge a graphical abstract from a library of five hand-tuned SVG layout
  archetypes (linear pipeline, hub mechanism, compare split, layered stack,
  data panel) with a machine layout audit and honest export chain. Trigger
  when the task asks for a graphical abstract / 图形摘要 / schematic summary
  figure where visual hierarchy, reading order, typography, colour-blind
  safety and export compliance matter: pick the archetype that matches the
  story shape, instantiate it with source-anchored content, prove no text
  overflows and no contrast fails, then export SVG + PNG + PDF with a
  recorded tool chain.
---

# ga-archetype-forge

A visual-grammar approach. Most agent-drawn abstracts fail on **layout**:
reading order unclear, text overflowing shapes, 5-pt labels, red/green
encodings. This skill makes layout a solved problem by construction: five
archetype skeletons carry the typographic rules in their geometry, every
text element declares its container width (`data-max-w`), and
`canvas_audit.py` proves — with a font-metrics estimate — that nothing
overflows, nothing is too small, and every text/background pair has WCAG
contrast. The agent's job is choosing the right archetype and filling it
with anchored content, not nudging coordinates.

## Runtime contract (DeepSeek Harness)

- Skill at `/skills/weekly-skill`. Inputs: `/input/case.json`, `/input/task.md`
  and the case materials. **Read the actual files** — the PDF has no
  pre-extracted answer layer (use pdf-text-tool / pdf-render-tool / ocr-tool
  as needed).
- Deliver under `/app/output`: `graphical_abstract.svg` (layered, labelled
  groups, editable text), `graphical_abstract.png` (300 dpi) and
  `graphical_abstract.pdf` when an exporter exists (chain below — a missing
  exporter is an **exception in result.json**, never a silent skip),
  `params.json` (the true editable source), `result.json` with the original
  `case_id` and all `output_contract` fields, honest status / limitations /
  milestones.
- Budgets: 64 model requests, 900 s, 16384 tokens per response. **Write an
  early-partial `result.json` with `write_result.py` before drawing.**
- Never fabricate source content. Labels and numbers must come from the
  materials; `forge_svg.py --pool` refuses to forge unanchored content.

## Protocol

```
0  result scaffold .. write_result.py            (before anything else)
1  read materials ... extract pool (any pdftotext; snippet in SKILL.md)
2  choose archetype . decision table below       (you)
3  fill params ...... params.json + sources[]    (you — the creative step)
4  forge ............ forge_svg.py --pool        (machine; refuses bad anchors)
5  LAYOUT GATE ...... canvas_audit.py            (machine; must PASS)
6  export ........... export_preview.py          (machine; records tool chain)
7  finalize ......... write_result.py --status complete
```

### Step 1 — source pool (minimal)

```bash
mkdir -p /app/work && : > /app/work/source_pool.txt
for f in /input/*.pdf; do pdftotext -layout "$f" - >> /app/work/source_pool.txt; done
for f in /input/*.txt /input/*.md /input/*.csv; do cat "$f" >> /app/work/source_pool.txt; done
```

(For image-only or scanned sources use the ocr-tool first and note it in
`limitations`.)

### Step 2 — choose the archetype (decision table)

| Story shape in the materials | Archetype |
|---|---|
| A → B → C → D pipeline, workflow, synthesis route | `linear-pipeline` |
| one central entity acted on by / driving several factors | `hub-mechanism` |
| treatment vs. control, before vs. after, ours vs. theirs | `compare-split` |
| device stack, tissue strata, membrane layers | `layered-stack` |
| the headline IS quantitative (bars/lines from source data) | `data-panel` |

One archetype per figure. If two seem to fit, prefer the one matching the
**conclusion**, not the methods, and record the rejected option in
`milestones`.

### Step 3 — fill `params.json`

Per-archetype fields: `references/archetype_guide.md`. Style rules:
`references/style_tokens.md` (colour tokens are the Okabe-Ito
colour-blind-safe set; roles, not decoration, drive colour). Every factual
label/number must ALSO appear in `params.sources[]` as
`{locator, quote}` with a verbatim quote from the pool — the forge checks.

### Steps 4–6 — forge, gate, export

```bash
python3 /skills/weekly-skill/scripts/forge_svg.py \
    --archetype hub-mechanism --params /app/work/params.json \
    --out /app/output/graphical_abstract.svg --pool /app/work/source_pool.txt
python3 /skills/weekly-skill/scripts/canvas_audit.py \
    --svg /app/output/graphical_abstract.svg --json /app/work/audit_report.json
python3 /skills/weekly-skill/scripts/export_preview.py \
    --svg /app/output/graphical_abstract.svg --outdir /app/output \
    --report /app/work/export_report.json
```

- Forge exit 1 ⇒ anchor quotes are not verbatim: fix params, re-forge.
- Audit exit 1 ⇒ concrete layout defects (element id + measured widths):
  shorten the label or switch that element's slot; never lower the font
  floor below 8 px.
- Export: `rsvg-convert → inkscape → soffice (+pdftoppm)`. Whatever ran is
  recorded; if nothing ran, deliver the SVG + audit and record the exception.

## Failure handling

| Situation | Action |
|---|---|
| Story fits no archetype | pick nearest + put the mismatch in `limitations`; do NOT hand-draw free-form SVG (that abandons the guarantee) |
| Label does not fit its slot even after shortening | move detail into the legend strip or subtitle; keep the slot short |
| Number in params not in pool quote | forge refuses; find the verbatim sentence or drop the number |
| No SVG exporter in environment | deliver SVG + report; add exception; do not claim a PNG exists |
| Materials contradict each other | show the primary source's version; record the conflict in `limitations` |

## Self-check before finalizing

1. `canvas_audit.py` PASS on the exact delivered SVG.
2. `export_report.json` names the tool that produced PNG/PDF (or the honest
   failure).
3. `params.sources[]` non-empty; every headline number has a quote.
4. PNG preview actually opened once by you — geometry passed the audit, but
   you confirm the reading order matches problem → method → result →
   conclusion.
5. `result.json` complete: case_id, artifacts, archetype_choice + reason,
   anchor_report, layout_audit, export_report, exceptions, limitations,
   milestones.

## Scope and limits

The archetypes encode single-page graphical abstracts, not multi-panel
journal figures; the data panel does simple bar/line charts (not
publication statistics). Editing an EXISTING provided figure is out of
scope for this bundle — that is a different task shape. See
`examples/minimal_example.md` for a runnable demo (marked as example).
