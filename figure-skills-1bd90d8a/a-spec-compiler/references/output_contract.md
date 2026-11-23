# Output contract — intake, result.json, checkpoints, budgets

## result.json fields

`/app/output/result.json` is created at intake and updated at finalize by
`scripts/make_result.py`. Guaranteed shape:

| field | content |
|---|---|
| `case_id` | copied **verbatim** from `/input/case.json` (`case_id` or `id`) |
| `status` | `partial` \| `complete` \| `failed` (semantics below) |
| `sources` | list of locators: every file + page/table/column/row actually used |
| `uncertainty` | list of honest statements: illegible regions, inferred relations, renderer gaps, tofu risk, accepted validator warnings |
| `change_record` | appended on every run: `{ts_utc, status, note}` — include what changed and why (also for edit-cases: what was preserved vs. changed) |
| *each `output_contract` field* | the case's own contract fields; `output_contract` may be a dict, a list of strings, or a list of dicts (`field`/`name`/`key`) — make_result normalizes all three and fills `"pending"` placeholders you must replace with real content |

Typical contract content: editable source path (`/app/output/figure.svg`),
exports (`figure.pdf`, `figure.png` + dpi/size from `export_manifest.json`),
figure summary, source/provenance description (point at
`mapping_ledger.json`), export check results.

## Status semantics

- `complete`: every required deliverable exists AND passed self-check; every
  contract field filled with real content.
- `partial`: something required is missing or unverified — the note and
  `uncertainty` MUST name exactly what and why. A partial is a success state
  when honest; a fake "complete" is a failure.
- `failed`: no usable figure could be produced; still deliver result.json,
  extraction notes, and the reason.

## Partial-result protocol (budget-driven)

1. **First minutes:** run make_result with `--status partial` before any real
   work (SKILL.md step 0). This is non-negotiable.
2. Improve incrementally: extraction notes → spec → compile → export. Each
   stage leaves artifacts on disk, so any interruption still yields a
   reviewable state.
3. **t > 600 s:** stop refining; run the finalize command with an honest
   status. Do not start new speculative work in the last minutes.

## The six scoring checkpoints (self-check table)

| # | checkpoint | how you verify it | where it is recorded |
|---|---|---|---|
| 1 | 科学实体 | diff entity strings in spec vs. extraction notes; verbatim spelling | extraction_notes.md, node/series labels |
| 2 | 空间关系 | PNG inspection: panels, compartments, arrow directions, topology match the task | figure.svg layers, PNG |
| 3 | 数据编码 | recompute glyph geometry from ledger `transform` strings; spot-check 2–3 values | mapping_ledger.json |
| 4 | 图例标注 | axis labels + units + magnitude; legend ↔ series 1:1; error_meaning declared | spec, legend, validator warnings |
| 5 | 可编辑源文件 | layered `<g id="layer-…">`, real `<text>` (no outlines), mm size + viewBox | figure.svg |
| 6 | 导出格式 | PDF+PNG exist, 300 dpi PNG (via pdftoppm), no tofu, sizes match canvas | export_manifest.json |

## Exception checklist (scored — walk it every case)

missing columns · NaN/empty values · scale/magnitude anomalies · overlong
labels · missing CJK fonts (tofu) · export failure · label occlusion.
For each: either demonstrate correct handling (ledger note / manifest
deviation / validator warning consciously accepted) or state why N/A.

## Budget protocol

- 64 model requests · 900 s wall · 16384 tokens/response.
- The compiler is deterministic and stdlib-only: re-running is cheap; never
  hand-patch SVG (that wastes budget and breaks provenance).
- Prefer one well-planned spec over many exploratory compiles: extraction
  notes first, spec second.

## Export requirements

- `figure.svg`: width/height in mm + viewBox; inline font-family fallback
  stack (Helvetica, Arial, 'Noto Sans CJK SC', 'Source Han Sans SC',
  'WenQuanYi Micro Hei', sans-serif); no timestamps (byte-identical re-runs).
- `figure.pdf` via soffice; `figure.png` at 300 dpi via pdftoppm (fallback
  soffice direct PNG, flagged as a deviation).
- `export_manifest.json`: tool_versions, font_summary (fc-list if present),
  outputs[{path,format,width_mm,dpi}], status ok|partial|renderer_unavailable,
  deviations[]. `renderer_unavailable` is an acceptable honest state — SVG +
  ledger stay authoritative.

## Honesty rules (hard constraints)

- Never fabricate scientific data, tool outputs, benchmark scores, or
  software state.
- A partial result must name its limits in `uncertainty` + `change_record`.
- Illustrative material must be labeled 示例/example.
- Read the real input files; never infer content from labels or filenames.
- Runtime artifacts (SVG/PNG/PDF/ledger) are retained independently of the
  final JSON — they must tell the same story as result.json.
