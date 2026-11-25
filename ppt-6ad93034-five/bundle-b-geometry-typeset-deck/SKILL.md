---
name: geometry-typeset-deck
description: Deterministic geometry-first academic deck builder (学术 PPT 生成与编辑). It measures every string with built-in font metrics and resolves overflow BEFORE writing the pptx (font ladder to a 14pt floor, then continuation slides, then backup slides — never unreadable shrink, never overlap), byte-clones the organizer template's theme so real fonts/colors survive in PowerPoint/LibreOffice, and proves the result with a post-export bounding-box audit. Trigger when a research paper PDF + slide work order + (optionally) an organizer template must become an editable academic deck under a strict request/time budget. Boundary: it does not fabricate charts, does not clone master artwork (bitmaps/backgrounds), and needs no network.
---

# geometry-typeset-deck

## Philosophy

**Build-time overflow elimination beats check-after-repair.** A deck that is
laid out with measured text geometry never needs emergency shrinking: every
bullet is wrapped against a conservative width model *before* any XML is
written, and every overflow is resolved by an explicit, logged policy ladder
(shrink to floor → split continuation slide → move to backup). Theme fidelity
is achieved by copying the template's `theme1.xml` **bytes** and referencing
theme fonts/colors symbolically (`+mj-lt`, `schemeClr`), not by guessing
font names. Finally, a post-export bbox audit on the rendered PDF *proves*
nothing overflows — and honestly reports `RENDERER_MISSING` when no renderer
exists instead of claiming success.

## Runtime contract

- The skill is installed at `/skills/weekly-skill`. Original inputs live under
  `/input`: `case.json`, `task.md`, the paper PDF, usually
  `target-template.pptx`, optionally `starting-deck.pptx` and
  `artifacts/slide-workorder.json`. **Read the REAL files.**
- Work under `/app/work`; deliverables under `/app/output`:
  `presentation.pptx` (editable), `presentation.pdf` + preview PNGs when
  `soffice` exists, `layout.json` + `render_audit.json`, `result.json`.
- `result.json` MUST contain the original `case_id` (case.json key `case_id`
  or `id`) and EVERY root field of the case's `output_contract` (read from
  case.json; if absent use defaults: `status`, `editable_source`,
  `export_artifact`, `content_map`, `compliance_checks`, `exceptions`).
  `status` ∈ `success|partial|unable_to_determine|refused`; `partial` states
  limits precisely. **Secure a partial result.json EARLY. Never fabricate.**
- Scripts are invoked as `python3 /skills/weekly-skill/scripts/<name>.py`;
  flags and/or env vars `CASE_INPUT_DIR`, `CASE_WORK_DIR`, `CASE_OUTPUT_DIR`
  (defaults `/input`, `/app/work`, `/app/output`). Pure-stdlib core;
  matplotlib is OPTIONAL (used only for PNG previews when importable).
  `pdftotext`/`pdftoppm`/`soffice` are detected via `shutil.which` and
  degrade gracefully. **No network.**

## Workflow (6 steps)

```bash
S=/skills/weekly-skill/scripts
# 0) Secure an early partial result BEFORE any heavy work:
python3 $S/result_make.py --status partial \
    --exception "pipeline started; final artifacts pending"

# 1) Probe the organizer template (geometry, fonts, colors, footer):
python3 $S/template_probe.py --template /input/target-template.pptx \
    --work /app/work            # writes /app/work/theme.json (defaults if missing)

# 2) AGENT STEP: read task.md + the paper PDF (pdftotext if present) and the
#    optional artifacts/slide-workorder.json, then author /app/work/plan.json:
#    {"meta":{"title","time_minutes"?},
#     "slides":[{"id","role","title","bullets":[...],"notes","image"?,"source_line"?}]}
#    roles: title | content | backup. Cite only what the paper actually says.

# 3) Resolve all layout deterministically (measure-before-write):
python3 $S/textfit.py --plan /app/work/plan.json --theme /app/work/theme.json \
    --out /app/work/layout.json   # concrete EMU boxes + actions[] + warnings[]

# 4) Forge the editable pptx (theme bytes cloned from the template):
python3 $S/deck_forge.py --layout /app/work/layout.json \
    --theme /app/work/theme.json --template /input/target-template.pptx \
    --images /app/work/figs --out /app/output/presentation.pptx
cp /app/work/layout.json /app/output/layout.json

# 5) Preview + post-export audit:
python3 $S/preview_render.py --layout /app/work/layout.json \
    --theme /app/work/theme.json --out /app/output/preview/
python3 $S/export_audit.py --pptx /app/output/presentation.pptx \
    --layout /app/work/layout.json --out /app/output   # exit 1 on FAIL

# 6) Final result.json (same writer, final status + declared exceptions):
python3 $S/result_make.py --status success \
    --exception "<each limitation precisely, or none>"
```

If step 5 returns FAIL, read `render_audit.json` `violations[]`, edit
`plan.json` (shorten/split the offending content), and rerun steps 3–5. Never
"fix" overflow by lowering the 14pt floor — it does not exist below 14pt.

## Exception table (declare each fired case in result.json `exceptions`)

| Situation | Behavior | Exception entry |
|---|---|---|
| `target-template.pptx` missing/unreadable | Office defaults (12192000×6858000 EMU, Calibri, Office accents); `theme.json.source="defaults"` + `assumptions[]` | "template missing; default geometry/theme used" |
| `soffice` missing | `render_audit.json.verdict=RENDERER_MISSING` (exit 0); SVG/PNG previews from `preview_render.py` are the inspection artifact | "no renderer; bbox audit not executed" |
| CJK-heavy deck | width model treats CJK/fullwidth as 1.00em (conservative); verify previews visually | "CJK metrics are heuristic; previews verified" |
| image file missing | placeholder box labeled with the intended source path — **never a fabricated chart** | "image <path> missing; placeholder used" |
| master artwork | only `theme1.xml` bytes are cloned; master bitmaps/backgrounds/decorative shapes are NOT carried over | "master artwork not cloned" |
| title wraps >1 line at 28pt | WARN in `layout.json.warnings[]`; box grows, body shifts down, nothing overlaps | "slide <id> title wraps; kept (see warnings)" |

## Scripts

| Script | Role |
|---|---|
| `scripts/template_probe.py` | zip-parse template → `theme.json` (sldSz, major/minor latin + ea fonts, accent1–6/dk1/lt1, footer presence) |
| `scripts/textfit.py` | deterministic measurement (`string_width_pt`, `wrap_text`) + overflow policy ladder → `layout.json`; importable and CLI |
| `scripts/deck_forge.py` | pure-stdlib pptx writer; verbatim theme-byte cloning, `+mj-lt`/`schemeClr` refs, notes slides, footers, slide numbers, PNG embedding (IHDR aspect) |
| `scripts/preview_render.py` | per-slide SVG (stdlib, exact geometry) + PNG when matplotlib is importable |
| `scripts/export_audit.py` | soffice→PDF (isolated profile), pdftoppm PNGs, `pdftotext -bbox` word-level audit → `render_audit.json`, exit 1 on FAIL |
| `scripts/result_make.py` | early-partial + final `result.json`, contract-complete, never fabricates |

## Synthetic example

`examples/run_example.sh` builds a fully synthetic fixture (fictional study,
fictional template with Georgia/Helvetica/#1F4E79 theme) and runs the whole
pipeline, asserting: theme probed from template, a 12-bullet slide splits into
slide + `(cont.)`, a 45-bullet slide overflows into backup slides, body font
never <14pt, output `theme1.xml` byte-identical to the fixture template, and a
contract-complete `result.json` marked `"synthetic_example": true`. See
`examples/expected_output.md`. 合成示例 — no real paper or template involved.
