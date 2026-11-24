---
name: citation-coverage-auditor
description: >
  Audit citation coverage and bibliography metadata for scientific
  introduction / related-work writing. Use when asked to: check citation
  coverage, verify bibliography metadata, reconcile references.json with its
  readable rendering, fix Vancouver numbering by first appearance, audit
  claim-citation correspondence, find orphan citations or decorative citation
  clusters, or confirm that closest/representative/recent works and mandated
  topics are cited. Chinese triggers: 补引用 (add missing citations),
  核对引用 (check citations), 检查引用覆盖, 核对参考文献元数据, 温哥华编号检查.
license: CC0-1.0
---

# Citation Coverage Auditor

## Purpose

This skill audits the **citation layer** of a manuscript Introduction /
Related Work section against the materials the task actually provides. Its
center of gravity is citation coverage and metadata verification:

1. **Traceability** — every cited work must resolve to an entry of the
   *provided* bibliography, and the structured (`references.json`) and
   human-readable (`references.md`) representations of that bibliography must
   carry consistent metadata (authors, year, title, journal, DOI, abstract).
2. **Vancouver numbering** — citations are numbered strictly by first
   appearance; the bibliography list order equals the citation order.
3. **Coverage** — the draft cites the closest works (same problem setting),
   representative works per route, and recent progress; it covers every topic
   the case mandates and meets `min_distinct_citations` with genuinely
   relevant works, never by decoration.
4. **Claim-to-citation correspondence** — every `[n]` marker is bound to a
   specific claim recorded in `facts_and_sources`; there are no orphan
   citations, no unsupported citation clusters, and no claim records
   disconnected from the draft.

The skill ships four stdlib-only Python scripts that do the mechanical
checking, plus doctrine (this file and `references/`) that governs the
semantic judgments the scripts can only flag.

## When to use

- **Drafting** — while writing the introduction/related work, to keep the
  citation layer consistent as sentences move around.
- **Revision** — after any edit that adds, deletes, or reorders sentences
  (numbering by first appearance breaks silently when text moves).
- **Pre-submission audit** — as the final gate before delivering
  `result.json`: one full pass of all four scripts plus the semantic review
  of everything they flag.

## Audit workflow

Run the steps in this order. Each script is cheap; iterate freely.

### Step 1 — Parse and reconcile the bibliography

```bash
python3 <skill-dir>/scripts/bib_parse.py \
  --json /input/material/references.json \
  --md   /input/material/references.md \
  --out-dir /app/work/audit
```

Produces `/app/work/audit/bib.json` (normalized entries with `key`, `number`,
`authors`, `year`, `title`, `journal`, `doi`, `abstract`, `evidence_level`)
plus `xcheck_report.json` / `xcheck_report.md`. Every disagreement between
the two representations (missing field, value mismatch, extra md entry,
ordering difference) is reported — never silently fixed. Read the report and
route each disagreement to `open_items` (see Exception handling).

### Step 2 — Draft with claim records

Write the introduction following the coverage doctrine below. While writing,
record **every statement about another work** as a claim object in the
`facts_and_sources` shape: `{id, section, text, type, refs[], quote,
source_span, stance, confidence}`. The claim `text` must match the draft
sentence (whitespace-normalized), and `refs` must list exactly the works the
sentence's markers point at. A statement about prior work without a claim
record is an orphan waiting to be caught in Step 5.

### Step 3 — Numbering check

```bash
python3 <skill-dir>/scripts/numbering_check.py \
  --bib   /app/work/audit/bib.json \
  --draft /app/work/draft/introduction.md \
  --out   /app/work/audit/numbering_report.json
```

Reports first-appearance violations, markers with no bibliography entry,
uncited bibliography entries, and duplicate-definition risks. Exit 1 means
violations. To repair:

```bash
python3 <skill-dir>/scripts/numbering_check.py \
  --bib   /app/work/audit/bib.json \
  --draft /app/work/draft/introduction.md \
  --out   /app/work/audit/numbering_report.json \
  --fix \
  --out-draft /app/work/draft/introduction.renumbered.md \
  --out-bib   /app/work/audit/references_renumbered.md
```

The fixer rewrites citation **markers only, never the prose**, rewrites the
bibliography in citation order, and emits a change record
(`<out-draft stem>.changes.json`: old→new mapping, count of edited markers).
After a fix, adopt the renumbered bibliography order in `bib.json`
(re-run `bib_parse.py` or reorder entries accordingly) before re-running the
later steps.

### Step 4 — Coverage ledger

```bash
python3 <skill-dir>/scripts/coverage_ledger.py \
  --case  /input/case.json \
  --bib   /app/work/audit/bib.json \
  --draft /app/work/draft/introduction.md \
  --out-dir /app/work/audit
```

Produces `coverage_ledger.json` and a readable `coverage_ledger.md` with a
coverage checklist table: cited vs uncited refs; distinct count vs
`constraints.min_distinct_citations`; each `must_cover_topics` phrase mapped
to cited refs by content-word overlap; a recency histogram (flagging ignored
recent entries); a closest-work ranking against the problem statement in the
manuscript facts (flagging any uncited top-2 closest ref); and a
decorative-citation lint (tail refs cited exactly once inside a 3+ marker
cluster with no sentence-level role — heuristic warning). Hard failures
(exit 1): minimum not met, mandated topic uncovered, top-2 closest work
uncited. Treat every flagged item as a *prompt for a semantic decision*:
read the reference's provided text and decide whether it genuinely belongs
in the draft.

### Step 5 — Claim-citation correspondence

```bash
python3 <skill-dir>/scripts/claimcite_check.py \
  --draft  /app/work/draft/introduction.md \
  --claims /app/work/draft/claims.json \
  --bib    /app/work/audit/bib.json \
  --out    /app/work/audit/claimcite_report.json
```

Verifies: every prior-work claim has ≥1 ref; every ref key used in claims
exists in `bib.json` and is actually cited in the draft; every `[n]` marker
sits in a sentence whose text appears (whitespace-normalized substring,
truncation tolerated) in some claim listing that ref. Orphans are reported
in both directions. Exit 1 on any hard failure.

### Step 6 — Fix from sources, re-run once

Fix findings **from the provided sources only**: add citations for
genuinely relevant uncovered works, remove decorative ones, repair claim
records, apply `--fix` renumbering if order changed. Then re-run the full
pipeline **once** to confirm everything is green. One audit pass plus one
fix pass is normally enough — the scripts are cheap; spend model effort on
the semantic judgments the scripts flag (is this ref really the closest
work? does this sentence really need this citation?), not on re-running.

## Runtime contract

- **Inputs**: read `/input/case.json` and `/input/task.md`; material paths
  inside `case.json` (`material.*`) are relative to the case directory.
- **Workspace**: do all intermediate work under `/app/work` (audit reports,
  renumbered drafts, ledgers).
- **Deliverables**: write the deliverables named in `case.json` (for the
  synthetic demo: `introduction`, `related_work`, `claim_citation_table`,
  `gap_chain`, `contribution_map`, `result_json`) plus `result.json` under
  `/app/output`.
- **result.json**: copy `case_id` **verbatim** from the input, and populate
  **every field of the case's own `output_contract` with the correct
  types** — for the demo contract: `case_id` (str), `target_artifact`
  (object with `path`, `format`, `sections[]`, `word_counts{}`),
  `facts_and_sources` (array of claim objects with `id`, `section`, `text`,
  `type`, `refs[]`, `quote`, `source_span`, `stance`, `confidence`),
  `version_and_boundary` (object with `changes[]`, `open_items[]`,
  `material_gaps[]`, `status`), `verification` (object with `checks[]` and
  pass/fail/not_verifiable counts — list each script run, its exit code,
  and the report artifact path), and `status`.
- **Honest status**: `status` is `complete` only if every check passes and
  all deliverables exist; `partial` if deliverables exist but findings
  remain or some check could not run; `blocked` if a required input is
  missing (see below). Enumerate every limitation, skipped check, and open
  disagreement in `version_and_boundary.open_items` /
  `version_and_boundary.material_gaps`.
- **Save partial early**: after each workflow step, persist what exists
  (draft, claims, audit reports, a provisional `result.json`) so an
  interrupted run still yields an honest `partial`.

## Budget note

One audit pass + one fix pass is the normal budget. All four scripts run in
well under a second on case-sized inputs. Do not loop the scripts; loop the
*thinking* about their findings instead.

## Exception handling

- **`references.json` missing but `references.md` present**: run
  `bib_parse.py --md references.md --out-dir DIR` (no `--json`); it parses
  the md alone, keys entries `ref01...` in md order, and marks each entry's
  `evidence_level` from the md (`abstract` if an abstract line exists, else
  `title-only`). No cross-check is possible in this mode — record the
  missing structured file in `material_gaps` and downgrade `status` to
  `partial` unless everything else is verifiable.
- **Reference without an abstract**: mark `evidence_level: "title-only"`
  and **never attribute findings, numbers, or methods to it** — you may
  cite it only for what its title/venue establish (existence and topic of
  the route). `bib_parse.py` sets this field; the coverage ledger and your
  writing must respect it.
- **Disagreement between the two representations**: report it (Step 1 does),
  copy it into `open_items`, and do **not** auto-resolve. Do not guess which
  side is right; do not invent corrected DOIs, years, or author lists.
- **Empty bibliography** (zero entries): the task cannot be cited-writing at
  all — set `status: "blocked"` with the explicit reason
  ("bibliography contains zero entries; Vancouver citation impossible"),
  and stop after emitting the partial artifacts.
- **Markers pointing outside the bibliography** (`[7]` with 6 entries):
  hard failure; `--fix` refuses to renumber them (exit 1). Find which
  provided work was meant, from the sentence content and the claim records.

## Limitations

- **Coverage heuristics are lexical.** Topic mapping, closest-work ranking,
  and the decorative lint use content-word overlap. They flag candidates and
  suspicious patterns; the writer must confirm semantic relevance by reading
  the provided reference texts. A lexical "covered" is not a semantic
  "covered", and a lexical "gap" may be a vocabulary mismatch.
- **Metadata cross-check is internal only.** It compares the two *provided*
  representations against each other. It does **not** verify DOIs, years, or
  author lists against external databases, and it must never be used to
  "correct" the provided metadata from outside knowledge.
- **The numbering fixer rewrites markers only, never the prose.** It cannot
  know whether a sentence *should* cite a work; it only makes the numbers
  consistent with first appearance.
- Sentence segmentation is heuristic (robust to decimals like `0.55`, not to
  arbitrary abbreviations); claim matching is whitespace-normalized
  substring, so heavily paraphrased claim records will be flagged for
  manual review.

## Coverage doctrine (intellectual core)

1. **Cover the closest works first.** Identify the works that share the
   manuscript's problem setting (the ledger ranks them against the problem
   statement). Any top-2 closest work left uncited is a hard failure — the
   reviewers will know these works and will look for them first.
2. **Then representative works per route.** Each method family or route that
   the field recognizes (and that the bibliography instantiates) should be
   represented by at least one cited work, cited for what it actually
   establishes.
3. **Then recent progress.** Check the recency histogram; ignoring the most
   recent bibliography entries signals a stale related-work section. Cite
   them where they genuinely play a role.
4. **Meet topic mandates and minimum counts with genuinely relevant works.**
   `min_distinct_citations` is a floor on *relevant* citations, never a
   quota to fill by decoration. A citation added only to inflate the count
   is exactly what the decorative lint looks for.
5. **Every citation plays a role in its sentence.** A marker is justified
   when the sentence states something the cited work establishes (a method,
   a result, a limitation, a classification). If removing the marker loses
   no information, remove the marker.
6. **Every claim about another work carries its citation in the same
   sentence and a claim record in `facts_and_sources`.** No orphan
   citations (marker without claim record), no unsupported clusters
   (3+ markers whose works are not named or characterized in the sentence),
   no claim records disconnected from the draft.
7. **Numbering strictly by first appearance.** The first work cited is
   `[1]`, the bibliography is in citation order, and any reordering of the
   text triggers a re-check (Step 3) and, if needed, a `--fix` pass.
8. **Metadata as provided.** Report conflicts between representations;
   never guess DOIs, years, author lists, or abstracts, and never import
   metadata from outside the provided material.

## Bundled example

`examples/` contains a fully synthetic demonstration: an invented manuscript
("PermaLig") with six invented references, a filled draft
(`examples/synthetic-case/filled/introduction.md`), its claim records
(`filled/claims.json`), a driver script (`run_example.sh`), and the real
outputs of running it (`sample-output/`). **It is a SYNTHETIC EXAMPLE that
demonstrates the interface only.** Never treat its content as real science,
and never submit these precomputed answers (or anything derived from them)
as results for the organizers' fixed cases — for a real case, run the
workflow on that case's own material.
