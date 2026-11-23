# ga-archetype-forge (Bundle B)

**One-line:** pick one of five layout archetypes, fill it with
source-anchored content, and let machines prove the typography and record
the export.

## Why this direction

Graphical abstracts live or die on layout: reading order, slot discipline,
font floors, colour-blind safety, export compliance. Instead of asking the
model to invent geometry (and fail in new ways each run), this skill ships
five hand-tuned SVG skeletons (`linear-pipeline`, `hub-mechanism`,
`compare-split`, `layered-stack`, `data-panel`) whose geometry already
encodes the rules, plus an auditor that proves — with font metrics — that no
text overflows, no font is below 8 px, and every text/background pair meets
WCAG contrast. Independent of any spec-compiler: the model never writes a
layout DSL, it fills archetype-shaped params.

## Contents

| File | Role |
|---|---|
| `SKILL.md` | protocol, archetype decision table, failure handling |
| `scripts/archetypes.py` | the five skeleton builders (pure stdlib SVG) |
| `scripts/forge_svg.py` | params + archetype → SVG; refuses unanchored content via `--pool` |
| `scripts/canvas_audit.py` | blocking layout gate (overflow / font floor / contrast / canvas / layers) |
| `scripts/export_preview.py` | rsvg-convert → inkscape → soffice+pdftoppm chain with honest report |
| `scripts/write_result.py` | early-partial + milestone result.json writer |
| `references/archetype_guide.md` | params schema per archetype |
| `references/style_tokens.md` | Okabe-Ito tokens, typography, canvas discipline |
| `examples/minimal_example.md` | runnable hub-mechanism demo (marked as example) |

## Dependencies

Python 3.9+ stdlib only for forging and audit. Export uses whatever exists
among rsvg-convert / inkscape / soffice / pdftoppm; none required for the
SVG itself. No network.

## Usage

See `SKILL.md` §Protocol: scaffold result → build pool → choose archetype →
params → forge (anchor-checked) → audit (layout gate) → export → finalize.

## Self-verification performed by the author

All five archetypes forged from the demo params and passed
`canvas_audit.py`. The audit caught three genuine defects during
development (hub-label contrast, orbit collision, dark-on-dark text), which
were fixed in the builders before shipping. Export chain tested for its
honest-failure path (no exporters on the authoring machine).

## Maintenance

Adding an archetype = adding one builder function in `archetypes.py` with
labelled layers and `data-max-w` on every text; the audit then covers it
automatically. Issues via the GitHub repo in `GITHUB_URL.txt`.
