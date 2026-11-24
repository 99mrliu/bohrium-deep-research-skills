# Synthetic example — 合成示例

**合成示例 / synthetic example**: all content here is invented for
demonstration; no real paper, data, or claims are involved.

A minimal end-to-end run of the termbase-forge workflow on a tiny invented
materials-science note (perovskite photovoltaics, EN→ZH).

## Files

| file | role |
|---|---|
| `source.txt` | invented English source, ~17 lines: two headed sections + a figure-caption line; 7 terms repeated across sections, incl. the acronym PCE and the discipline-sensitive word *cell* (电池, not 细胞) |
| `terms_draft.json` | ACTUAL output of `extract_terms.py` on `source.txt` |
| `glossary.json` | hand-curated locked glossary, 7 entries; two entries carry `forbidden_variants` (`钙钛矿电池`, `功率转换效率`, `细胞`) and two carry `first_mention` forms |
| `translation_zh.md` | hand-written Chinese translation, fully consistent with the lock |
| `lint_output.txt` | ACTUAL output of `lint_glossary.py` (PASS, exit 0) |
| `glossary_check.json` | ACTUAL output of `check_consistency.py` (all 7 terms `locked_ok`, exit 0) |

## Reproduce

```bash
cd examples/synthetic
python3 ../../scripts/extract_terms.py source.txt -o terms_draft.json
python3 ../../scripts/lint_glossary.py glossary.json
python3 ../../scripts/check_consistency.py glossary.json source.txt translation_zh.md -o glossary_check.json
```

Expected: extraction surfaces PCE (x2), perovskite solar cell (x4),
charge carrier mobility (x4), power conversion efficiency (x3),
grain boundary (x3), open-circuit voltage (x3), Spin Coating (x5);
lint exits 0; consistency check exits 0 with every term `locked_ok`
(src/tgt counts: 4/4, 3/3, 4/4, 3/3, 5/5, 3/3, 8/8).

Negative behavior (verified during bundle testing, not stored here): a
glossary with conflicting duplicate targets / empty targets /
forbidden==target fails lint with exit 1; a translation using
`功率转换效率` or `细胞` fails the consistency check with
`forbidden_variant` errors pointing at the offending line.
