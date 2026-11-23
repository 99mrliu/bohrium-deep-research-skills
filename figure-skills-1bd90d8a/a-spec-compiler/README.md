# fig-spec-compiler

**Version 1.0.0** — a Skill for the Bohrium Playground challenge
"科研数据图表生成与编辑" (challenge-1bd90d8a).

The agent hand-writes ONE declarative artifact — `figure.spec.json` — after
reading the real paper/data. A deterministic, zero-dependency compiler then
does all mechanical drawing and produces a layered, editable SVG in which
**every glyph carries a `data-src` provenance attribute**, plus
`mapping_ledger.json` with the bidirectional glyph ↔ source-cell
correspondence. Nothing is ever drawn by hand-editing SVG.

This directly targets the classic "looks right but is wrong" failure mode:
any bar, point, node or edge can be traced back to an exact file/column/row
or PDF page/table, and the SVG is byte-identical on re-runs, so reviewers can
reproduce the figure exactly.

## What it does

- **Chart mode** (`source_value_chart` cases): grouped_bar / line / scatter,
  single- or multi-panel; linear + log axes with nice-number ticks
  (1/2/2.5/5×10ⁿ); error bars with declared meaning; legend ↔ series 1:1;
  annotations with locators; CSV/TSV/JSON binding by column (+row filter).
- **Diagram mode** (`figure03`-style cases): nodes (rounded_rect / ellipse /
  cylinder / diamond) with wrapped centered labels, edges
  (arrow=activates / tbar=inhibits / blunt=binds / dashed=putative, straight
  or elbow routes), background compartments, arrow-semantics legend.
- **Source-preserving edits**: re-express the original figure as a spec,
  change only what the task asks, recompile; changes land in `change_record`.
- **Graceful degradation**: missing column → precise error; NaN/empty/dirty
  cell → drawn gap + ledger note; magnitude span > 1e6 → validator suggests
  log scale; overlong labels → wrap/rotate/truncate-with-ellipsis + warning;
  no CJK font → fallback stack + manifest warning; no renderer → honest
  `renderer_unavailable`, exit 0.

## Install

None. The skill is a directory of UTF-8 text files; the evaluator mounts it
at `/skills/weekly-skill`. No build, no package manager, no network.

## Dependencies

| component | requirement | degradation |
|---|---|---|
| all four scripts | Python ≥ 3.8, **stdlib only** (no matplotlib/numpy) | — |
| `pdftotext` / `pdftoppm` | poppler (usually provided) | pdftoppm optional; PNG falls back to soffice direct |
| `soffice` (LibreOffice) | optional, for PDF/PNG export | manifest `renderer_unavailable`, exit 0, SVG stays authoritative |
| `fc-list` | optional, font summary | font check skipped with note; inspect PNG for tofu |

## Usage quickstart

```bash
export SKILL_DIR=/skills/weekly-skill
mkdir -p /app/work /app/output
# 0. honest partial result first
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status partial --note intake
# 1. extract sources (pdftotext -layout / read csv), write extraction notes
# 2. hand-author /app/work/figure.spec.json  (see references/spec_authoring.md)
# 3. validate
python3 $SKILL_DIR/scripts/validate_spec.py /app/work/figure.spec.json \
  --report /app/work/validate_report.json
# 4. compile
python3 $SKILL_DIR/scripts/compile_figure.py /app/work/figure.spec.json \
  --out-svg /app/output/figure.svg --ledger /app/output/mapping_ledger.json
# 5. export previews (graceful if renderers missing)
python3 $SKILL_DIR/scripts/export_preview.py /app/output/figure.svg \
  --out-dir /app/output --manifest /app/output/export_manifest.json
# 6. self-check the PNG + ledger against the six checkpoints; fix the SPEC, recompile
# 7. finalize
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
  --out /app/output/result.json --status complete \
  --source "…" --uncertainty "…" --note "final"
```

## File map

| path | role |
|---|---|
| `SKILL.md` | entry instructions: pipeline, checkpoints, budgets, failure handling |
| `spec_schema.json` | JSON-schema-style description of figure.spec.json |
| `scripts/validate_spec.py` | stdlib validator (errors/warnings/notes, JSON report, --strict) |
| `scripts/compile_figure.py` | deterministic renderer → layered SVG + mapping ledger |
| `scripts/export_preview.py` | SVG → PDF/PNG previews + export manifest (never crashes) |
| `scripts/make_result.py` | create/update result.json per the case output_contract |
| `references/spec_authoring.md` | how to choose encodings, write locators, lay out diagrams |
| `references/output_contract.md` | result.json contract, checkpoints, budget protocol, honesty |
| `examples/minimal_example.md` | complete worked 示例 (synthetic) for both modes |
| `GITHUB_URL.txt` | public source link |

## Scope and limitations

- Chart types are deliberately limited to grouped_bar / line / scatter (plus
  multi-panel composition); box plots and heatmaps are out of scope for v1.
- The layout engine estimates text width (CJK = 2× ASCII); extreme font
  substitutions can cause minor overflow — always inspect the PNG.
- Diagram routing is straight/elbow with rect-approximate node clipping; no
  automatic graph layout — node placement is the spec author's (agent's) job.
- PDF/PNG rendering depends on external renderers when present; without them
  only the SVG + ledger are produced (honestly disclosed).
- The compiler validates provenance presence, not scientific correctness of
  the agent's reading — extraction notes and self-checks remain essential.

## Verification

Smoke-tested end-to-end (python3.12, poppler, LibreOffice present; and with
soffice/fc-list simulated absent): spec validation, chart + diagram +
multi-panel compile, byte-identical recompile, bar-geometry ↔ data
recomputation from the SVG, ledger forward/reverse coverage, graceful
renderer_unavailable path, and negative tests (missing locator, missing
column, dirty cells, 192-char label). See `examples/minimal_example.md`.
