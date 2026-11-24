# Retrieval Protocol

How the retrieval entry (`scripts/build_index.py` + `scripts/query.py`) indexes,
matches, ranks, and reports. Everything here is stdlib-only and deterministic:
no wall-clock fields, sorted serialization, `(-score, doc_id)` tie-breaking.

## Documents and locators

The index holds one document per input record:

| kind        | id               | text                                   | type        | date                          |
|-------------|------------------|----------------------------------------|-------------|-------------------------------|
| annotation  | `annotation_id`  | `anchored_text` + `contents`           | `type`      | inventory mtime of its `file` |
| note        | `note_id`        | `claim` + all evidence `quote`s        | `note_type` | `created_at`                  |
| file        | `file:<relpath>` | `relpath`                              | `"file"`    | inventory `mtime`             |

Every document carries its full source locator: `kind`, `id`, `file` (plus
`files` for multi-file notes), `page`, `type`, `tags`, `date`, `text`. Dates
normalize to `YYYY-MM-DD`; epoch numbers are treated as UTC.

## Tokenization

- **Latin**: lowercased runs of `[a-z0-9]+`. `"O(n^2)"` → `o`, `n`, `2`;
  `"sparse-attention"` → `sparse`, `attention` (hyphens split).
- **CJK**: characters in U+3400–U+4DBF / U+4E00–U+9FFF are grouped into maximal
  runs and emitted as overlapping **bigrams**: `增量学习` → `增量`, `量学`, `学习`.
  A lone CJK character is kept as a unigram so single-character text remains
  matchable. The same tokenizer runs at index time and query time, so any CJK
  substring of length ≥ 2 matches without a dictionary.

## Indexed fields and scoring

Indexed fields per document: `text`, `tags`, `type`, `file`. The inverted index
stores `index[term][doc_id][field] = tf`.

Query `--q` is tokenized identically. Scoring is a plain term-frequency sum
over matched fields:

```
score(doc) = Σ over query terms t  Σ over fields f  tf(t, doc, f)
```

Consequences, by design: a term repeated in a document weighs more; a hit in
`tags` counts the same as a hit in `text`; documents matching more distinct
query terms outrank documents matching one term many times only if their total
tf is higher. Ranking sorts by `(-score, doc_id)`. A query with no `--q`
returns all filter-passing documents with score 0.

## Facet semantics (filters)

Filters are applied after scoring and never change scores:

- `--tag T` — exact string membership in the document's tag list.
- `--type T` — exact match on document type (e.g. `highlight`, `claim`).
- `--file F` — exact relpath match against every file the document is located
  in (a note citing three files matches any of the three).
- `--since` / `--until DATE` — inclusive `YYYY-MM-DD` bounds on the document
  date. Documents without a date are excluded while a date filter is active.

## No-hit policy

Zero hits is a normal, reportable answer — never a silent empty list. The
no-hit report contains a **facet-elimination diagnosis**: each active facet is
removed one at a time and the query retried; a facet whose removal alone
restores hits is named in `eliminating_facets`. If no single facet is
responsible but removing all of them restores hits, `combination_eliminated`
is set. If the bare text query still matches nothing,
`text_terms_matched_nothing` is set with suggestions to check spelling variants,
synonyms, or broader terms (remembering CJK matches by bigrams, so a one-off
character in a longer word still matches).

## Low-recall policy

`LOW_SCORE_THRESHOLD = 2.0` (defined in `query.py`). When a text query's best
score is below the threshold, the whole response is marked
`low_confidence: true` and each weak hit carries its own flag. Rationale: a
score under 2.0 means the best document matched a query term only once in a
single field — plausible, but weak. Consumers of the result must surface this
flag (e.g. in result.json `uncertainty`) instead of presenting weak hits as
solid recall.

## Query log and reviewer replay

With `--log query_log.jsonl`, every query appends one line:

```
{"seq": 3, "args": {"q": "...", "tag": null, "type": null, "file": null,
 "since": null, "until": null}, "hits": 2, "low_confidence": false}
```

`seq` is the previous line count + 1; there is deliberately **no wall-clock**,
so the log is byte-stable across replays. A reviewer replays any search by
re-running `query.py` with the recorded `args` against the same `index.json`;
because scoring, filtering, and ranking are deterministic, the hit list and
ranking reproduce exactly. The gate's replay-determinism check additionally
guarantees the shipped `index.json` is byte-identical to a fresh rebuild from
the recorded inputs, so the log replays against the true index.
