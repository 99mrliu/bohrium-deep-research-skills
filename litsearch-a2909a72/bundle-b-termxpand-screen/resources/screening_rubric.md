# Screening rubric — two-stage, reason-coded, auditable

Every retrieved record receives exactly one terminal decision. Exclusion is a logged
decision with a reason code and an evidence snippet, never a silent delete.

## Reason codes

| Code | Decision | Meaning |
|-|-|-|
| I1 | included | core: title covers ≥ half the concepts and the abstract covers ≥1 |
| I2 | included | peripheral: relevant but partial concept coverage (score ≥ threshold) |
| I3 | included | include-uncertain: no abstract available; title on-topic; flag for full-text check |
| E1 | excluded | off-topic at title screen: no concept term in the title and <2 concepts in the abstract |
| E2 | excluded | low abstract relevance: relevance score below the threshold (default 0.35) |
| E3 | excluded | duplicate of an already screened record (canonical copy is kept) |
| E4 | excluded | excluded publication type (retraction etc.) |
| E5 | excluded | outside the requested year window |

## Scoring formula (stage 2)

```
score = 0.55 * (fraction of concepts with ≥1 term in the title)
      + 0.30 * (fraction of concepts with ≥1 term in the abstract)
      + 0.15 * min(log(1 + cited_by) / log(1 + 5000), 1)
```

A "concept" is the agent-defined unit from `/app/work/terms.json`: a name plus its
expanded term set (abbreviations, spelling variants, zh/en equivalents). Concept
coverage is facet-level recall, so a paper mentioning only one synonym of every
concept still scores full coverage.

## Decision order (first match wins)

1. **Type gate (E4/E5).** Retractions and out-of-window years are excluded before
   content screening; they stay visible in the ledger.
2. **Stage 1 — title screen (E1).** No concept term in the title AND fewer than 2
   concepts in the abstract. This is the high-volume precision filter.
3. **Stage 2 — abstract screen (E2).** Score below threshold. The ledger records the
   actual score and the threshold, so the border is reproducible.
4. **Include (I1/I2/I3).** Code by coverage strength; I3 marks records whose abstract
   is missing — they are honest uncertainties, not silent inclusions.

## Evidence snippet

For every included or E2-excluded record the ledger stores the first abstract sentence
containing a concept term (fallback: the title). A reviewer can therefore check each
decision against the exact text the engine saw, without re-running anything.

## Omission accounting

`omissions.md` lists (a) concepts with zero retrieved records — genuine coverage gaps
that belong in `result.json` `uncertainty`, and (b) the ten highest-scoring E2
exclusions — the borderline set a human would re-check first if the threshold is
questioned.

## Tuning

- `--threshold` (default 0.35): raise toward 0.45 for precision-critical reviews,
  lower toward 0.25 for scoping searches. State the chosen value in the report.
- Concept design dominates quality: 3–6 well-expanded concepts beat 10 raw keywords.
  Put abbreviations and Chinese equivalents in `expanded`, not in separate concepts.
