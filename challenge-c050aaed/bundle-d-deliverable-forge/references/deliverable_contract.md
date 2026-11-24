# Deliverable contract — what a reviewer can rely on

Deliverable-forge turns typed note drafts into inspectable, evidence-linked
artifacts. This file states what a reviewer should be able to do with the
output and what each mechanism guarantees.

## 1. Independent re-verification

A reviewer can re-run the evidence-chain gate at any time and must get the
same result:

```
python3 scripts/verify_claims.py --notes notes.jsonl \
    --sources-dir sources/ --out claims_report.rerun.json
```

- Exit code 0 means every claim's quote provably occurs (after Unicode NFKC +
  whitespace-collapse normalization) at the cited page of the cited file.
- Exit code 3 lists every offending `note_id` with its status
  (`file_missing` / `page_missing` / `quote_not_found`).
- The pipeline is deterministic: no wall-clock values enter any output, note
  order follows input order, so a re-run on unchanged inputs yields identical
  bytes (and identical sha256 values in `manifest.json`).

## 2. Human inspection

- `notebook.md` — grouped by note type (problem / method / result /
  reusable_point / doubt). Each note shows the claim first, then the verbatim
  evidence quotes as block quotes, each closed by a source locator line
  `file — p.N — annotation_id` (or `direct` for agent-supplied locators),
  plus tags and the verification status. A header block records provenance:
  per-page sha256 hashes from `sources/<filekey>/source.json` when present,
  the tool version, and the aggregate verification rate.
- `index.html` — fully standalone (inline CSS, no external resources, works
  offline from `file://`). A verification summary table links every row to a
  clickable per-note anchor (`#note-<note_id>`), so a reviewer can click any
  claim and jump to it.
- `manifest.json` — sha256 and byte count of each deliverable file, so a
  reviewer can detect any later tampering or drift.

## 3. Human-edit retention (snapshots and diffs)

Manual edits to the rendered deliverables are legitimate (a human fixes a
typo, reorders a section) but must stay auditable:

```
python3 scripts/render_deliverables.py --out-dir deliverables --snapshot before-edit
# ... human edits deliverables/notebook.md by hand ...
python3 scripts/render_deliverables.py --out-dir deliverables --snapshot after-edit
python3 scripts/render_deliverables.py --out-dir deliverables \
    --diff before-edit after-edit
```

- `--snapshot LABEL` copies the current `notebook.md` and `index.html` into
  `change_records/<LABEL>/`. Labels are restricted to `[A-Za-z0-9._-]`.
- `--diff LABEL1 LABEL2` writes `difflib.unified_diff` output for every
  snapshotted text file into `change_records/diff-<L1>-to-<L2>.diff`; if
  nothing changed, a marker file saying so is written instead.
- `change_records/` therefore contains the full audit trail of human/manual
  edits without touching the machine-generated deliverables.

## 4. The `excerpt_only` warning

`compose_notes.py` flags a note with `excerpt_only` when the claim is
identical to one of its evidence quotes (after normalization). The note is
still accepted — this is a warning, not a rejection — but it means the note
is a pure excerpt and carries no intellectual work: it adds nothing over the
annotation itself.

**Rewrite the note when you see this warning.** A good claim interprets,
connects, or questions the quote in the agent's own words; the quote stays in
`evidence` as proof. The intellectual content of notes always comes from the
agent reading the material — the scripts only validate, verify, and render.

## 5. What the scripts do NOT guarantee

- They do not check that a claim is a *faithful interpretation* of the quote,
  only that the quote exists where cited. Reviewers must still read.
- They do not extract annotations, migrate annotation formats, or index
  content for retrieval. Companion fields in `annotations.jsonl` (e.g. a
  migration marker) are passed through untouched, never reinterpreted.
