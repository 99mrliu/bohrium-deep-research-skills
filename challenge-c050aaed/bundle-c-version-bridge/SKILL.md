---
name: version-bridge
description: >-
  Version lineage and cross-version annotation migration (版本谱系/跨版本归并).
  Use when a library contains the same document in multiple versions or
  duplicate downloads (版本关系, 重复下载) and annotations must be migrated onto
  the newest version with explicit per-annotation status (批注迁移, 归并) so
  notes are never silently split or mixed across versions (版本串味).
---

# version-bridge

Build an evidence-typed identity graph over a document library (which files
are the same document, which is newer) and migrate annotations from old
versions onto the canonical version's text with explicit per-annotation
status: `migrated` / `shifted` / `orphaned` / `native`.

## When to use

- The case library holds several versions of one document, or byte-identical
  duplicate downloads under different names/paths.
- Annotations exist on more than one version and must be consolidated onto a
  single canonical version without merging or losing any of them.
- The case asks which files are duplicates, which is newest, or where each
  annotation should live after 归并.

Do NOT use it for within-file extraction, note authoring, or retrieval
(see Boundaries).

## Inputs & runtime contract

- Inputs: `/input/case.json`, `/input/task.md`, plus the case's real material
  files. Work under `/app/work`; write deliverables under `/app/output`.
- `/app/output/result.json` MUST contain the original `case_id` and every
  field named by the case's `output_contract` — read the contract dynamically
  from `case.json` at runtime; never hardcode field names.
- Write a partial `result.json` EARLY (after the first artifact), then
  improve it in place. `status` ∈ {`complete`, `partial`, `failed`}.
- Record `sources`, `uncertainty`, and `change_records`; record every skip,
  failure, conflict and recovery. Never fabricate content or evidence.

## Producing page texts in the eval environment

Scripts operate on text artifacts, never on binary PDFs:

1. `manifest.json` — inventory of the library, schema
   `version-bridge/manifest@1` (see `references/version_schema.json`):
   one entry per file with `relpath`, `sha256`, `size`, `mtime`
   (ISO-8601 UTC). Build it with `hashlib` + `os.stat`.
2. `texts/<filekey>/page-NNN.txt` — extracted page texts, where
   `filekey = relpath` with `/` replaced by `__` (e.g. `notes_v1.txt`,
   `downloads__report.pdf`). Produce them by probing, in order:
   - `shutil.which("pdftotext")` → `pdftotext -layout in.pdf out.txt`,
     then split `out.txt` on the form-feed `\f` into `page-001.txt`,
     `page-002.txt`, ... (strip a trailing empty page).
   - else `import fitz` (PyMuPDF) → `page.get_text()` per page.
   - else honest failure: state in `result.json` that page texts could not
     be produced, mark `status: "partial"`, and record it in
     `change_records`. Plain-text sources (`.txt`/`.md`) are their own page
     texts: copy to `texts/<filekey>/page-001.txt`.
3. `annotations.jsonl` — one JSON object per line:
   `{annotation_id, file, file_sha256, page, type, anchored_text, contents}`
   where `file` is the manifest `relpath` of the version the annotation was
   taken on. Take annotations exactly as the case provides them; if the case
   gives no annotations, say so and skip migration (record the skip).

## Workflow

Run from the installed skill; keep intermediate artifacts in `/app/work` and
final ones in `/app/output`:

```bash
python3 /skills/weekly-skill/scripts/version_graph.py \
  --manifest /app/work/manifest.json --texts-dir /app/work/texts \
  --out /app/output/version_graph.json
python3 /skills/weekly-skill/scripts/migrate_annotations.py \
  --annotations /app/work/annotations.jsonl --texts-dir /app/work/texts \
  --graph /app/output/version_graph.json \
  --out /app/output/migration_report.jsonl
python3 /skills/weekly-skill/scripts/merge_plan.py \
  --graph /app/output/version_graph.json \
  --migration /app/output/migration_report.jsonl \
  --out /app/output/merge_plan.json \
  --read-only <relpath-of-each-file-the-case-marks-untouchable>
```

If `task.md` contains administrative version notes (e.g. "v3 is the final
draft"), prefer them over mtime when they conflict with the graph, and record
the override in `result.json` (`change_records` + `uncertainty`); see
`references/merge_playbook.md`.

## Outputs

- `version_graph.json` — nodes, typed edges with evidence (`byte_duplicate`,
  `renamed_copy`, `version_of` with the similarity ratio), clusters with a
  canonical member and the rule used, `metadata_conflicts`, `uncertainty`.
- `migration_report.jsonl` — one record per annotation: status, source and
  target file hashes, target page/char offsets, ratio, uncertainty/notes.
- `merge_plan.json` — per cluster: canonical, aliases (never deleted),
  status counts, conflict queue, `read_only`, `requires_human_review`
  (empty ⇒ `fully_automatic: true`).
- `result.json` — the case contract, filled as described above.

## Failure handling

Exit codes: `0` success · `2` usage/input error (nothing or partial written)
· `3` degraded — output still written, but some evidence was unobtainable
(e.g. missing page texts → `similarity_unavailable` conflict; migration
records with `status: "error"`). On any non-zero exit, mirror the reason into
`result.json` (`status: "partial"` or `"failed"`, `change_records`). Missing
texts never get guessed; unknown similarity is reported as unknown.

## Boundaries

- No extraction of annotations from raw binary PDFs — annotations arrive as
  JSONL text artifacts only.
- No note authoring / summarization; no retrieval index or search API.
- Never deletes, moves or overwrites input files; never merges two
  annotations into one.

## Minimal example

A complete synthetic fixture library with real observed output lives in
`examples/`: three byte-identical reports, `notes_v1.txt` → `notes_v2.txt`
(one paragraph moved, one sentence reworded, one deleted), 4 annotations
(migrated / shifted / orphaned / native). See `examples/README.md` for the
exact commands and `examples/EXPECTED.md` for the observed output.
