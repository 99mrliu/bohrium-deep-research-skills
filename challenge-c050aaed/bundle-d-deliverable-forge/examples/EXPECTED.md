# EXPECTED — real observed outputs

All outputs below were **actually observed** by running the commands from
README.md with local `python3` (Python 3.12.14, macOS arm64) against the
fixtures in this directory. No output was hand-written. The pipeline is
deterministic (no wall-clock in outputs), so re-running reproduces these
numbers byte-for-byte.

## 1. Compose, all 6 drafts (README step 1) — exit 0

```
compose_notes deliverable-forge 1.0.0
drafts: 6  valid: 6  invalid: 0
notes per type: problem=1 method=1 result=2 reusable_point=1 doubt=1
evidence items: 7 (annotation-linked: 5, direct: 2)
annotations referenced: 5 / 5
annotation -> notes:
  ann-001 -> n-problem-1
  ann-002 -> n-method-1
  ann-003 -> n-result-1
  ann-004 -> n-reusable-1
  ann-005 -> n-doubt-1
warnings: 0
wrote: notes_all.jsonl (6 notes)
exit=0
```

The bad draft `n-bad-1` passes compose: its direct locator is structurally
valid. Its badness is semantic (quote not on the cited page), which is
exactly what the verify gate is for.

## 2. Verify, all 6 drafts — exit 3, names n-bad-1

```
verify_claims deliverable-forge 1.0.0
claims: 7  verified: 6  unverified: 1  verified_rate: 0.8571
wrote: claims_all.json
exit=3
stderr:
UNVERIFIED note n-bad-1: quote_not_found (demo_paper p.2 ann=None) quote='the control group scored 99 percent on every test...'
evidence-chain gate FAILED: fix or remove unverified claims.
```

claims_all.json totals: `total_claims=7, verified=6, unverified=1,
verified_rate=0.8571, all_verified=false`.

## 3. Valid-only pipeline (README step 2) — exit 0 / exit 0

`head -n 5 drafts.jsonl > drafts_valid.jsonl`, then:

```
compose_notes: drafts: 5  valid: 5  invalid: 0
notes per type: problem=1 method=1 result=1 reusable_point=1 doubt=1
evidence items: 6 (annotation-linked: 5, direct: 1)
annotations referenced: 5 / 5
warnings: 0
exit=0
```

```
verify_claims: claims: 6  verified: 6  unverified: 0  verified_rate: 1.0
evidence-chain gate PASSED.
exit=0
```

## 4. Render (README step 3) — exit 0

```
render_deliverables deliverable-forge 1.0.0
notes rendered: 5
  index.html: 5765 bytes sha256=da871da89373ab97…
  notebook.md: 2523 bytes sha256=e9dff3ccee776873…
  manifest.json written
exit=0
```

Rendered file list in the output dir:

```
index.html      5765 bytes
manifest.json    348 bytes
notebook.md     2523 bytes
```

notebook.md (77 lines) contains: the synthetic-example banner, a Provenance
block with the per-page sha256 from `source.json`, five sections in fixed
order (Problems / Methods / Results / Reusable points / Doubts), each note
with claim, tags, `status: verified`, and quote blocks closed by locators
such as `— demo_paper — p.2 — ann-003` (or `— direct`). index.html is
fully standalone (single `<style>` block, zero external URLs), with a
verification summary table (`6/6 verified`) and `#note-<note_id>` anchors.
manifest.json sha256 values (full):

```
index.html   da871da89373ab9773bf8330dbd0f4c85308d35f1c630105ff4859e258b06fec
notebook.md  e9dff3ccee77687351dd12886ad004e1497c370c6fada3655826e0c88c396c77
```

Re-rendering into a second directory produced byte-identical notebook.md and
index.html (sha256 equal), confirming determinism.

## 5. Snapshot / human edit / diff cycle (README step 4)

```
snapshot 'before-edit' saved: notebook.md, index.html -> deliverables/change_records/before-edit   exit=0
# hand edit: one line in notebook.md changed
#   - tags: provenance, honesty
#   + tags: provenance, honesty, human-edited
snapshot 'after-edit' saved: notebook.md, index.html -> deliverables/change_records/after-edit    exit=0
diff written: deliverables/change_records/diff-before-edit-to-after-edit.diff (11 lines)          exit=0
```

The recorded diff file, verbatim:

```diff
--- before-edit/notebook.md
+++ after-edit/notebook.md
@@ -69,7 +69,7 @@
 ### n-doubt-1 (doubt)

 - **claim**: These figures are synthetic fixtures and must never be cited as empirical findings; provenance has to travel with the note.
-- tags: provenance, honesty
+- tags: provenance, honesty, human-edited
 - status: verified

 > these numbers are invented fixtures for tooling tests
```

change_records/ afterwards contains `before-edit/`, `after-edit/` (each with
notebook.md + index.html) and the `.diff` file. Diffing a snapshot against
itself writes the marker `# no differences between snapshots ...` (exit 0).

## 6. Negative tests (all observed)

| # | Test | Observed |
|---|------|----------|
| N1 | Draft with `note_type: "summary"` + empty evidence | compose exit 3; stderr: `INVALID n-invalid: note_type 'summary' not in [...]` and `INVALID n-invalid: evidence must be a non-empty list`; notes.jsonl NOT written |
| N2 | Claim identical to its quote | compose exit 0 with `warnings: 1` / `WARNING n-excerpt: excerpt_only: claim is identical to its quote; rewrite the claim in your own words` |
| N3 | verify with missing `--sources-dir` | exit 2, `verify_claims: ERROR: sources dir not found: no_such_dir` |
| N4 | `--diff` with unknown snapshot label | exit 2, `snapshot 'no-such-label' not found` |
| N6 | Direct locator citing page 9 (does not exist) | verify exit 3, status `page_missing`, `verified_rate: 0.0` |

`--help` on all three scripts exits 0.
