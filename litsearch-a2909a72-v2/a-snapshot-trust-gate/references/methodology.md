# Methodology — snapshot-trust-gate

Every decision the engine makes is listed here so a reviewer can re-derive it.

## 1. Discovery and classification

All files under `--input` (organizer material) and `--corpus` (agent-saved raw
responses) ending in `.json`/`.xml` are considered, except `case.json` and
`result.json`. Each file is SHA-256 hashed (first 12 hex chars reported) and
classified by payload shape:

| shape | source_type |
|-|-|
| `{"message": {"items": [...]}}` | crossref |
| `{"resultList": {"result": [...]}}` | europepmc |
| `{"results": [...]}` | openalex |
| `{"records": [...]}` | generic-records |
| `{"message": {"DOI": ...}}` | crossref-single |
| anything else | — (quarantined) |

## 2. Snapshot-level quarantine reason codes

| code | meaning | rationale |
|-|-|-|
| `PARSE_ERROR` | file is not valid JSON (truncated download, wrong encoding, HTML error page saved as .json) | a truncated page silently drops tail records; using it understates recall |
| `DUPLICATE_PAYLOAD` | SHA-256 identical to an earlier file | ingesting twice doubles record weight and breaks dedup accounting; first copy wins |
| `SCHEMA_UNRECOGNIZED` | JSON parses but matches no known snapshot shape | cannot extract records without guessing field semantics |
| `EMPTY_RECORD_LIST` | recognized schema, zero records, and not a legitimate empty result page | usually a failed query saved as if successful |

A Crossref page with `total-results: 0` is *not* quarantined: it is a legitimate
empty response and is noted as such.

## 3. Record-level flags (kept, but visible)

Records stay in the corpus but carry `record_flags`; a snapshot with any flagged
record is downgraded to trust tier **T2-flagged-records** (else **T1-verified**):

- `DOI_FORMAT_INVALID` — DOI does not match `^10\.\d{4,9}/\S+$`
- `TITLE_MISSING`
- `YEAR_IMPLAUSIBLE` — year outside 1450–2100
- `NO_IDENTIFIER` — neither DOI nor title (record kept only under an
  anonymous key so it can never merge with another record)

## 4. Normalization

Per record: title (first element if list), authors (Crossref given+family /
EuropePMC authorString split / OpenAlex authorships), year (Crossref
`issued.date-parts[0][0]`, EuropePMC `pubYear`, OpenAlex `publication_year`),
venue, DOI (lower-cased, `https://doi.org/` prefix stripped), abstract (HTML tags
stripped; OpenAlex inverted index reconstructed).

## 5. Deduplication

Key = `doi:<normalized DOI>` when present, else `title:<lowercased alphanumeric
title>`. Later duplicates are not discarded silently: their provenance is appended
to `also_in` so multi-source corroboration remains visible.

## 6. Retrieval scoring (deterministic)

Query terms = lowercase alphabetic tokens (len > 2, stopword-filtered) plus
bigrams of every CJK run — this handles Chinese questions without a segmenter.

Per term: +3.0 if it appears in title, else +1.0 in abstract, else +0.5 in venue.
If the case specifies `year_from`/`year_to`, records outside the window are
halved (soft penalty, never silent exclusion). Ranking: score desc, year desc,
title asc. Records with score 0 are excluded from `candidates.*` but remain in
`verified_corpus.json`.

`zero_hit_terms` = query terms matched by no record — reported as coverage gaps.

## 7. Known limits (state them, do not patch around them)

- Term matching is literal: no synonym expansion. If recall matters, the agent
  should fetch extra raw responses with variant terms (step 2 of SKILL.md) —
  the gate then covers those too.
- `.xml` files are hashed and inventoried but not parsed (EuropePMC XML is
  uncommon in organizer snapshots); an XML-only case yields `partial` with an
  explicit note.
- No full-text analysis: abstracts only, exactly as delivered by the source.
