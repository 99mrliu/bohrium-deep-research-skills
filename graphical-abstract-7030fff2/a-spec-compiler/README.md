# ga-spec-compiler (Bundle A)

**One-line:** the model authors a source-anchored JSON spec; machines gate it
and compile it into a deterministic, editable graphical abstract.

## Why this direction

Base agents asked for a graphical abstract tend to emit a one-off SVG/bitmap
whose numbers cannot be traced and whose layout cannot be reproduced. This
skill removes the model from the drawing path entirely: creativity happens
exactly once, in a structured spec file where every factual element carries a
verbatim source quote; a deterministic compiler renders SVG/PNG/PDF. Same
spec + same matplotlib version ⇒ same figure (PDF CreationDate metadata
varies; see render_report.json).

## Contents

| File | Role |
|---|---|
| `SKILL.md` | protocol, contract, failure handling |
| `scripts/extract_materials.py` | /input → `source_pool.txt` + sha256 index + data previews (pdftotext → pypdf chain, honest degradation) |
| `scripts/check_spec.py` | blocking gate: structure, verbatim anchoring, number tracing, canvas/overflow, palette, legend/units |
| `scripts/render_spec.py` | matplotlib compiler → layered editable SVG + 300-dpi PNG + PDF |
| `scripts/make_result.py` | early-partial + final `result.json` writer |
| `references/spec_format.md` | spec grammar + gate rules |
| `references/source_anchoring.md` | verbatim-quote discipline, schematic-vs-data, prior art |
| `examples/minimal_example.md` | complete runnable demo (marked as example) |

## Dependencies

Python 3.9+, matplotlib (scientific-python tool), pdftotext (pdf-text-tool).
No network, no other packages. All scripts are stdlib + matplotlib only.

## Usage

See `SKILL.md` §Protocol. Five commands; the creative step is editing
`figure_spec.json`. The gate must pass before rendering.

## Self-verification performed by the author

Ran the example end-to-end: gate PASS, SVG contains named groups and real
text, PNG at 300 dpi. Corrupted-value spec (`42→37`) correctly fails the
gate with an S3 finding. OCR fallback path documented but not exercised
(no scanned PDF available).

## Maintenance

Scripts are deterministic and side-effect-free outside their `--outdir`.
Report issues via the GitHub repo in `GITHUB_URL.txt`.
