# Claim record schema

One record per factual sentence (or per sentence part, when a sentence cites
several works for different clauses). The array of records maps directly onto
a `facts_and_sources`-style contract field.

```json
{
  "id": "c5",
  "section": "related_work",
  "text": "MultiTempl pools pockets from up to 8 template structures and gains 0.15 recall over single-template transfer, yet precision on low-identity targets stays flat because low-quality templates vote with equal weight.",
  "type": "prior_work",
  "refs": ["synth03"],
  "quotes": {"synth03": ["pools predicted pockets from up to 8 template structures and ranks them by pocket frequency", "Pooling raises recall by 0.15 over single-template transfer, but precision on low-identity targets stays flat because low-quality templates vote with equal weight"]},
  "source_span": "abstract sentences 1-2",
  "stance": "notes_limitation",
  "confidence": "high"
}
```

## Fields

- `id` — stable identifier; never renumber after reviews reference it.
- `section` — `background` | `related_work` | `gap` | `contributions` (use the
  case's own section names when it declares them).
- `text` — the sentence **as it appears in the draft**, citation markers
  optional. The grounding audit matches this text back to the draft; keep it
  in sync when you edit prose (orphan records fail G2).
- `type` — `prior_work` (about a cited work), `background` (field-level
  statement, usually survey-backed), `gap` (derived from cited limitations),
  `own_work` (any statement about the present manuscript; no refs), and
  `contribution` (an own-work claim that asserts a method or result — it must
  name one of the case's available anchors, e.g. Fig 1).
- `refs` — bibliography keys from the evidence store, never numbers invented
  from memory.
- `quotes` — map of ref key → verbatim quote, or list of verbatim quotes when
  one reference grounds several clauses. Single-ref claims may use a plain
  `quote` string.
- `source_span` — human pointer for reviewers: "abstract sentence 2",
  "Methods, paragraph 3". Free text; make it findable.
- `stance` / `confidence` — see `grounding_protocol.md`.

## What the verifier rejects (hard failures)

- R1: a ref key absent from the store.
- R2: findings attributed to a `title-only` / `metadata-only` reference.
- R3: a quote that is not a verbatim substring of that reference's text.
- R4: a number in `text` that appears in no bound quote (prior work) or in no
  fact-base line (own work).
- R5: an own-work claim carrying refs, or a `contribution` claim naming none
  of the case's available anchors.
- R6: stance/confidence outside the allowed vocabularies.

Warnings (fix before delivery, but not blocking): a quote bound to a ref not
listed in `refs`; an own-work claim with refs attached.
