# Methodology — multi-round query planning engine

This document records the exact rules `scripts/planned_search.py` implements, so every
returned paper and every ranking number can be defended or reproduced.

## 1. Facet decomposition (agent-authored plan)

The agent writes `/app/work/plan.json` after reading the case:

- `facets`: 2–5 conceptual components of the research question. Each facet has a `name`,
  1–4 `terms`, and optional `expanded` synonyms (abbreviations, spelling variants,
  Chinese equivalents for Chinese questions). Every facet explicitly present in the
  research question must appear in the plan; facets that cannot be covered are reported,
  not dropped.
- `databases`: subset of `crossref`, `openalex`, `europepmc`. EuropePMC is included only
  for biomedical questions.
- `year_from` / `year_to`: inclusive bounds, `null` when the case imposes none.

If no plan exists, the engine derives facets by token-frequency over the question
(stopword-filtered, max 4 facets) and marks `plan_origin: auto-fallback` in the report.

## 2. Query construction and round schedule

| Round | Name | Construction | Purpose |
|-|-|-|-|
| 0 | local-ingest | none — scans `/input/**/*.json` for saved Crossref/EuropePMC/OpenAlex responses or reference lists | organizer-provided source-bound material is always authoritative |
| 1 | core-AND | `(f1t1 OR f1t2 OR f1t3) AND (f2t1 OR ...) ...` across all facets | high-precision anchor set |
| 2 | facet-relaxed | one query per facet: `t1 OR t2 OR t3 OR t4` | recall per sub-topic, rescues facets the AND query starves |
| 3 | question-plain | stopword-filtered free text of the question, ≤160 chars | catches phrasing the facets missed |
| 99 | snowball | OpenAlex `cites:` and `cited_by:` filters on the top-5 scored seeds with OpenAlex IDs | citation-graph expansion, both directions |

Crossref is queried with `query.bibliographic`, OpenAlex with `search`, EuropePMC with
`query`. Each round queries every selected database with `rows=20` (snowball: 25).

**Stop criterion.** After each of rounds 1–3, if the round added fewer than
`max(2, 5% of pool)` new unique records, later relaxed rounds are skipped and the stop
reason is recorded. The snowball round always runs when OpenAlex is available.

## 3. Deduplication

Key = lowercased DOI when present, else the title normalized to `[a-z0-9 ]`. A second
copy of a record adds a `provenance` entry to the existing record and fills a missing
abstract; it never creates a new candidate.

## 4. Relevance scoring (fixed formula)

```
score = 0.5 * (fraction of facets with ≥1 term in the title)
      + 0.3 * (fraction of facets with ≥1 term in the abstract)
      + 0.2 * min(log(1 + cited_by) / log(1 + 5000), 1)
```

Records outside the requested year window are multiplied by 0.3 (down-ranked, not
deleted, so they remain auditable). The formula is intentionally simple and lexical:
its behavior is fully explainable from `plan.json`, and every 0.1 of score difference
can be attributed to a specific term presence.

## 5. Evidence records

- `evidence/search_log.jsonl`: one line per executed query —
  `{round, tag, source, query, url, ok, error, hits, new_unique, elapsed_s}` plus
  snowball lines with the seed OpenAlex ID. Re-issuing the `url` reproduces the query.
- `evidence/raw/*.json`: the first raw API response per (round, database, query), capped
  at 400 KB, with its URL. Candidates reference these files in `provenance[].raw`.
- `search_report.md`: plan origin, facets, databases, record counts, stop reason,
  per-facet coverage table, and the failure list. Facets with zero hits are marked
  **NOT COVERED** and must surface in `result.json` `uncertainty`.

## 6. Failure semantics

- A source that errors (timeout, HTTP error, rate limit) is retried once with backoff,
  then recorded in `search_report.md` and the digest; the run continues with the
  remaining sources.
- `ENGINE_STATUS` is `partial` when offline, when any source failed and the pool is
  empty, or when facets remain uncovered; otherwise `success`.
- The engine never synthesizes records, never fills missing metadata by guessing, and
  never deletes a retrieved record (down-ranking only).
