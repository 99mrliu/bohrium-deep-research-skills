# Synthetic example — anchor geometry end to end

Fully synthetic text fixtures (no PDFs, no binaries). One fake document
`sample.pdf` with three pages of word boxes and six raw annotation marks.

## Fixture layout

| page | file | layout | words origin |
|------|------|--------|--------------|
| 1 | `pages/sample.pdf/page-001.words.tsv` | single column | `text` |
| 2 | `pages/sample.pdf/page-002.words.tsv` | **two columns** (gutter x≈277), stored in interleaved row-major order to simulate a naive extractor dump | `text` |
| 3 | `pages/sample.pdf/page-003.words.tsv` | single column | `ocr` (with confidence) |

## Annotations (`annotations.jsonl`)

| id | page | type | geometry | point of the case |
|----|------|------|----------|-------------------|
| ann-001 | 1 | Highlight | 1 quad over "lazy dog" | baseline single-column resolve |
| ann-002 | 2 | Highlight | 2 quads spanning the column break (col-1 tail + col-2 head) | **two-column repair — the core claim** |
| ann-003 | 2 | Underline | 1 quad in column 2 | per-column ordering, type preserved |
| ann-004 | 1 | FreeText | `rect` only, in the right margin | `nearest_block` anchoring with distance |
| ann-005 | 3 | Highlight | quad drifted 15 units right; `contents` has 2 char errors vs the OCR words ("coestal", "station") | classified `drifted`, then `corrected` |
| ann-006 | 3 | Highlight | quad fine, but `contents` is an alien sentence | honestly `unrecoverable` |

## Run it

```bash
B=/path/to/bundle-b-anchor-geometry
W=$(mktemp -d)

python3 "$B/scripts/anchor_resolve.py" \
  --annotations "$B/examples/annotations.jsonl" \
  --pages-dir "$B/examples/pages" \
  --out "$W/resolved.jsonl"            # exit 0

python3 "$B/scripts/anchor_verify.py" \
  --resolved "$W/resolved.jsonl" \
  --pages-dir "$B/examples/pages" \
  --out "$W/verify_report.json"        # exit 0 here (1 anchor 'drifted')

python3 "$B/scripts/drift_correct.py" \
  --resolved "$W/resolved.jsonl" \
  --pages-dir "$B/examples/pages" \
  --out "$W/corrected.jsonl"           # exit 3: one anchor stays unrecoverable

python3 "$B/scripts/anchor_verify.py" \
  --resolved "$W/corrected.jsonl" \
  --pages-dir "$B/examples/pages" \
  --out "$W/verify_report_corrected.json"   # exit 0, all anchors exact
```

See `EXPECTED.md` for the real observed outputs, the hand-check of the
two-column case, and the negative tests (seeded bad anchor → verify exit 3).
