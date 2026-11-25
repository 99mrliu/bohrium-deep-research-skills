# Methodology — graded-relevance-bench

Every decision the engine makes is listed here so a reviewer can re-derive any
grade from the raw snapshot and the facets file alone.

## 1. Pool construction

All `.json` files under `--input` (organizer material) and `--corpus`
(agent-saved raw responses) are consulted, except the engine's own outputs and
`case.json` / `facets.json` / `result.json`. Payload shapes recognized:

| shape | source |
|-|-|
| `{"message": {"items": [...]}}` | Crossref page |
| `{"resultList": {"result": [...]}}` | EuropePMC page |
| `{"results": [...]}` | OpenAlex page |
| `{"records": [...]}` | generic record list |

Files that fail to parse or match no known shape are skipped and listed in
`ranking_report.md` — nothing is dropped silently. Per record the engine
extracts title, authors, year, venue, DOI (lower-cased, `https://doi.org/`
prefix stripped) and abstract (HTML tags stripped; OpenAlex inverted indexes
reconstructed). Missing fields stay `null`.

**Dedup:** key = `doi:<normalized DOI>` if present, else
`title:<lowercased alphanumerics-only title>`. Duplicates merge into the first
record; their provenance is appended to `also_in` and `duplicates_merged` is
counted in the digest. Records with neither DOI nor title are skipped with a
reason (they can never be deduplicated or evidenced).

## 2. Facets

Preferred source: agent-authored `<work>/facets.json`:

```json
{"facets": [{"name": "material", "terms": ["perovskite", "halide perovskite"]}, ...]}
```

2-5 facets are expected; extra facets are truncated to the first 5 with a
note; facets with no usable terms are dropped. Terms are lower-cased at load.

Fallback (when no usable facets.json exists): the research question is
tokenized into lowercase alphabetic tokens (length > 2, stopword-filtered)
plus bigrams of every CJK run, and **each content term becomes its own
single-term facet**. The fallback is always announced in the digest
(`facets_source: fallback-auto ...`) and in `ranking_report.md`, because
single-term facets lack synonyms and make grades noisier.

## 3. Matching and the exact grading rubric

Matching is **literal, case-insensitive substring** matching of each facet
term against the record's title and abstract. No stemming, no embeddings, no
synonym expansion beyond the terms written in `facets.json`.

For each facet of a record, define:

- `title_hits` = distinct facet terms found in the title
- `abstract_hits` = distinct facet terms found in the abstract

Facet status:

| status | condition | contribution |
|-|-|-|
| `hit` | `len(title_hits) >= 1` **or** `len(abstract_hits) >= 2` | 1.0 if any title hit, else 0.6 |
| `weak` | exactly `len(abstract_hits) == 1` and no title hit | 0.2 |
| `miss` | otherwise | 0.0 |

Let `H` = number of facets with status `hit`, `W` = number with status `weak`,
`N` = number of facets. The record's grade:

| grade | exact rule |
|-|-|
| **3** | `H == N` and `N > 0` — every facet hit (each via ≥1 title term or ≥2 abstract terms) |
| **2** | `H > N/2` but `H < N` — a strict majority of facets hit |
| **1** | `1 <= H <= N/2` (minority), **or** `H == 0 and W >= 1` (weak-only / borderline evidence, e.g. one facet term mentioned once in the abstract) |
| **0** | `H == 0 and W == 0` — nothing matched anywhere |

Consequences worth knowing: with 3 facets, 2 hits → grade 2, 1 hit → grade 1;
with 2 facets, 1 hit is not a majority → grade 1; a single abstract mention of
a single term never counts as a facet hit, it surfaces as `weak` and pushes
the record to grade 1 / the borderline queue.

## 4. Score decomposition (per record, per facet)

`score_decomposition` is a list with one entry per facet:

```json
{"facet": "material",
 "matched_terms": {"title": ["perovskite"], "abstract": ["perovskite"]},
 "fields": ["title", "abstract"],
 "status": "hit",
 "contribution": 1.0,
 "evidence": ["title: Defect passivation for moisture-stable halide perovskite solar cells",
              "abstract: ...the sentence containing the matched term..."]}
```

Evidence snippets are the full title (for title matches) or the first
abstract sentence containing each matched term (trimmed to ~240 chars with
ellipses). A human can verify every contribution point against these snippets
without opening the snapshots.

## 5. Confidence tiers

| tier | rule |
|-|-|
| `clear-include` | grade ≥ 2 **and** at least one facet hit is evidenced in the title |
| `borderline` | grade 1, **or** grade ≥ 2 with *all* facet hits abstract-only (a grade built purely on abstract mentions is exactly the judgment call an agent should make) |
| `clear-exclude` | grade 0 |

Only `borderline` records enter `borderline_queue.json`. Each queue entry
carries the full decomposition plus *specific questions for the adjudicator*:
one per weak facet term ("does term X appearing only in the abstract satisfy
facet Y for the research question?") and, for abstract-only grade-≥2 records,
one per abstract-only hit facet ("are abstract-only mentions of terms [...]
sufficient evidence ...?").

## 6. Ranking and tie-breaks

Records are ranked by: final grade desc → facet coverage (`H/N`) desc → weak
hits desc → year desc (missing year last) → title asc. Fully deterministic:
same pool + same facets → same ranking, always.

## 7. Adjudication and the agreement metric

`--adjudicate FILE` accepts `{"<doi-or-id>": 0|1|2|3}` or
`{"<doi-or-id>": {"grade": g, "rationale": "..."}}`. Keys starting with `_`
(e.g. `_note`) are ignored as metadata. Keys may be the engine id
(`doi:...` / `title:...`) or a bare DOI; unknown keys are rejected with the
full valid id list and nothing is written (exit 3). Applied grades become
`final_grade`; the engine grade is preserved alongside, and every change is
ledgered in `adjudication_ledger.md` with the rationale. Non-adjudicated
records keep their engine grade as final grade. Adjudicated records leave
`borderline_queue.json` (they are decided; the ledger is their record), so a
fully adjudicated run reports `borderline_count: 0` plus
`borderline_resolved_by_adjudication`.

**Engine-vs-adjudication nDCG@10** (self-consistency, *not* a benchmark
score): with `gains g_i` = adjudicated grade of the record at engine-rank `i`,

```
DCG@10  = Σ_{i=1..10} (2^{g_i} - 1) / log2(i + 1)      over the engine ranking
IDCG@10 = same sum over the adjudicated grades sorted descending
nDCG@10 = DCG@10 / IDCG@10        (null if IDCG == 0, i.e. all grades 0)
```

It measures how well the engine's *order* anticipates the adjudicated grades.
A high value means the engine's ranking needs little reordering; it says
nothing about absolute relevance quality.

## 8. Known limits (state them, do not patch around them)

- **Literal term matching only.** No stemming ("passivating" ≠ "passivation"
  unless both are listed), no synonyms, no translations. The intended fix is
  agent-authored `facets.json` with synonyms and morphological variants —
  that is step 3 of SKILL.md, not an engine patch.
- **Abstract-only evidence is inherently weaker**, which is why single
  abstract terms are `weak` and abstract-only grades are pushed to the
  borderline queue rather than trusted.
- **No full text, no citation context:** title + abstract as delivered by the
  snapshot, nothing more.
- **Facet quality bounds grade quality.** The fallback single-term facets are
  a safety net; interpret fallback-mode histograms with suspicion.
- **nDCG is self-consistency.** With no gold labels in a source-bound case,
  the number compares the engine against the agent's own adjudications; it
  must never be presented as benchmark nDCG.
