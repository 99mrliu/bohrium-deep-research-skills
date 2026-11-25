# Publication, source-preserving editing, export, and QC

## Publication conventions

- Keep text as `<text>`/`<tspan>`; do not outline labels in the editable master. Native IDs and groups (`layer-background`, `layer-headings`, `layer-diagram`, `layer-charts`, `layer-legend`, `layer-footer`) make targeted edits possible.
- Root `viewBox` and millimetre `width`/`height` are explicit. Inspect at the intended physical size. The example is 320 × 200 mm with a 1600 × 1000 viewBox.
- Palette uses dark text and white/pale backgrounds with blue/orange/purple/green/red relation channels. Every relation also has a line/marker code. Do not rely on red/green distinction alone.
- Apparatus glyphs use native strokes and simple geometry; labels remain independent editable nodes. Panel labels and data/flow legends are generated from actual content.
- Live fonts are **not embedded**. The CSS font stack is `Noto Sans`, `Source Han Sans SC`, `Arial`, sans-serif. Export tools may substitute available fonts. Visually inspect Latin/CJK glyphs and disclose substitution risks.

## Byte-span SVG edits

`patch_svg.py` reads UTF-8 bytes and uses Expat `CurrentByteIndex`. It locates exactly one `id`, then replaces only the addressed simple-text content, quoted attribute value, attribute-removal span, or attribute insertion point. It never uses ElementTree to write the document, never normalizes quotes/whitespace, and preserves every other byte. The report includes input/output SHA-256 and exact original byte spans.

A whole-document hash must change after an edit; that does not contradict localized byte preservation. To test preservation independently, compute a common prefix/suffix around each reported edit or apply the inverse patch and compare hashes. Always rerun SVG validation and preview inspection.

## Optional export

Core build uses stdlib only. Automated PNG/PDF export tries CairoSVG, `rsvg-convert`, Inkscape, and Chrome Headless in that order until one succeeds; no installation is attempted. Attempt failures and the selected tool are recorded. CairoSVG uses 1.5× viewBox dimensions; Chrome uses a 2400 × 1500 screenshot window with aspect-preserving containment and an SVG-sized physical PDF page. Other exporters use their native defaults. Export never replaces the live-text SVG editing master.

QC checks are deliberately concrete:

- SVG XML parse, root dimensions/viewBox, unique IDs, valid `url(#…)` references, native text/group counts, byte size and SHA-256;
- PNG magic/IHDR, nonzero dimensions, all chunk lengths and CRC32 values, IDAT and IEND;
- PDF magic, page object, MediaBox and EOF, byte size and SHA-256.

These checks do not replace visual/scientific review and do not prove every PDF glyph remains searchable or every font is embedded.

## Negative tests (expected nonzero)

Malformed CSV mapping:

```bash
printf 'time,value\n1,2\n' > /tmp/vps-bad.csv
python3 - <<'PY'
import json
p=json.load(open('examples/synthetic/input/source_spec.json'))
p['charts'][0]['data_csv']='/tmp/vps-bad.csv'
p['charts'][0]['x_column']='missing_time'
json.dump(p,open('/tmp/vps-bad.json','w'))
PY
python3 scripts/studio.py build --spec /tmp/vps-bad.json --output-dir /tmp/vps-bad-output
# Expected: x_column not present; exit 2
```

Label overflow:

```bash
python3 - <<'PY'
import json
p=json.load(open('examples/synthetic/input/source_spec.json'))
p['nodes'][0]['label']='An intentionally unshortenable overflowing apparatus label ' * 8
p['nodes'][0]['max_label_lines']=1
p['charts'][0]['data_csv']=str(__import__('pathlib').Path('examples/synthetic/input/chart.csv').resolve())
json.dump(p,open('/tmp/vps-overflow.json','w'))
PY
python3 scripts/studio.py build --spec /tmp/vps-overflow.json --output-dir /tmp/vps-overflow-output
# Expected: Label overflow; exit 2
```

Automated regression check (includes deterministic SVG, automatic ranks, byte-prefix/suffix preservation, malformed mapping, missing CSV, overflow, and duplicate IDs):

```bash
python3 scripts/self_test.py --example-dir examples/synthetic --report /tmp/vps-self-test.json
```

For a separate determinism check, run the same builder into two different directories and compare `figure.svg` hashes. Export hashes can vary by renderer/version; report the actual exporter and hashes rather than claiming cross-version binary identity.
