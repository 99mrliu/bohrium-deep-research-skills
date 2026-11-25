# Catalog schema (catalogforge.py)

## catalog.jsonl — one record per line

```json
{
  "id": "<first 12 hex of sha256(relative path); unique per file>",
  "content_id": "<first 12 hex of sha256(content); shared by duplicates>",
  "path": "<relative path in library>",
  "name": "<filename>",
  "ext": ".md",
  "size": 1234,
  "mtime": "<utc iso>",
  "readable": true,
  "sha256": "<64 hex>",
  "title": "<first non-empty line, heading stripped>",
  "excerpt": "<first ~2000 chars, text files only>",
  "metadata": {"...": "merged from sidecar keyed by filename"},
  "metadata_source": "sidecar",
  "role": "canonical",
  "duplicate_of": "<id of canonical, when identical content>",
  "version_cluster": "<normalized stem shared by versions>",
  "edges": [{"src": "...", "dst": "...", "kind": "...", "evidence": "..."}]
}
```

## catalog.edges.json

```json
{"generated_at": "...", "edges": [
  {"src": "<id>", "dst": "<id>", "kind": "duplicate_of",
   "evidence": "identical sha256 <prefix>"},
  {"src": "<id older>", "dst": "<id newer>", "kind": "superseded_by",
   "evidence": "same stem 'notes'; version marker / mtime order"},
  {"src": "...", "dst": "...", "kind": "superseded_by",
   "evidence": "administrative note: <verbatim line>"}
]}
```

Edge rules:
- `duplicate_of` requires identical sha256 — filename similarity alone
  never suffices.
- Heuristic `superseded_by` requires same normalized stem + extension and
  different content; order comes from explicit `vN` markers, then mtime.
- An administrative-note edge quotes the verbatim note line and overrides
  the heuristic order for the same pair.

## library.sqlite

- `files(id PK, path, name, ext, title, sha256, size, mtime, role,
  duplicate_of, version_cluster, excerpt, metadata)`
- `edges(src, dst, kind, evidence)`
- `fts(title, name, excerpt, metadata, path)` — FTS5 virtual table when
  the runtime's sqlite3 provides FTS5; otherwise absent and queries fall
  back to per-field substring matching. Check which mode is active with:
  `SELECT name FROM sqlite_master WHERE name='fts';`

## answers.jsonl

```json
{"qid": "q1", "question": "...", "status": "answered|unanswered",
 "evidence": [{"id": "...", "path": "...", "title": "...",
               "sha256": "...", "matched_field": "fts|title|excerpt|...",
               "snippet": "..."}],
 "note": "...", "reason": "<only when unanswered>"}
```
