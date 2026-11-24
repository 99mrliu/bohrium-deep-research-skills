# Grounding protocol

The protocol that `extract_sources.py`, `bind_claims.py` and
`verify_grounding.py` enforce, stated for the writer.

## Evidence levels

Every reference in the store carries an evidence level derived from what text
the case actually provides:

| Level | What it supports |
|---|---|
| `abstract` | Findings, numbers, limitations **as stated in that abstract** — nothing beyond it |
| `title-only` | Identification and topic ("X is a template-based predictor"); no findings, no numbers, no limitations |
| `metadata-only` | Existence and bibliographic citation only |

Rules:

- Absence from an abstract is not absence of a capability. Write "its abstract
  reports no comparison against template-based predictors" — not "it cannot be
  compared with template-based predictors".
- Full text, when the case provides it, outranks the abstract; methods text
  supports capability claims, results/captions support comparisons.
- The manuscript fact base is the only source for the present work. Figure
  anchors support what the figure shows: a pipeline figure supports a design
  claim, a results figure supports an accuracy claim with its stated
  comparator, metric and conditions.

## Quote discipline

- A quote is a contiguous substring of the source's available text. Whitespace
  may differ; words may not. Ellipsis stitching of two distant fragments is two
  quotes, not one — the scripts accept a list of quotes per reference.
- Quote the smallest span that carries the claim: the clause with the number,
  the clause with the limitation.
- If the right quote does not exist, the claim does not exist. Rewrite the
  sentence to what the source supports or move it to open items.

## Number tracing

Every numeral in the draft must occur in exactly one of two places:

- prior-work sentence → in that claim's bound quotes;
- own-work / background sentence → in the manuscript fact base.

This catches the two most damaging fabrication modes: inventing a result, and
importing a number from general knowledge (a benchmark size, a dataset count)
that the provided material never states. Anchor numbers (Fig 1, Table 2) are
checked separately by the anchor rule, not by number tracing.

## Stance taxonomy

| stance | meaning | typical trigger |
|---|---|---|
| `supports` | the quote directly states the claim | "reaches 0.55 top-1 precision when ..." |
| `notes_limitation` | the source itself states the limit you cite | "precision drops to 0.41 for targets below 30% identity" |
| `scopes` | you delimit where the claim applies | "its abstract reports no low-identity evaluation" |
| `contrasts` | two sources conflict and you keep both | method A reports X, method B reports not-X under the same condition |
| `identifies` | the reference names/categorizes rather than proves | surveys, taxonomies, dataset introductions |

`confidence` records your residual doubt after reading: `high` when the quote
says exactly what the sentence says; `medium` when the sentence compresses or
generalizes the quote; `low` — rarely acceptable in a finished draft — when
the binding is directional but loose; such claims belong in open items unless
revised.

## Failure examples (synthetic)

1. Draft: "MultiTempl improves precision on low-identity targets [5]."
   Source says precision "stays flat". R3 passes if you quoted the recall
   clause — the failure is semantic, caught by the re-read, not the script.
   Fix: align the sentence with the quote.
2. Draft: "GeoScore underperforms template-based methods [4]."
   The abstract reports no such comparison. No verbatim quote exists → the
   claim is unbindable → rewrite as a scope statement or drop it.
3. Draft: "evaluated on 120 proteins". Fact base says 60. R4/G3 fails: 120
   appears in no quote and no fact line. Delete or correct.
