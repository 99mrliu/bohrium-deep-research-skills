# Expected output (合成示例 / synthetic)

Captured from an actual run of `bash run_example.sh` on this machine
(macOS arm64, Python 3.12, matplotlib 3.11, no soffice). Everything is
synthetic: fictional study, fictional template, fictional numbers.

## Console highlights

```
make_fixture: template=.../work/input/target-template.pptx (5640 bytes)
result_make: case_id=synthetic-demo-002 status=partial contract_fields=6 -> .../result.json
template_probe: source=template slide=12192000x6858000 EMU title='Georgia' body='Helvetica'
ASSERT OK: theme probed from fixture template (Georgia/Helvetica/#1F4E79)
textfit: 9 slide(s) (4 continuation, 2 backup); 6 action(s), 1 warning(s)
ASSERT OK: 9 slides total, 4 continuation, 2 backup, 6 actions, min body 14pt
deck_forge: 9 slide(s), 0 media file(s), theme_cloned=True -> .../presentation.pptx
ASSERT OK: pptx valid zip (35 parts); theme1.xml byte-identical to fixture template
preview_render: 9 SVG(s), 9 PNG(s) via matplotlib -> .../preview
ASSERT OK: 9 SVG previews, 9 PNG previews (all >10KB)
export_audit: soffice missing -> verdict RENDERER_MISSING
ASSERT OK: render_audit verdict=RENDERER_MISSING (words_checked=0)
result_make: case_id=synthetic-demo-002 status=success contract_fields=6
ASSERT OK: result.json case_id=synthetic-demo-002, 6 contract fields, synthetic_example=true
run_example: ALL OK
```

## Artifacts and what they prove

| Artifact | Proves |
|---|---|
| `work/input/target-template.pptx` | synthetic organizer template with Georgia/Helvetica/#1F4E79 theme, built by importing the bundle's own `deck_forge` |
| `work/work/theme.json` | template probe: `source="template"`, real fonts/colors extracted |
| `work/work/layout.json` | **overflow-split demonstration**: the 12-bullet slide → 10 bullets + a `"Key findings (dense slide) (cont.)"` slide; the 45-bullet slide → 10+10+10 + 2 `role:"backup"` slides at deck end; `actions[]` logs `shrink_font` / `split_continuation` / `move_to_backup` / `backup_slides_emitted`; body font never below 14pt; `warnings[]` flags the 2-line title |
| `work/app-output/presentation.pptx` | valid pptx zip; **`ppt/theme/theme1.xml` byte-identical to the fixture template's theme** (theme cloning proof — asserted in `run_example.sh`); title runs use `+mj-lt` + `schemeClr accent1`; notes slides, footers, slide numbers present; the missing `figs/lattice_schematic.png` became a labeled placeholder box, not a fabricated chart |
| `work/app-output/preview/slide-*.svg` (+ `.png`) | exact-geometry previews: theme color #1F4E79 titles, wrapped lines, source_line strip, image placeholder, footer + page numbers; PNGs rasterized by matplotlib (all >10KB) |
| `work/app-output/render_audit.json` | `verdict: "RENDERER_MISSING"` — soffice is not installed on this machine; the audit says so honestly and still writes the file (exit 0). On a machine with LibreOffice it converts to PDF and runs the word-level bbox audit |
| `work/app-output/result.json` | `case_id: "synthetic-demo-002"`, all six `output_contract` fields, `status: "success"`, `synthetic_example: true`, declared exceptions (synthetic fixture; renderer missing; master artwork not cloned) |

## Notes

- The early `result_make --status partial` call at step 2 demonstrates the
  "secure a partial result.json EARLY" rule; step 8 overwrites it with the
  final status.
- Determinism: rerunning `textfit.py` on the same `plan.json`+`theme.json`
  yields a byte-identical `layout.json`; `deck_forge.forge()` writes zip
  members in fixed order with a fixed docProps timestamp.
