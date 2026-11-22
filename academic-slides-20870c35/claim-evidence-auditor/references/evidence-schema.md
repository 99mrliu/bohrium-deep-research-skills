# Evidence schema: source index, claim cards, content map, coverage ledger

All artifacts are JSON, UTF-8, written under `/app/work` during the run and the deliverable ones copied to `/app/output`.

## 1. Source index (`/app/work/source_index.json`, produced by `scripts/pdf_index.py`)

```json
{
  "file": "paper.pdf",
  "page_count": 12,
  "pages": [{"pdf_page": 1, "text": "..."}],
  "exhibits": [
    {"kind": "figure", "id": "Figure 2", "pdf_page": 6, "printed_page": 4,
     "caption": "Figure 2: Detection error vs label budget ..."}
  ],
  "sections": [{"title": "3.2 Alignment module", "pdf_page": 5}],
  "citations": [{"raw": "[12]", "pdf_page": 2}]
}
```

- `exhibits` covers every figure/table caption found; if the layout parser misses one (two-column papers, caption detached), add it manually after visual inspection of the rendered page — the registry must be complete before the coverage gate can pass.
- `printed_page` is parsed from the page footer when detectable, else null; locators may cite either, always saying which.

## 2. Claim card (`/app/work/claims.json`)

```json
{
  "claims": [
    {"id": "C07",
     "statement": "Demo-Net reduces small-object error by 12% relative on the benchmark test split",
     "kind": "measured",
     "strength": "established",
     "locator": {"file": "paper.pdf", "pdf_page": 6, "printed_page": 4,
                 "section": "4.1", "exhibit": "Figure 2"},
     "anchor": "error drops from 25.0 to 22.0 AP_small (12% relative) on test",
     "attribution": "this_work",
     "conditions": "benchmark X, test split, 10% label budget",
     "notes": "baseline is the authors' re-implementation, Table 1"}
  ]
}
```

Field rules:

- `kind`: `measured` (experiment/observation), `computed` (derivation/simulation), `cited_prior` (other groups' results), `inferred` (authors' interpretation), `framing` (context/motivation).
- `strength`: see `strength-rubric.md`; grade the evidence, not the sentence.
- `anchor`: verbatim quote (short) or exact transcription with units; this is what the number gate matches against.
- `attribution`: `this_work | cited_work | presenter_synthesis`. Presenter synthesis is allowed but must be labeled as such wherever it appears.
- A claim you cannot locate exactly has no card; a claim with no card has no slide.

## 3. Content map (`/app/output/content_map.json`, deliverable)

```json
{
  "case_id": "...",
  "slides": [
    {"index": 6, "headline": "...", "claim_ids": ["C07"],
     "exhibits_used": [{"exhibit": "Figure 2", "source_pdf_page": 6, "crop": "left panel"}],
     "strength_on_slide": "established"}
  ]
}
```

The map is generated from `page_plan.json` and corrected to match the deck as built — it describes the delivered deck, not the plan.

## 4. Coverage ledger (`/app/output/coverage.json`, deliverable)

```json
{
  "exhibits": [{"exhibit": "Figure 1", "disposition": "slide 4"},
               {"exhibit": "Table 2", "disposition": "backup"},
               {"exhibit": "Table 5", "disposition": "omitted: per-epoch curve redundant with Table 3 for this audience"}],
  "sections": [{"section": "Appendix A", "disposition": "omitted: proofs beyond scope, pointer in notes of slide 5"}]
}
```

Every registry item appears exactly once; `omitted` always carries a reason. This is what makes "full source" checkable instead of asserted.

## 5. Audit report (`/app/output/audit_report.json`, deliverable)

Produced by `scripts/audit_deck.py`; see `audit-playbook.md` for the gates and the acceptance criteria. Any finding the run could not resolve stays in the report and is echoed in `result.json` uncertainties — an open finding is a fact, hiding it is a failure.
