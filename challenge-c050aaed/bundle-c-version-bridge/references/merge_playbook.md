# Merge playbook — version-bridge

Policies for consolidating a multi-version library onto canonical documents
without losing or mixing annotations. The scripts enforce these policies;
this file explains them and the judgment calls around them.

## 1. Never delete input files

Non-canonical members of a cluster become **aliases**, recorded in
`merge_plan.json` under `aliases` with the alias policy string. Nothing is
deleted, moved, renamed or overwritten — not even byte-identical duplicates.
Rationale: the evaluator's case rules, other skills, or the reader's own file
organizing habits may depend on those paths; aliasing is fully reversible,
deletion is not. Files the case marks untouchable are additionally listed
verbatim in `read_only` (pass them with `--read-only`).

## 2. mtime is weak version evidence

`version_of` edges are directed older→newer by mtime, and the canonical
member is chosen by newest mtime (ties: shortest relpath, then lexicographic
order). But copies, re-downloads, syncs and `git checkout` all rewrite mtime.
Therefore:

- Every graph output repeats the mtime caveat under `uncertainty`.
- When `task.md` or the case materials contain **explicit version notes**
  (e.g. "v3 is the final draft", "use the March revision"), those notes win
  over mtime. If the notes contradict the graph's canonical choice, keep the
  graph output as machine evidence, but state the override in `result.json`
  (`change_records` entry + `uncertainty` entry) and, if you regenerate the
  graph, adjust the manifest mtimes to match the case's stated order —
  recording that you did so.
- If the case's version notes are ambiguous, do not guess: flag the cluster
  in `requires_human_review` territory by reporting the ambiguity in
  `result.json`'s `uncertainty`.

## 3. Administrative version notes in task.md

Read `task.md` before finalizing `merge_plan.json`. Extract any statements
about versions, authority ("final", "approved", "superseded") or files that
must not be touched. Cross-check them against the graph; conflicts between
administrative notes and computed evidence are exactly the kind of thing to
surface, not to silently resolve.

## 4. Conflict handling — group, never auto-resolve

Two annotations conflict when they come from **different versions**, their
anchored text lands on **overlapping character spans of the same canonical
page region** (500-char buckets), and their `contents` disagree. The merge
plan groups such annotations into the cluster's `conflict_queue` with both
bodies quoted, and lists them in `requires_human_review`. The tool never
picks a winner, never merges the two into one record, and never edits
`contents`. Same-version duplicates and identical contents are not
conflicts.

`shifted` and `orphaned` annotations also appear in `requires_human_review`
because their placement is uncertain (ratio in [0.7, 0.9)) or absent
(ratio < 0.7). Only when `requires_human_review` is empty is the plan marked
`fully_automatic: true`.

## 5. Orphaned annotations stay searchable on their original version

An orphaned annotation is NOT dropped. Its migration record keeps
`status: "orphaned"`, the full `source` block (file, file_sha256, page), the
best ratio found, and a note explaining why it did not migrate. Because the
source file is only aliased — never deleted (§1) — the annotation remains
valid and searchable against the original version's page texts under
`texts/<filekey>/page-NNN.txt`. Any downstream system should index orphaned
annotations against their **source** version, not the canonical one, and
surface them for manual re-anchoring.

## 6. Honesty rules

- Unknown similarity is reported as unknown (`similarity_unavailable`),
  never guessed; missing page texts degrade the run (exit 3) rather than
  fabricate an edge.
- Every output is deterministic: stable sorts, ratios rounded to 4 decimals,
  no wall-clock timestamps. Re-running on identical inputs yields identical
  bytes.
- Skips (e.g. no annotations provided), failures, conflicts and recoveries
  belong in `result.json`'s `change_records` with the matching `status`.
