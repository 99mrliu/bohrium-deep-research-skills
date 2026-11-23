# fig-readback-verifier

A skill bundle for generating scientific data charts (bar / line /
scatter) and biological mechanism diagrams with a **closed-loop guarantee**:
every figure is drawn with matplotlib, then independently **read back**
from its own SVG — numeric values are recovered from glyph geometry by
fitting the pixel→data affine transform from axis tick marks — and
compared against the source data. A figure is not delivered until the
read-back matches the source within tolerance, or the failure is
explicitly disclosed. Repair directives are machine-readable; the agent
fixes the plan and re-draws (max 3 rounds, each logged).

Innovation claim: a bidirectional figure↔data check that mechanically
catches "画得漂亮但数字错" failures (wrong column mapping, swapped
series/legend, unit/magnitude slips, missing labels, CJK tofu,
text-as-outlines), which pure visual QA misses.

## Install

Copy this directory to the skill mount point (evaluator:
`/skills/weekly-skill`). No build step. Entry point: `SKILL.md`.

## Dependencies

- python3 ≥ 3.8
- **matplotlib** — required for `scripts/draw_figure.py` only (Agg,
  headless; numpy optional).
- `scripts/readback_verify.py`, `scripts/export_check.py`,
  `scripts/make_result.py` are **pure stdlib** — they cannot share a bug
  with the drawer.
- Optional: `pdftoppm`/`pdftotext` (PDF intake), `fc-list` (font
  confirmation; absent → warn, not crash), `soffice` (unused by scripts).

## Usage

```bash
export SKILL_DIR=/path/to/this/dir
# 0. honest partial result FIRST
python3 $SKILL_DIR/scripts/make_result.py --case /input/case.json \
    --out /app/output/result.json --status partial --note intake
# 3. draw
python3 $SKILL_DIR/scripts/draw_figure.py /app/work/figure_plan.json \
    --out /app/output/figure --formats svg,png,pdf
# 4. verify (read-back)
python3 $SKILL_DIR/scripts/readback_verify.py --svg /app/output/figure.svg \
    --plan /app/work/figure_plan.json --report /app/output/verify_report.json
# 6. export compliance
python3 $SKILL_DIR/scripts/export_check.py /app/output/figure.svg \
    /app/output/figure.png /app/output/figure.pdf \
    --report /app/output/export_report.json
```

All verifiers exit 0 always; read the JSON reports. The drawer exits 2
with a stderr message on plan/data errors.

## File map

| path | role |
|---|---|
| `SKILL.md` | entry instructions: pipeline, loop invariant, budget/failure protocol |
| `scripts/draw_figure.py` | plan-driven matplotlib drawer (charts + diagrams), semantic gids, CJK handling, draw log |
| `scripts/readback_verify.py` | stdlib-only SVG read-back verifier (geometry → values → diff) |
| `scripts/export_check.py` | PNG dpi (pHYs), PDF MediaBox/pages, SVG editability checks |
| `scripts/make_result.py` | create/update result.json honoring output_contract, change_record |
| `references/plan_authoring.md` | figure_plan.json field reference + binding rules |
| `references/verification.md` | methodology, check catalog, repair playbook, known limits |
| `examples/minimal_example.md` | worked 示例 incl. a caught corruption |
| `GITHUB_URL.txt` | source repository pointer |

## Limitations

- Linear axes only for numeric read-back (log scales: fit in log space
  manually / declare unverifiable). No stacked bars, twin axes, or broken
  axes read-back.
- Read-back relies on matplotlib's SVG gid structure; SVGs from other
  tools degrade to `unverifiable` (disclosed, never crash).
- Font check cannot rasterize: a final human look at the PNG is part of
  the protocol.
- Occlusion check is a bounding-box heuristic (warn-level).

## Version

1.0.0
