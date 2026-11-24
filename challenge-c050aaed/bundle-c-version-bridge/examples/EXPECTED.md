# EXPECTED — real observed output

Captured by actually running the commands in `README.md` (Python 3, stdlib
only) on this fixture library. Ratios are deterministic functions of the
fixture bytes; re-running on identical inputs yields byte-identical output
(verified, see Determinism below).

## 1. version_graph.py → exit 0

stderr: `version_graph: 6 nodes, 4 edges, 3 clusters, 0 metadata conflicts`

Edges (all four, with type and evidence):

| type            | from                  | to                | evidence |
|-----------------|-----------------------|-------------------|----------|
| byte_duplicate  | downloads/report.pdf  | report.pdf        | same sha256 `b28551bd…e3fa`, same basename |
| renamed_copy    | downloads/report.pdf  | report_copy.pdf   | same sha256, different basename |
| renamed_copy    | report.pdf            | report_copy.pdf   | same sha256, different basename |
| version_of      | notes_v1.txt          | notes_v2.txt      | stem `notes`, **text_similarity 0.7852** (char 5-gram Jaccard, ≥ 0.6), direction by mtime 2026-02-01 → 2026-02-05 |

Clusters:

- `c1` canonical **downloads/report.pdf** (newest mtime 2026-01-12 beats the
  other two copies), members: downloads/report.pdf, report.pdf,
  report_copy.pdf
- `c2` canonical **notes_v2.txt**, members: notes_v1.txt, notes_v2.txt
- `c3` canonical **unrelated.md**, single member

`metadata_conflicts: []`, `degraded: []`, and `uncertainty` contains the
mtime-is-weak-evidence note.

## 2. migrate_annotations.py → exit 0

stderr: `migrate_annotations: migrated=1, native=1, orphaned=1, shifted=1`

Per-annotation records (all keep `annotation_id`, source hash, target hash):

| annotation | status   | ratio  | target |
|------------|----------|--------|--------|
| a-001      | migrated | 1.0    | notes_v2.txt `ecb30f8b…5cd5`, page 1, chars [215, 303) |
| a-002      | shifted  | 0.7544 | notes_v2.txt, page 1, chars [406, 463), with `uncertainty` |
| a-003      | orphaned | 0.3867 | `target: null`, note: kept on source version, remains searchable |
| a-004      | native   | 1.0    | notes_v2.txt, page 1, chars [402, 462) |

## 3. merge_plan.py → exit 0

stderr: `merge_plan: 3 clusters, 3 items need human review, fully_automatic=False`

- Cluster `c2`: canonical `notes_v2.txt`, aliases `["notes_v1.txt"]`,
  counts `{migrated: 1, shifted: 1, orphaned: 1, native: 1}`.
- Conflict queue (one entry): canonical page 1, region 0 ([0, 500)),
  overlap span [402, 463) — **a-002** (from notes_v1.txt, "provenance over
  volume") vs **a-004** (from notes_v2.txt, "disagree: volume is what
  enables recall"); grouped for human review, no auto-resolution.
- `requires_human_review`: 3 entries — conflict [a-002, a-004],
  orphaned [a-003], shifted [a-002]. `fully_automatic: false`.
- `read_only`: ["downloads/report.pdf", "report.pdf", "report_copy.pdf"].
- Cluster `c1` (the report trio) carries no annotations; `c3` none either.

## Hand-checks (verified manually against the fixture text)

1. **a-001 lands on the right v2 sentence.** Slice 215–303 of the normalized
   `texts/notes_v2.txt/page-001.txt` equals the anchored text verbatim:
   "version drift causes annotations to scatter across duplicate downloads
   of the same paper" — paragraph C, which moved from position 3 (v1) to
   position 2 (v2); the offset shift is exactly what migration must catch.
2. **a-002 is flagged, not silently placed.** Its best v2 window [406, 463)
   is "tation provenance clearly matters more than sheer volume." — the
   reworded sentence; ratio 0.7544 ∈ [0.7, 0.9) → `shifted` + uncertainty.
3. **a-003 stays orphaned.** Paragraph D was deleted in v2; best ratio
   0.3867 < 0.7; record keeps source file/hash and explains why.
4. **Duplicate trio flagged by bytes.** report.pdf ↔ downloads/report.pdf is
   `byte_duplicate` (same name), both ↔ report_copy.pdf are `renamed_copy`;
   no text similarity was needed or consulted (the report page text exists
   only for realism).

## Negative tests (all run for real)

1. **Nowhere-text probe.** Appended `a-999` with anchored text "Zebra
   quantum waffles orbit the mahogany telescope nightly." → status
   `orphaned`, ratio 0.3898, exit 0. Nothing fabricated.
2. **Missing page texts.** Deleted `texts/notes_v2.txt/` →
   version_graph exits **3** with a `similarity_unavailable` metadata
   conflict and a `degraded` entry; no `version_of` edge is invented, so
   migrate treats both notes files as standalone (all `native`, exit 0).
3. **Bad inputs.** Nonexistent `--manifest` → exit **2**. A non-JSON line in
   annotations.jsonl → exit **2**. A record missing required keys →
   `status: "error"` record, migrate exits **3**, merge_plan propagates and
   exits **3** with an `error` entry in `requires_human_review`.
4. **Determinism.** Full pipeline run twice in a fresh directory;
   `version_graph.json`, `migration_report.jsonl` and `merge_plan.json` are
   byte-identical across runs (`cmp` clean).
