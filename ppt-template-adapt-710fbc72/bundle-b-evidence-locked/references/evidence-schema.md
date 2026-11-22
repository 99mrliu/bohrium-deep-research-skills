# Evidence schemas used by the evidence-locked pipeline

## claims.json (input to the gate)

```json
[
  {"id": "c1",
   "claim": "one-sentence slide-ready claim, in the deck's language",
   "kind": "figure | table | section | equation | text",
   "ref": "Fig. 3",
   "pdf_page": 7,
   "anchor": "short verbatim quote copied from the extracted page text"}
]
```

Rules:

- `anchor` must be verbatim from `source_index.json` page text — including
  its numbers. Quotes spanning a line break may mismatch exactly; that is
  what `--fuzzy` (token overlap ≥ 0.8) is for.
- `pdf_page` is the PDF page (1-based), not the printed page number.
- One claim = one checkable statement. Do not bundle three results into one
  claim with one anchor.

## claims.verified.json (gate output)

Adds per claim: `status` in `verified | page_mismatch | unverified` and a
`verification` explanation string. Only `verified` claims may be copied into
`plan.json` evidence lists.

## evidence_map.json (builder output, one entry per slide)

```json
[
  {"slide": 2, "title": "Results on WMT",
   "claim_summary": "…",
   "sources": [{"kind": "table", "ref": "Table 2", "pdf_page": 8,
                "anchor": "…", "status": "verified"}]}
]
```

This file is the page-level evidence map the task requires; keep it in
`/app/output` and reference it from `result.json`.

## Uncertainty bookkeeping

Anything that ends up on a slide *without* a verified anchor (allowed only
in `--no-strict` recovery situations) must appear in `result.json`'s
`uncertainty` with the slide number and reason — `contract_check.py`
cross-checks this.
