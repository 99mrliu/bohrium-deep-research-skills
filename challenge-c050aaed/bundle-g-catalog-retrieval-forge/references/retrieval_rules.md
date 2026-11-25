# Retrieval and contract rules (catalogforge.py)

## Query semantics

1. **FTS5 mode**: the query string is split on whitespace; tokens are
   AND-combined as quoted phrases (`"tok1" AND "tok2"`). This favors
   precision; a multi-word question with one rare token may return zero
   hits — that is a signal to retry per-token, not a library defect.
2. **Fallback / supplement**: when FTS5 is missing or returns nothing,
   every field (title, name, excerpt, metadata, path) is scanned with
   case-insensitive substring matching. Because CJK questions arrive
   without whitespace, each long CJK term is expanded into character
   bigrams. **Relevance gate**: a record counts as a hit only when a full
   original term matches, or at least 3 distinct bigrams match — a single
   shared pair (e.g. "催化") is noise, not evidence, and must not turn an
   unanswerable question into a fabricated answer. Hits are ranked by
   matched-term count.
3. Every hit reports: record id, path, sha256, matched field, and a
   snippet centered on the first matched term. A hit without a snippet
   and hash is not evidence — treat it as a lead to open the file.

## Recall discipline

- Zero hits always produce `recall_note` with: the token list, a
  suggestion to query individual terms, and a reminder that zh/en
  variants or metadata-only content may be involved.
- Before declaring a question unanswerable, run at least: the full
  question, its core noun phrase, and one synonym/language variant.
  Record which formulations were tried when abstaining.
- Prefer three precise hits over ten weak ones (`--k`); cite only hits
  whose snippet actually supports the answer.

## Contract assembly discipline

- `case_id` is copied verbatim from case.json (`case_id`, else `id`).
- `output_contract` may be a dict (field names = keys) or a list (strings
  or objects with `name`); both are accepted.
- Fill order per contracted field: existing draft value → `--map
  field=artifact` file (JSON parsed, else raw text) → `not_produced`
  marker with reason. The script never invents field content.
- Exit code of `contract` is 1 while any field is `not_produced`; treat
  this as a checklist, and explain each gap in the final answer.
- Prose fields the contract demands (summaries, 说明) are written by the
  Agent from the artifacts and passed via `--draft`; the script preserves
  them untouched.
