---
name: graded-relevance-bench
description: Offline graded-relevance adjudication for source-bound literature retrieval. Turns a local candidate pool (organizer-provided Crossref/EuropePMC/OpenAlex JSON snapshots under /input, plus any raw responses the agent saves) into defensible 0-3 relevance grades against explicit conceptual facets — every grade carries a per-facet score decomposition with matched terms, hit fields and evidence snippets a human can re-verify point by point. Borderline records are never silently included or dropped — they go into borderline_queue.json with the exact question the adjudicating agent must answer, and the agent's final grades are applied via --adjudicate with a ledger (engine grade vs final grade, rationale) plus an honest engine-vs-adjudication nDCG@10 self-consistency number. A contract-driven builder fills result.json with the original case_id and every output_contract field. Use for 学术文献检索/literature-search cases scored on ranking quality (Precision@k, nDCG@k) and verifiable relevance judgments, where the pool is fixed local snapshots and every relevance call must be defensible.
---

# graded-relevance-bench — make every relevance grade inspectable

Philosophy: **in a source-bound evaluation, ranking quality is decided by the
quality of per-record relevance judgments, not by recall tricks.** A ranked
list that cannot explain *why* record X sits above record Y — which facet of
the research question it satisfies, on which field, with which evidence — is
indefensible under Precision@k / nDCG@k scrutiny. This skill makes every point
of every grade inspectable: the engine decomposes each 0-3 grade into per-facet
matched terms, hit fields (title/abstract), contributions and evidence
snippets, and it converts the genuinely hard calls into a small explicit
borderline queue for the agent instead of guessing.

The agent contributes judgment (authoring facets with synonyms, adjudicating
the borderline queue); the engine does all matching, grading, ranking and
accounting deterministically, offline, stdlib-only.

## Runtime contract

- Platform installs this skill at `/skills/weekly-skill` and runs fixed cases:
  input `/input/case.json` + `/input/task.md` (+ snapshot material), work under
  `/app/work`, deliverables under `/app/output`, including `result.json` with
  the original `case_id` and **every** field named by `output_contract`.
- First action in any run: `ls -R /input` and read `case.json` — note
  `case_id`, every `output_contract` field name, the research question, and
  what snapshot material actually exists.
- Save a partial `result.json` before grading; improve incrementally; keep
  `status=partial` whenever anything material is open (an unadjudicated
  borderline queue, an empty facet, a skipped snapshot).
- Budget: grading is one deterministic pass over the pool — cheap. Spend your
  effort on the two steps only an agent can do: facet authoring (step 3) and
  borderline adjudication (step 5). Do not re-run the engine to "tune" grades;
  change facets or adjudications, then re-run once.

## Procedure

1. **Secure a partial result immediately:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status partial
   ```

   (If the skill landed elsewhere, locate it with `ls /skills/*/scripts/`.)

2. **(Optional, only if platform search tools are available) widen the pool.**
   Save **raw, unmodified** JSON responses under `/app/work/corpus/`. The
   engine ingests them with the same normalization and dedup as organizer
   snapshots. Never hand-edit a response. If no search tools exist, skip —
   the organizer snapshots alone are a valid pool.

3. **Author facets (the highest-leverage step).** Read the research question
   and write `/app/work/facets.json` with 2-5 *conceptual* facets, each with
   terms **and synonyms**, e.g.:

   ```json
   {"facets": [
     {"name": "material", "terms": ["perovskite", "halide perovskite"]},
     {"name": "problem",  "terms": ["moisture", "humidity", "stability"]},
     {"name": "method",   "terms": ["passivation", "defect passivation"]}]}
   ```

   The engine matches literally — synonyms you do not write down do not exist.
   If you skip this step the engine falls back to one single-term facet per
   content word of the question and says so in the report; that fallback is a
   safety net, not a strategy.

4. **Run the grading engine:**

   ```
   python3 /skills/weekly-skill/scripts/grade_relevance.py \
       --case /input/case.json --input /input \
       --corpus /app/work/corpus --work /app/work --out /app/output
   ```

   It prints a one-line JSON digest: files consulted, records loaded, unique
   records, grade histogram, tier counts, `zero_hit_facets`, `borderline_count`.
   Exit 2 means the pool is empty — deliver partial with the digest in
   `uncertainty`.

5. **Adjudicate the borderline queue.** Open
   `/app/output/borderline_queue.json`. Each record lists its full
   decomposition, evidence snippets, and the *specific question* you must
   answer ("does term X in abstract satisfy facet Y for this research
   question?"). Read the abstracts, decide, and write
   `/app/work/adjudications.json` mapping record id/DOI to your final grade
   (0-3) with a rationale:

   ```json
   {"10.0000/synth.c.003": {"grade": 2, "rationale": "passivation mechanism transfers to perovskite grain boundaries"}}
   ```

   Then re-run once with adjudication:

   ```
   python3 /skills/weekly-skill/scripts/grade_relevance.py \
       --case /input/case.json --input /input \
       --corpus /app/work/corpus --work /app/work --out /app/output \
       --adjudicate /app/work/adjudications.json
   ```

   You get `adjudication_ledger.md` (engine grade vs your final grade, every
   change ledgered) and an engine-vs-adjudication nDCG@10 — a self-consistency
   number, **not** a benchmark score; report it as such. Unknown ids are
   rejected with the valid id list; fix the file, never force it. Skip this
   step only if the queue is empty or budget is exhausted — and then say so in
   `uncertainty`.

6. **Read the reports, act only on what they say.** `ranking_report.md` —
   grade histogram, tier counts, skipped files, and `zero_hit_facets`: facets
   matched by *no* record are honest coverage gaps; copy them into
   `result.json` uncertainty or enrich facet terms and re-run once.
   `graded_candidates.md` — spot-check that the top rows' decompositions match
   their evidence snippets. If grades look systematically wrong, the facets
   are wrong: fix `facets.json` and re-run, do not edit outputs.

7. **Finalize and validate:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status success \
       --clear-uncertainty
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --validate
   ```

   Fill any unmapped contract field with `--set 'field=/app/output/<file>'`.
   Record real limitations with `--uncertainty "..."` and keep
   `--status partial` if any gap is material. The validator fails loudly on
   empty contract fields, `case_id` mismatch, dangling paths, or `success`
   with non-empty uncertainty.

## What the engine guarantees (do not break these)

- **No fabrication:** grades come only from literal matching against local
  files; missing metadata stays `null`; no synonym expansion beyond what you
  wrote in `facets.json`.
- **Every grade is decomposable:** each record's `score_decomposition` lists,
  per facet, the matched terms, the fields they matched in, the contribution
  weight, and evidence snippets — a reviewer can re-derive every grade.
- **Borderline means borderline:** grade-1 records and grade->=2 records whose
  hits are abstract-only go to the queue; they are never silently promoted or
  dropped.
- **Adjudication is ledgered, never silent:** your overrides appear in
  `adjudication_ledger.md` with rationale; the engine grade is preserved next
  to your final grade.
- **Honest gaps:** zero-hit facets, skipped files and the all-zero-grades
  finding belong in the report and in `uncertainty`, not in the trash.

## Exception handling

| Situation | Handling |
|-|-|
| Empty candidate pool | Engine exits 2 with `ENGINE_STATUS=partial`. State plainly that the case shipped no usable snapshots; if platform search tools exist, do step 2, else deliver partial. |
| No facets.json and weak question | Fallback facets are single-term — expect noisy grades. Author facets.json (step 3) and re-run once; keep the fallback note in the report. |
| Borderline queue large | Normal on broad questions. Adjudicate top-down by engine grade; if budget runs out, adjudicate as many as you can, keep `status=partial`, and list the unadjudicated count in `uncertainty`. |
| Adjudication rejected (unknown ids) | The error lists every valid id. Fix the keys in adjudications.json and re-run; do not rename records in outputs. |
| All records graded 0 | Reported as a finding. Either facets do not describe the pool or the pool is off-topic — check `facets` and `question` in the digest before trusting anything. |
| zero_hit_facets non-empty | Honest coverage gap: enrich facet terms or widen the corpus (step 2), re-run once; otherwise carry it into `uncertainty`. |
| result.json validation fails | Fix exactly the reported field with `--set`; never blank a contract field; use `--clear-uncertainty` only when the notes are truly resolved. |

## Resources

- `scripts/grade_relevance.py` — the grading engine (stdlib only, offline).
- `scripts/make_result.py` — output_contract-driven result.json
  builder/validator.
- `references/methodology.md` — the exact 0-3 rubric, tier rules,
  decomposition format, tie-breaks and the nDCG formula, so each decision can
  be defended.
- `references/selfcheck.md` — pre-submission checklist.
- `examples/minimal_example.md` — a real two-stage local run on a synthetic
  case (outputs marked synthetic, not a formal case result).
