---
name: litsearch-query-planner
description: Coverage-driven multi-round query planning for academic literature retrieval. The agent writes one small search plan (facets + synonyms + year window + databases) after reading the case; a deterministic stdlib-only engine then runs planned query rounds (core-AND, facet-relaxed OR, citation snowball via OpenAlex) against Crossref/OpenAlex/EuropePMC plus any local snapshots in /input, stops on marginal yield, deduplicates by DOI/normalized title, scores relevance with a documented rubric, and writes ranked candidates, a per-facet coverage report, and a complete query-level evidence log. A contract-driven builder fills every output_contract field of the case. Use for literature-search cases (学术文献检索/文献筛选) where recall, coverage of all sub-topics, and per-query traceability matter and the run must finish within a tight budget (~8-12 model requests).
---

# Literature search by multi-round query planning — plan once, let the engine run

Philosophy: **you do the thinking that needs judgment (decomposing the research question into facets and synonyms); the engine does everything mechanical (queries, dedup, scoring, logging) deterministically.** A base agent fails retrieval cases by issuing one or two ad-hoc queries, losing track of what was searched, and returning unverifiable lists. Here every round is planned, every query is logged to `evidence/search_log.jsonl`, every candidate traces to a raw API response or a local snapshot file, and coverage gaps are reported instead of hidden.

## Inputs and outputs

- Read first: `/input/case.json` (note `case_id` and **every** field name in `output_contract`), `/input/task.md`, and `environment/resources.yaml` if present. Also `ls -R /input` — the case may ship local snapshots (saved Crossref/EuropePMC/OpenAlex responses, reference lists, PDFs); the engine ingests them automatically and treats them as authoritative.
- Work in `/app/work`; all deliverables go to `/app/output`, including `result.json` containing the original `case_id` and **every** field named by `output_contract`.
- Save a partial `result.json` **before** searching, then improve it. Budget target: ≤12 model requests total.

## Procedure

1. **Secure a partial result immediately:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial
   ```

   (If the skill is installed elsewhere, find the path with `ls /skills/*/scripts/`.)

2. **Read the case and write the search plan** — this is your one high-value act. From `case.json` + `task.md` extract: the research question, its 2–5 conceptual facets (e.g. material / method / application / metric), synonyms and abbreviations per facet (include both English and Chinese terms if the question is Chinese), any year window, and which databases to use. Write `/app/work/plan.json`:

   ```json
   {"facets": [{"name": "perovskite", "terms": ["perovskite"],
                "expanded": ["halide perovskite", "钙钛矿"]},
               {"name": "stability", "terms": ["stability", "degradation"],
                "expanded": ["lifetime", "稳定"]}],
    "databases": ["crossref", "openalex", "europepmc"],
    "year_from": null, "year_to": null}
   ```

   Rules: every facet in the question must appear (uncovered facets are reported as gaps — do not silently drop them); 1–4 terms per facet; use EuropePMC only for bio/medical topics. If you skip this step the engine falls back to automatic facet extraction, which is worse — say so in `uncertainty` if you had no time.

3. **Run the engine:**

   ```
   python3 /skills/weekly-skill/scripts/planned_search.py --case /input/case.json --input /input --work /app/work --out /app/output
   ```

   It prints a one-screen digest: `ENGINE_STATUS`, unique record count, per-facet coverage, source failures, stop reason. Runtime is typically 1–3 minutes. It executes: round 0 local-snapshot ingest → round 1 core-AND query per database → round 2 facet-relaxed OR queries → round 3 plain-question query (stops early when a round adds <5% new uniques) → OpenAlex citation snowball (references + citing works of the top-5 seeds) → dedup → relevance scoring → ranked `candidates.md`/`candidates.json` + `search_report.md` + `evidence/search_log.jsonl` + `evidence/raw/*.json`.

4. **Verify the digest, fix only what is cheap.** Read `search_report.md`. If a facet is **NOT COVERED** and you can see why (e.g. a mistranslated term), correct `plan.json` and re-run once. If a source failed (timeout/HTTP), that is recorded — do not retry more than once; the failure belongs in `uncertainty`. Check that the top-10 titles in `candidates.md` are actually on-topic; if the question was misread, fix the plan, not the output files.

5. **Finalize and validate:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status success
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --validate
   ```

   The builder hashes every consulted input file into `sources`, fills each `output_contract` field with the matching artifact, and the validator fails loudly on empty contract fields, wrong `case_id`, dangling paths, or `status=success` with non-empty `uncertainty`. Fill stubborn fields with `--set 'field=/app/output/<file>'`; record real limitations with `--uncertainty "..."` and keep `status` `partial` if anything material is missing.

## What the engine guarantees (and what you must not break)

- **Traceability:** every record in `candidates.json` carries `provenance` entries `{source, query, round, url, raw, retrieved_at}`; `raw` points to the actual cached API response under `evidence/raw/`. A reviewer can re-issue any query from `search_log.jsonl`.
- **No fabrication:** candidates come only from actual API responses or local snapshots. Missing metadata fields are `null`, never guessed. Do not hand-edit `candidates.*` to "improve" them — fix the plan and re-run.
- **Honest coverage:** facets with zero hits stay visible in `search_report.md` as NOT COVERED and must be copied into `result.json` `uncertainty`. An uncovered facet is a finding, not a failure to hide.
- **Determinism:** same plan + same API state ⇒ same output; the ranking formula is fixed and documented in `resources/methodology.md`.

## Exception handling

| Situation | Handling |
|-|-|
| Engine exits non-zero | Read the traceback; the common cause is a malformed `plan.json` — validate it with `python3 -c "import json;json.load(open('/app/work/plan.json'))"`. Re-run once; if it persists, deliver partial results with the error in `uncertainty`. |
| All sources fail (no network) | Re-run with `--offline`: the engine uses only local snapshots from `/input`. Status becomes `partial`; state clearly that live databases were unreachable. |
| Zero records overall | Check the question extraction in the digest (`question_excerpt`). If the case stores the question under an unusual key, add it to `plan.json` yourself via facets. If truly nothing exists, keep `status=partial` and document the queries tried (they are in `search_log.jsonl`). |
| HTTP 429 / rate limit | The engine already backs off; if the digest shows repeated 429s for one source, remove it from `plan.json` `databases` and re-run once. |
| Local snapshot unreadable | It is skipped silently by design; check `evidence/search_log.jsonl` round 0 and mention skipped files in `uncertainty` if they looked relevant. |
| Snowball finds nothing new | Normal for narrow topics; the stop line is in the report. No action. |

## Resources

- `scripts/planned_search.py` — the engine (plan → multi-round queries → snowball → dedup → score → coverage report). Stdlib only, no installs.
- `scripts/make_result.py` — output_contract-driven result.json builder/validator.
- `resources/methodology.md` — exact query-construction rules, stop criterion, dedup keys, and the relevance formula, so every ranked number can be defended.
- `resources/selfcheck.md` — 10-point final checklist before finalizing.
- `examples/minimal_example.md` — one minimal end-to-end invocation with illustrative (clearly marked) output.

## Limits

- Relevance scoring is lexical (facet-term coverage + citations), not semantic embeddings; borderline-relevant papers may rank low — mitigate by generous synonyms in `plan.json`.
- Snowballing uses only OpenAlex citation links; paywalled-graph gaps are inherited.
- EuropePMC suits biomedical topics; for physics/CS keep it out of `databases`.
- The engine does not read full-text PDFs; screening is title/abstract/metadata level. If the task requires full-text judgement, state that limit in `uncertainty`.
