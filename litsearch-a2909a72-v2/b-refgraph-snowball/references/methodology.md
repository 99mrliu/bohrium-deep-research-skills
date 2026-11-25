# Methodology — refgraph-snowball

Every rule the engine applies, so a reviewer can re-derive each decision.
Constants are named in `scripts/refgraph.py`; nothing is tuned per case.

## 1. Question and seed extraction

- Research question: first non-empty of `research_question`, `question`,
  `query`, `topic`, `title` in `case.json` (string or `{text|question|title|
  description}` dict); else the first substantive line of `task.md`
  (≥ 12 chars, not an output/input/contract heading).
- Query terms: lowercase `[a-z][a-z0-9-]+` tokens (len > 2, stopword-filtered)
  plus bigrams of every CJK run — this handles Chinese questions without a
  segmenter. Terms only feed the relevance tie-breaker (§6).
- Seeds, in priority order:
  1. `seed_dois` / `seeds` / `seed_papers` / `seed_records` in `case.json`
     (strings, dicts with `doi`/`title`, or nested lists) → `explicit-case`;
  2. `seeds.json` / `seed_papers.json` / `seeds.txt` directly under `--input`
     → `explicit-file:<name>`;
  3. otherwise the top-3 records by question-term score (title 2.0/term,
     abstract 0.5/term) become seeds and the digest says
     `seed_origin=derived-title-match` — a weaker starting point, flagged so
     the agent can override with real seeds.
- Seed-to-record matching: DOI exact, else normalized-title fuzzy (same rule
  as §4). Unmatched seed specs are listed in `seeds_unmatched`.

## 2. Snapshot shapes recognized

Walked under `--input` and optional `--corpus`; `case.json`, `result.json`,
`task.md`, seeds files are hashed into the evidence manifest but never parsed
as corpus.

| shape | source_type |
|-|-|
| `{"message": {"items": [...]}}` | crossref |
| `{"resultList": {"result": [...]}}` | europepmc |
| `{"results": [...]}` | openalex |
| `{"message": {"DOI": ...}}` | crossref-single |

Unparseable or unrecognized JSON is hashed, marked `role=unparsed` in the
evidence manifest, and contributes zero records (the engine is a snowballer,
not a quarantine gate — snapshot vetting is bundle A's job; here defects
surface as missing nodes/edges).

Per record normalized: title (first list element; OpenAlex `display_name`),
authors (Crossref given+family / EuropePMC `authorString` split / OpenAlex
`authorships[].author.display_name`), year (Crossref `issued.date-parts[0][0]`,
EuropePMC `pubYear`, OpenAlex `publication_year`), venue, DOI (lowercased,
`https://doi.org/` / `http://doi.org/` / `doi.org/` / `doi:` prefixes stripped,
trailing punctuation stripped), abstract (HTML tags stripped; OpenAlex
inverted index reconstructed), OpenAlex `W...` id.

Dedup key: `doi:<normalized>` when a DOI exists, else
`title:<lowercased alphanumeric+CJK title>`; records with neither get an
anonymous per-file key and can never merge. Duplicates are not discarded:
provenance goes to `also_in` and their reference lists are merged into the
kept record (a reference visible in only one copy still becomes an edge
candidate).

## 3. Reference extraction

- **Crossref** item `reference[]`: DOI from `DOI`/`doi`; title from
  `article-title`/`series-title`; `unstructured` text is scanned with
  `10\.\d{4,9}/[^\s"'<>\],;)}]+` for a DOI. Entries that are bare strings are
  treated as unstructured.
- **OpenAlex** `referenced_works[]`: the `W...` id is taken from each URL.
- **EuropePMC**: search-result records carry no reference list — documented
  limit; EuropePMC records contribute nodes, not edges.
- **Standalone reference files** (`.bib`, `.ris`, `.txt`, `.md` under the
  walked roots, excluding case material): `.bib` is split on `@entry`
  boundaries (DOI regex + `title = {...}`), `.ris` on `ER  -` (`DO  -` /
  `TI  -`), `.txt`/`.md` one reference per line (DOI regex, else the line
  itself as a fuzzy-matchable title). A standalone file is treated as **the
  reference list of the seed set**: each resolved target gets an edge from a
  `file:<name>` pseudo-node and is reachable at backward hop 1 from the seeds.
  This is the standard organizer pattern "here are the seed paper's
  references as an export".

## 4. Reference resolution

Each extracted reference is resolved against the local corpus in order:

1. DOI exact match → edge `via=doi`.
2. OpenAlex id exact match → edge `via=openalex-id`.
3. Title fuzzy match: `difflib.SequenceMatcher` on normalized titles, ratio
   **≥ 0.92** (`TITLE_MATCH_THRESHOLD`). If two or more distinct records tie
   within **0.005** (`AMBIGUITY_EPSILON`) of the best ratio → `ambiguous`,
   no edge.
4. Else the reference goes to the unresolved ledger with reason:
   `doi-not-in-corpus` (had DOI), `openalex-id-not-in-corpus`,
   `title-not-in-corpus` (had only a title), `no-identifier` (neither),
   `ambiguous`.

Resolved references become directed edges `record → referenced work`;
self-loops and duplicate edges are dropped. The ledger counts every reason —
unresolved references are coverage findings, not errors.

## 5. Snowball semantics

Breadth-first from the seed set, depth ≤ `--max-hops` (default 2):

- **backward**: follow outgoing edges (records the seed cites);
- **forward**: follow incoming edges (local records citing the seed).

Hop distance is the shortest distance from any seed in that direction; a
record reachable both ways is labelled `direction=both`. Seeds themselves are
hop 0. Records not reachable within the hop budget stay in `graph.json` but
never enter `candidates.*`.

## 6. Scoring formula (deterministic)

Per candidate, every component is shown in `score_breakdown`:

```
total = seed_base + backward_reach + forward_reach
      + cocitation_bonus + relevance_bonus

seed_base        = 10.0                       if the record is a seed, else 0
backward_reach   = 4.0 / hop_backward         if reachable backward, else 0
forward_reach    = 4.0 / hop_forward          if reachable forward, else 0
cocitation_bonus = 2.0 × (k − 1)              non-seeds only; k = number of
                                              distinct seeds directly citing
                                              or cited by the record (k ≥ 1)
relevance_bonus  = 2.0 × (question terms in title)
                 + 0.5 × (question terms in abstract)
```

Ranking: `total` desc, hop asc (seeds first), year desc, title asc — total
order, no randomness, same input → same output. The relevance term exists so
question-relevance breaks graph-ties; it can never promote an unreachable
record into the candidate set.

## 7. Outputs

- `graph.json` — nodes (with hop distances, provenance) + resolved edges.
- `candidates.json` / `candidates.md` — ranked candidates with full
  `score_breakdown`, hop, direction, matched terms, provenance
  `{file, json_index, sha256_12}`.
- `unresolved_references.md` — ledger + counts by reason.
- `search_report.md` — digest JSON + interpretation + honest gaps (unmatched
  seeds, seeds with zero resolvable refs, zero-density graph).
- `evidence/evidence_index.json` — sha256 manifest of every file consulted.
- Stdout: one-line JSON digest. Exit 0 when any records were loaded, 2 when
  the corpus is empty.

## 8. Known limits (state them, do not patch around them)

- Recall is bounded by the retained graph: a relevant record with no resolved
  citation path to any seed within `--max-hops` cannot be a candidate. Widen
  the corpus (SKILL.md step 2) or raise `--max-hops`; do not fabricate edges.
- No live coverage: the engine never validates DOIs against remote services;
  `doi-not-in-corpus` means absent *locally*, not nonexistent.
- Fuzzy title matching can still confuse near-identical titles; the ambiguity
  tie-rule refuses to guess, and refusals are ledgered.
- EuropePMC snapshots contribute no edges (their search shape carries no
  reference lists); PDFs under /input are hashed into the evidence manifest
  but not parsed.
- The relevance bonus is literal term matching — no synonym expansion; it is
  deliberately small so it cannot override graph structure.
