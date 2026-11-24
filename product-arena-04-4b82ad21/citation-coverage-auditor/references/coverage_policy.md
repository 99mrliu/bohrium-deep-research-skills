# Coverage policy — what must be covered, and why

This document is the doctrine behind `coverage_ledger.py`. It tells the
writer what an adequately covered introduction/related-work citation layer
looks like, and names the anti-patterns the audit is designed to catch.
The concrete example below uses the six **synthetic** references of the
bundled demo case (invented works; interface demonstration only).

## The three coverage layers

### 1. Closest works first (same problem setting)

The works that share the manuscript's problem setting must be cited and
discussed before anything else. Reviewers know these works and look for them
immediately; omitting one reads as either ignorance or evasion.

`coverage_ledger.py` operationalizes "closest" as content-word overlap
between each reference's title+abstract and the **problem statement** in the
manuscript fact base (`case.json → material.manuscript_facts`). A top-2
closest reference left uncited is a **hard failure**. The ranking is a
lexical heuristic: always confirm by reading the provided abstract that the
work really does address the same setting.

### 2. Representative works per route

Each method family ("route") that the field recognizes — and that the
provided bibliography instantiates — should be represented by at least one
cited work. You do not need every member of a family; you need a
representative whose cited statement is accurate. If the case mandates
topics (`constraints.must_cover_topics`), each mandated topic must map to at
least one **cited** reference; an uncovered mandated topic is a **hard
failure**.

### 3. Recent progress

The recency profile (histogram of cited-reference years) exists to catch
staleness. When the most recent bibliography entries are ignored, the ledger
raises a warning: either the newest works are irrelevant (say so to
yourself, explicitly, by reading them) or the related-work section is
out of date. Cite recent works where they genuinely play a role — not as a
decorative "recently, many methods [3-7]" gesture.

## Minimum distinct citations

`constraints.min_distinct_citations` is a floor on **genuinely relevant**
citations, never a quota. If the draft is below the floor, the correct fix
is to find provided works that truly belong in the argument (closest works,
route representatives, recent progress) and give them real sentences. The
wrong fix is to sprinkle markers into clusters — that is exactly what the
decorative-citation lint flags.

## Worked synthetic coverage table

The demo case mandates three topics and `min_distinct_citations: 4`. With
all six synthetic references cited, the ledger produces (real output,
`examples/sample-output/coverage_ledger.md`):

| layer | synthetic ref | year | role it is cited for |
|---|---|---|---|
| closest work (top-1 overlap with the problem statement) | synth01 TemplateTransfer | 2021 | single-template transfer; precision 0.55 above 40% identity, 0.41 below 30% — the exact weakness the manuscript attacks |
| closest work (top-2) | synth02 SeqPocket | 2022 | sequence-only route; matches template-based on template-free targets, lags on template-rich ones |
| route representative: multi-template pooling | synth03 MultiTempl | 2023 | pooling raises recall +0.15 but flat low-identity precision (equal-weight votes) |
| route representative: geometry-based | synth04 GeoScore | 2020 | fast, template-free; no comparison vs template-based reported |
| recent progress (newest entry) | synth05 ConsenSite | 2024 | consensus across homologous structures; +0.07 precision; needs target's own structures |
| field frame / survey | synth06 survey | 2019 | taxonomy of families; low-identity transfer is the weakest setting |

Checklist results for this table: distinct citations 6 >= 4 (PASS); all three
mandated topics mapped to cited refs (PASS); top-2 closest works cited
(PASS); newest year 2024 cited (PASS); no decorative clusters (PASS).

## Anti-patterns (what the audit is designed to catch)

1. **Chronological listing.** "In 2019, A did X. In 2020, B did Y. In 2021,
   C did Z." Organize by problem and route, not by year. The ledger cannot
   see prose structure — this one is on the writer; the doctrine forbids it
   because chronological tours never state what each work *means* for the
   gap.
2. **Decorative clusters.** "Many approaches exist [4-6]." where refs 4-6
   are never named or characterized. The lint flags bibliography-tail refs
   cited exactly once inside a 3+ marker cluster with no sentence-level
   role. Every citation must earn its marker: if removing it loses no
   information, remove it.
3. **Citing title-only refs for findings.** A reference with
   `evidence_level: "title-only"` may be cited for the *existence and topic*
   of its route, never for results, numbers, or methods — those are not in
   the provided material, and attributing them fabricates evidence.
4. **Quota filling.** Adding markers to reach `min_distinct_citations`
   without giving the works real sentences. Indistinguishable from
   decorative clustering; treated the same way.
5. **Ignoring the closest work.** Citing six peripheral works while skipping
   the one that shares the problem setting. The ledger fails this outright
   (top-2 closest uncited).
6. **Stale related work.** No citation from the most recent bibliography
   year(s). Warning-level, but in a real review it reads as a manuscript
   written before the field's current state.
7. **Gap not grounded in cited limitations.** The gap statement must follow
   from the limitations of the works actually cited (as in the demo: single
   template dependence, equal-weight voting, missing low-identity
   evaluation), not from a generic "this topic is important".
