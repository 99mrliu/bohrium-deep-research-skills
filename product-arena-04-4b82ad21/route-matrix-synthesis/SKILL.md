---
name: route-matrix-synthesis
description: >-
  Write the Related Work passage and research gap of a manuscript
  introduction by first building a route-grouped comparison matrix of prior
  works and then deriving the gap from the matrix's documented limitations.
  Trigger phrases: write or organize related work, derive the research gap,
  compare prior methods on shared axes, introduction writing, related-work
  matrix, counterexample-scoped gap.
---

# route-matrix-synthesis

Turn a pile of prior-work references into (1) a **comparison matrix** —
references grouped by method route and compared on shared axes — and
(2) a **Related Work + research gap** draft whose every gap sentence is
derivable from a documented limitation in that matrix. Three stdlib-only
scripts scaffold the matrix, lint the filled matrix, and check the draft's
gap chain; the model's effort goes into reading sources, filling cells with
verbatim quotes, and writing the prose.

## Purpose

Reviewers reject introductions whose related work is a chronology of papers
and whose gap is "this topic is important". This skill enforces the
stronger pattern:

- prior work is **grouped by method route / problem setting**, not by year;
- routes are **compared on shared axes** (problem setting, inputs required,
  scoring/integration stage, evaluation setting, stated limitation);
- each route gets **one decisive comparative sentence**: shared task +
  meaningful distinction + consequence under this manuscript's conditions;
- the **gap is derived from the limitation column** of the matrix and
  **survives the strongest counterexample** (the nearest alternative's
  strongest relevant capability is stated and scoped before the gap is
  claimed);
- **each contribution maps to an available anchor** (figure/section) and to
  the gap it closes.

## When to use

- Writing the Introduction / Related Work of a methods manuscript from a
  fixed bibliography and a fact base (the competition's standard setup).
- Reorganizing an existing related-work draft that reads paper-by-paper.
- Auditing whether a draft's gap paragraph is actually supported by the
  cited works' stated limitations.

## When NOT to use

- No bibliography is provided (nothing to matrix; request material or
  degrade to a background-only draft and report blocked).
- The task is a full systematic review or survey (this skill produces one
  introduction-scale passage, not a review article).
- References arrive as bare titles with prose-claim expectations: the skill
  refuses to attribute findings to title-only references, so if most of the
  bibliography is title-only, expect a partial deliverable.
- Copy-editing, citation-formatting-only, or non-comparative writing tasks.

## Inputs and runtime contract

Read at start:

- `/input/case.json` — case descriptor. Honor `constraints`
  (word budgets, citation style, required sections, `available_anchors`,
  `must_cover_topics`, `min_distinct_citations`) and mirror
  `output_contract` exactly in your `result.json`.
- `/input/task.md` — the task statement.

Work area: `/app/work` — all intermediates (scaffolds, filled matrix,
drafts, lint reports) go here. **Save an editable partial draft early**
(after phase 2) and keep updating it, so an interruption still leaves a
usable artifact.

Final deliverables: `/app/output` — the introduction/related-work artifact
plus `result.json`. `result.json` MUST contain:

- `case_id` — copied verbatim from the input case;
- every field named in the case's own `output_contract`, mirrored with the
  declared types (e.g. `target_artifact` object with `path`, `format`,
  `sections[]`, `word_counts{}`; `facts_and_sources` array of claim
  objects; `version_and_boundary` object with `changes[]`, `open_items[]`,
  `material_gaps[]`, `status`; `verification` object with check results);
- `status` — one of `complete | partial | blocked`. Use `partial` whenever
  any check failed, any reference could not be classified or verified, or
  any constraint could not be honored, and state the concrete limits in
  `open_items` / `material_gaps`. Never claim `complete` over unverified
  material.

## Budget awareness (64 model requests / 900 s / 16384 tokens per response)

- Run the scripts for everything mechanical: route classification, matrix
  scaffolding, closeness ranking, quote verification, gap checking. Do not
  re-derive by hand what a script emits.
- Spend model requests on: reading the bibliography and fact base (once,
  carefully), filling matrix cells with verbatim quotes, and writing the
  prose. A typical budget: 1 request to read materials, 1–2 to fill the
  matrix, 1–2 to draft, 1 per lint-fix round.
- Keep each response under the token cap: fill `matrix.json` in chunks if
  the bibliography is large, and never paste whole reference lists into a
  response more than once.
- Run all linters before the final answer; a failed lint fixed from the
  sources is far cheaper than a rejected deliverable.

## Method — four phases

### Phase 1 — Read the case and materials

1. Read `/input/case.json` and `/input/task.md`. Extract: constraints,
   `available_anchors`, required sections, the output contract.
2. Read the manuscript fact base and the full bibliography. Note which
   references have abstracts and which are title-only.
3. Copy the materials into `/app/work` and record any missing pieces as
   open items immediately.

### Phase 2 — Build and fill the comparison matrix

Scaffold with the script (do not hand-build JSON):

```bash
python3 <skill-dir>/scripts/build_matrix.py \
  --case /app/work/case.json \
  --bib /app/work/references.json \
  --facts /app/work/manuscript-facts.md \
  --route-keywords <skill-dir>/references/route_keywords.json \
  --out-dir /app/work/matrix
```

This writes `matrix.json` (scaffold) and `matrix.md` (editable table). It
classifies each reference into routes by keyword rules, ranks references by
closeness to the manuscript's problem terms, and marks the top ones as
closest-alternative candidates. **Verify every route assignment against the
source text** — the classification is a keyword heuristic; merge, split or
rename routes where the science demands it, and edit
`route_keywords.json` if a whole family is missed.

Then fill the cells (the core intellectual work):

- For every reference, fill the six axes: `problem_setting`,
  `inputs_required`, `scoring_or_integration_stage`, `evaluation_setting`,
  `stated_limitation`, `decisive_comparison`. See
  `<skill-dir>/references/comparison_axes.md` for per-axis guidance.
- **Every filled cell carries a verbatim quote** copied from the
  reference's provided text plus a location label (`abstract`, `title`).
  The linter checks quotes as whitespace-normalized substrings — paraphrase
  goes in `text`, never in `quote`.
- `stated_limitation` is sacred: only limitations documented in the
  provided text. If none is stated, write "none stated in provided text".
- `decisive_comparison`: shared task + meaningful distinction + consequence
  under this manuscript's conditions; at least one filled per route.
- Title-only references: no attributed findings; fill at most what the
  title supports.
- Set each reference's `citation_number` once your draft's Vancouver
  numbering (by first appearance) is fixed — `gap_check.py` uses it.

### Phase 3 — Draft the related work and the gap

Structure (respect the case's word budgets and required sections):

1. **Background** — frame the problem from the fact base only.
2. **Related work, route by route** — for each route, compare its members
   on the shared axes and close with the route's decisive comparative
   sentence. Cite Vancouver-style, numbered by first appearance, only from
   the provided bibliography. Cover the case's `must_cover_topics`.
3. **Gap paragraph** — under a heading containing "gap". Follow the
   four-link chain in `<skill-dir>/references/gap_patterns.md`:
   source-supported prior capability → specific remaining requirement →
   why it changes the outcome under this manuscript's conditions → own
   mechanism with actual evidence. Every gap sentence must be derivable
   from a `stated_limitation` cell. **Scope the strongest counterexample**
   (start from the matrix's closest-alternative candidates): state its
   strongest relevant capability, cite it, then bound it with its own
   stated limitation before claiming the gap.
4. **Contributions** — bullets under a heading containing "contribution";
   each bullet closes part of the gap and ends with an anchor from
   `constraints.available_anchors` (e.g. "Fig 1"). No anchor, no
   contribution.

Draft conventions the checker relies on: section headings containing
"gap" and "contribution"; gap as prose sentences (not bullets);
contributions as bullets.

Writing doctrine (non-negotiable):

- Never attribute findings to a title-only reference.
- No invented numbers, datasets, benchmarks or results — if the material
  does not state it, it goes to `open_items`, not into the prose.
- Every statement about another work traces to that work's provided text
  via a matrix quote.
- The gap never rests on "the topic is important"; it rests on documented
  limitations.

### Phase 4 — Lint, fix from sources, deliver

```bash
python3 <skill-dir>/scripts/matrix_lint.py \
  --matrix /app/work/matrix/filled_matrix.json \
  --bib /app/work/references.json \
  --out /app/work/matrix/lint_report.json

python3 <skill-dir>/scripts/gap_check.py \
  --case /app/work/case.json \
  --matrix /app/work/matrix/filled_matrix.json \
  --draft /app/work/drafts/introduction.md \
  --out /app/work/drafts/gap_report.json
```

- Exit 0 = pass, 1 = findings, 2 = usage/IO error. Treat every exit-1
  finding as a must-fix: repair quotes and claims **from the source
  texts**, never by weakening the check or deleting the offending cell
  (unless the cell was itself unsupported).
- Iterate until both pass, or until the remaining findings are documented
  as open items with `status: partial`.
- Copy final artifacts to `/app/output` and write `result.json` per the
  contract above: mirror every `output_contract` field with correct types,
  include the lint reports under `verification`, and state partial limits
  honestly.

## Script reference

All scripts are pure Python 3.9+ stdlib, argparse CLIs, explicit path
arguments (nothing is read from a hardcoded location). Exit codes:
`0` pass, `1` findings/fail, `2` usage or IO error.

| Script | Purpose |
|---|---|
| `<skill-dir>/scripts/build_matrix.py` | classify refs into routes, rank closeness, emit `matrix.json` + `matrix.md` scaffold |
| `<skill-dir>/scripts/matrix_lint.py` | verify completeness, per-route decisive comparisons, verbatim-quote fidelity |
| `<skill-dir>/scripts/gap_check.py` | verify gap←limitation derivability, counterexample scoping, contribution anchors, citation validity |

Supporting files: `<skill-dir>/references/route_keywords.json` (editable
route rules), `<skill-dir>/references/comparison_axes.md`,
`<skill-dir>/references/gap_patterns.md`.

## Exception handling

- **Empty bibliography** — `build_matrix.py` emits an empty matrix and a
  warning. Do not fabricate references; deliver background + planned
  contributions only, `status: partial`, open item "no bibliography
  provided".
- **References without abstracts** — they classify from the title, are
  marked `title-only`, and must receive no attributed findings. If the
  majority is title-only, say so in `material_gaps` and expect `partial`.
- **Unclassifiable references** — they land in the `unclassified` route.
  Read them by hand; either assign a real route (update the matrix and,
  if useful, `route_keywords.json`) or keep them unclassified with a note.
- **Missing constraints** (no `available_anchors`, no word budget) — note
  the absence in `open_items`, proceed with conservative defaults, and do
  not invent anchors.
- **Linter failures you cannot fix from sources** — keep the finding, mark
  `status: partial`, list it in `open_items`. Never silence a check by
  editing the scripts or deleting evidence.
- **Contradiction between task and materials** — follow the materials for
  facts, the task for form, and record the contradiction as an open item.

## Limitations

- Route classification is a **keyword heuristic**; the writer must verify
  and correct route assignments against the sources.
- The linters check **mechanical properties only**: quote fidelity,
  presence of comparisons, token overlap between gap and limitations,
  anchor presence, citation membership. They do **not** check semantic
  validity, whether a paraphrase is fair, or whether the prose is good.
- `gap_check.py`'s counterexample screen uses distinctive-token overlap;
  it can miss a conceptual counterexample phrased in different words and
  can flag a harmless one. Human judgement decides; the screen only
  guarantees the question gets asked.
- No check ever replaces reading the sources.

## Bundled examples are synthetic demonstrations

Everything under `<skill-dir>/examples/` is a **SYNTHETIC EXAMPLE**: the
PermaLig manuscript, its six references, all authors, journals, DOIs,
abstracts and numbers are invented to demonstrate the interface end to end.
They are **not** answers to the organizers' fixed cases. Precomputed or
bundled answers must never be submitted as solutions to a real case: for
every actual task, rebuild the matrix from that case's own materials and
write the prose fresh.
