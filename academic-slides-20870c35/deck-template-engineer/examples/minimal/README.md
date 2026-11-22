# Minimal invocation example (illustrative, synthetic)

Interface demonstration only; the deck, template and QA values are **synthetic**, not a formal case result.

## Input (hypothetical)

- `/input/case.json` — `case_id: "DEMO-SYNTH"`, output contract root fields `case_id, status, editable_source, export_artifact, content_map, compliance_checks, exceptions`.
- `/input/artifacts/slide-workorder.json` — mode: create; 8 slides; template `target-template.pptx`; export PDF required; Chinese deck.
- `/input/paper.pdf` — hypothetical source paper.

## Invocation

> Use deck-template-engineer on the work order, template and paper under /input; deliver the compliant deck, render QA report, previews and result.json to /app/output.

## What the agent does

1. Contract intake; early `result.json` (`partial`); tool census finds `soffice`, poppler, `fc-list :lang=zh` → one CJK family.
2. Forensics: `python3 scripts/inspect_deck.py /input/target-template.pptx --out /app/work/inspect_template.json` → 16:9, 1 master, 11 layouts, theme fonts recorded (see `inspection.example.json` for the shape).
3. `layout_map.json`: 8 slides mapped to Title Slide / Title and Content / Section Header / Two Content; one free-text fallback logged for a figure caption.
4. Build inside the template with python-pptx; figures cropped from rendered paper pages at 150 dpi with margins; version snapshots in `/app/work/versions/`.
5. QA: `python3 scripts/render_qa.py /app/output/presentation.pptx --outdir /app/output --out /app/output/render_qa.json --expected-pages 8 --theme-fonts "<theme fonts>"` → page count 8/8, no blanks, one overflow suspect on slide 6 confirmed visually and fixed by shortening the caption; `pdffonts` shows the theme fonts only.
6. Visual pass over the contact sheet; `changelog.md` records the slide-6 repair; `result.json` finalized with observed compliance values (renderer version, fonts, page count, SHA-256) and `status: complete`.

## Illustrative artifact

`inspection.example.json` — the shape of the phase-1 forensics report. Marked as an example; reuse the format, never the content.
