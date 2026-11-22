# Render checks: what the loop audits and why

## The check battery (per iteration, on the rendered PDF)

| Check | Signal | Typical cause |
|-|-|-|
| page_parity | PDF page count vs slide count | hidden slides, crashed export |
| blank_page | page with no words and no text | lost images, broken slide part |
| clipped_text | `pdftotext -bbox` words outside the page rect | text box extends off-slide |
| title_missing | slide title absent from its PDF page | title placeholder emptied or clipped |
| text_lost | any paragraph (≥ 8 chars) absent from its PDF page | overflow beyond the slide edge; the renderer clips it |
| font list | `/BaseFont` names in the PDF | theme font absent in the export environment → substitution |

Substring checks compare **whitespace-free** text on both sides: renderers
insert CJK–latin autospacing and re-wrap lines, so naive substring matching
produces false "lost text" alarms.

## Repair policy

- Repairable: `clipped_text`, `text_lost`, `title_missing` on specific
  slides → every run on that slide −2 pt (floor 12 pt), re-render.
- Not font-repairable: `page_parity`, `blank_page` → stop and inspect.
- Still failing at 12 pt → the content does not fit; split the slide. The
  deviation table in `render_report.json` is the honest record and must be
  disclosed in `result.json` uncertainty.

## LibreOffice headless notes

```
soffice --headless --norestore --nolockcheck \
  -env:UserInstallation=file://<private profile> \
  --convert-to pdf --outdir <dir> deck.pptx
```

- Bare first runs on a fresh machine commonly fail with
  `DeploymentException`; the private profile + one retry handles it.
- Output file name is `<deck basename>.pdf` in `--outdir`.
- The export uses environment fonts only; a missing theme font shows up in
  the PDF font list as a substitute (e.g. Calibri → Carlito).

## Batch-consistency rules (whole deck, not first pages)

- Title band: same (left, top) on every content slide.
- Body fonts: one ladder (e.g. 18/16/14/12), second level −2 pt; spread
  beyond ~8 pt across the deck suggests drift; anything < 12 pt fails.
- Apparatus: footer and slide-number placeholders on *all* content slides
  or none; partial application fails the audit.
- Margins: body boxes share a common left edge.
- Notes: present on every slide; total volume ≥ ~50% of the talk budget at
  240 CJK chars/min (or 140 latin words/min).
