# Render playbook: checks, failure classes, repairs

`scripts/render_qa.py` automates the checks below. Conversion chain: `soffice --headless --convert-to pdf` → `pdftoppm -png -r 110` previews → geometry/font checks on the PDF. Record actual tool versions in the QA report.

## Check catalogue

| Check | Method | Failure class | Repair |
|-|-|-|-|
| Page count | PDF pages vs deck slides vs mandated count | `count_mismatch` | find the lost/duplicated slide; rebuild it from its mapped layout |
| Blank page | per-page text length + image count | `blank_page` | slide lost its content or master; re-add from snapshot, verify layout relationship |
| Text overflow | `pdftotext -bbox` words outside page bounds or overlapping the footer zone | `overflow_suspect` | shorten text or split slide; never shrink font below the template floor; confirm visually |
| Font substitution | `pdffonts` names vs theme fonts | `font_substituted` | install is forbidden — remap text to an installed theme-compatible font, record the remap |
| Image integrity | `pdfimages -list` per page vs placed pictures | `image_missing` | re-insert the crop from the source PNG; check the file was not moved |
| Placeholder residue | deck re-inspection for empty prompt text ("Click to add…") | `empty_placeholder` | fill or delete the placeholder; empty prompts print as stray text |
| Aspect distortion | picture shape ratio vs source PNG ratio | `aspect_distorted` | reset width/height to the source ratio inside the slot |

Automated checks nominate; the agent's visual pass over the contact sheet and dense pages decides. Every confirmed failure gets a changelog row with before/after page numbers.

## Renderer situations

- **`soffice` present**: full pipeline. Use a private profile (`-env:UserInstallation=file:///tmp/lo_profile_<pid>`) to avoid lock failures; a second conversion of the same file in the same outdir silently refuses — clear or version the outdir.
- **No `soffice`, Keynote/PowerPoint automation present**: use it, record the different renderer; font behavior differs, rerun the font check against its PDF.
- **No renderer at all**: deliver the PPTX and the inspection JSON; write `render: unverified` in the QA report and `result.json`; do not rasterize placeholder "previews" and do not claim export success.

## CJK and symbol fonts

- Chinese decks on minimal Linux images substitute aggressively: check `fc-list :lang=zh` in the tool census; if no CJK font exists and the deck is Chinese, that is a delivery-blocking environment fact — record it, choose the least-bad installed font, and flag the visual risk.
- Math/symbol glyphs (Greek, operators) are the first casualties of substitution: spot-check equation slides glyph by glyph in the render.

## Acceptance

QA report passes when: count matches, no blank pages, no confirmed overflow, font findings all recorded with remaps, images complete, no placeholder residue, and the agent's visual pass signed off page by page. Anything not achieved is a named known issue in `result.json` — the report is a record, not a certificate.
