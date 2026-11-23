# source_ledger.json format (Bundle C)

A JSON list, one entry per figure element:

```json
[
 {"element": "node-drug",
  "kind": "entity",
  "shows": "Staurosporine 5 uM, 6 h treatment node",
  "evidence": [{"key": "paper.pdf#page-2",
                "quote": "We treated HeLa cells with 5 uM staurosporine for 6 h"}],
  "numbers_shown": ["5", "6"]},
 {"element": "edge-drug-cells",
  "kind": "relation",
  "shows": "treatment arrow from staurosporine to HeLa cells",
  "evidence": [{"key": "paper.pdf#page-2",
                "quote": "We treated HeLa cells with 5 uM staurosporine"}]},
 {"element": "bar-viability",
  "kind": "value",
  "shows": "viability 42% after treatment (CCK-8)",
  "evidence": [{"key": "viability.csv#para-1",
                "quote": "staurosporine_5uM,42"}],
  "numbers_shown": ["42"]}
]
```

## Field rules

- `element` (required): the SVG element id, or the figure region name if the
  figure is not yours. With `--svg`, ids not present in the SVG raise a
  warning (fix the id or explain the mapping in `exceptions`).
- `kind` (required): `entity | relation | value | label | annotation`.
- `shows` (required): one sentence stating what the element claims. Used for
  coverage matching; write it as the claim, not a description of the shape.
- `evidence` (required, ≥ 1): `key` must exist in `evidence_pool.jsonl`
  (`file#page-N` for PDFs, `file#para-N` for text/data); `quote` must be a
  **verbatim substring** of that block after whitespace normalisation.
- `numbers_shown` (optional but expected for values): each must occur in the
  concatenated evidence quotes of the same entry. A number that lives only
  in a different block is an orphan — add the block as a second evidence
  item or drop the number.

## Verification semantics (ledger_verify.py)

| Finding | Severity | Meaning |
|---|---|---|
| `no-evidence` | blocker | element has no evidence at all |
| `bad-locator` | blocker | pool key does not exist |
| `quote-mismatch` | blocker | quote not verbatim in the cited block |
| `orphan-number` | blocker | displayed number absent from its own evidence |
| `unknown-kind` | warning | kind outside the taxonomy |
| `ledger-not-in-svg` | warning | element id not found among SVG ids |

Any blocker ⇒ exit 1 ⇒ figure is not deliverable as `complete`. Disposition
only in writing (`result.json.exceptions`), never by deleting the finding.
