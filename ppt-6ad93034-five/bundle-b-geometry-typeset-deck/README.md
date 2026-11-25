# geometry-typeset-deck (bundle b-geometry-typeset-deck)

Deterministic, geometry-first academic PPT builder (学术 PPT 生成与编辑).
Paper PDF + slide work order (+ organizer template) → editable
`presentation.pptx` with **provably no overflow**.

Center of gravity: **downstream rendering engineering**.

1. **Measure-before-write layout** (`scripts/textfit.py`): every string is
   measured with a built-in, documented font-metric model; overflow is
   resolved *before* any pptx byte is written — font ladder 18→16→**14pt
   floor**, then `"…(cont.)"` continuation slides, then `backup` slides at
   deck end. Every resolution is logged in `layout.json.actions[]`.
2. **Byte-level theme cloning** (`scripts/deck_forge.py`): the template's
   `ppt/theme/theme1.xml` is copied verbatim; runs reference `+mj-lt` /
   `+mn-lt` fonts and `schemeClr` colors, so PowerPoint/LibreOffice render
   the organizer's real fonts and colors. (Master artwork is NOT cloned —
   declared exception.)
3. **Post-export bbox audit** (`scripts/export_audit.py`): soffice → PDF,
   `pdftotext -bbox` word-level audit against the page rect and footer zone
   → `render_audit.json` with `PASS|FAIL|RENDERER_MISSING` (honest when no
   renderer exists).

Supporting pieces: `template_probe.py` (template → `theme.json`),
`preview_render.py` (per-slide SVG always, PNG via matplotlib when
importable), `result_make.py` (early-partial + final, contract-complete
`result.json`, never fabricates).

## Quick start

```bash
cd examples && bash run_example.sh   # fully synthetic end-to-end demo
```

At evaluation the skill lives at `/skills/weekly-skill`; see `SKILL.md` for
the exact runtime contract and 6-step workflow. Engine details:
`references/layout_engine.md`.

Pure stdlib core; matplotlib optional; `soffice`/`pdftotext`/`pdftoppm`
auto-detected with graceful degradation; no network.
