# Style tokens and typography rules (Bundle B)

## Colour tokens (Okabe-Ito, colour-blind safe)

| Token | Hex | Use for |
|---|---|---|
| `ink` | #1a1a1a | text, strokes, arrows |
| `entity` | #56B4E9 sky blue | research objects (cells, molecules, materials) |
| `process` | #009E73 bluish green | mechanisms, transformations |
| `outcome` | #E69F00 orange | results, phenotypes |
| `condition` | #F0E442 yellow | experimental conditions |
| `intervention` | #D55E00 vermillion | treatments, stimuli |
| `control` | #999999 grey | controls, baselines |
| `accent` | #0072B2 blue | hub, headline data series |
| `purple` | #CC79A7 reddish purple | secondary data series |
| `band` | #F2F2F2 | panel backgrounds |

Colour encodes **role**, never decoration. If the source uses red/green
semantics (e.g. up/down regulation), map them to vermillion/bluish-green and
say so in `limitations` — do not reintroduce a red/green pair.

## Typography

- Font stack `Helvetica, Arial, sans-serif`; sizes: title 17 px bold,
  subtitle 11 px, headings 13 px, body labels 9–11 px, small print ≥ 8 px.
  8 px at 96 px/in = 6 pt — the floor the audit enforces. Never below it.
- Labels are noun phrases; verbs live on arrows. One idea per slot.
- Units always with the number and in the axis/legend, matching the source
  exactly (µM vs uM: use what the source prints).

## Canvas discipline

- One page, one reading order: problem → method → result → conclusion,
  left→right or top→bottom; the archetype geometry enforces this.
- Whitespace is load-bearing: if the audit passes only after shrinking three
  labels, the content is overloaded — drop the least important element into
  the legend/subtitle instead.
- Every text element carries `data-max-w` (its container width in px). The
  audit's overflow proof is exact for forged SVGs; if you hand-add elements,
  you must add `data-max-w` yourself or the audit falls back to a canvas
  heuristic and says so.

## Export compliance

- SVG: width/height + viewBox always present; labelled layer groups
  (`inkscape:label`) for title / body / legend.
- PNG: 300 dpi default (canvas × 3.125 px). PDF via the recorded tool chain.
- A missing exporter is reported, not faked — the SVG plus audit report is
  still a deliverable.
