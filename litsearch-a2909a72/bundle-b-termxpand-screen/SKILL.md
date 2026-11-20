---
name: litsearch-termxpand-screen
description: Terminology-expansion and reason-coded two-stage screening for academic literature retrieval. A stdlib-only engine expands the research question's terms (abbreviation pairs detected from the case text, spelling/hyphen/morphology variants, a built-in Chinese-English scientific glossary the agent extends), issues a bounded set of expanded queries against Crossref/OpenAlex/EuropePMC plus local snapshots in /input, then screens every record through an explicit PRISMA-style rubric (title screen, abstract screen) where every kept AND every dropped paper lands in screening_ledger.csv with decision, stage, reason code, score and the exact evidence sentence. Produces prisma_flow.md counts, an omissions report (zero-coverage concepts and near-miss exclusions) and a contract-driven result.json. Use for literature-search/screening cases (文献检索与筛选) where defensible inclusion/exclusion rationale and metadata traceability matter, within ~8-12 model requests.
---

# Literature retrieval by terminology expansion + auditable screening

Philosophy: **recall is won or lost at the term level, and credibility is won or lost at the screening ledger.** Base agents fail these cases two ways: they query with the question's raw words only (missing abbreviations, synonyms and Chinese/English equivalents), and they present a final list with no record of what was rejected or why. This skill fixes both: you define 3–6 well-expanded concepts; the engine handles variants, queries, dedup, scoring, and writes a complete decision ledger in which exclusion is a documented decision, never a silent delete.

## Inputs and outputs

- Read first: `/input/case.json` (note `case_id` and **every** field in `output_contract`), `/input/task.md`, `environment/resources.yaml` if present, and `ls -R /input` — organizer snapshots (saved API responses, reference lists) are ingested automatically and are authoritative.
- Work in `/app/work`; deliverables to `/app/output` including `result.json` with the original `case_id` and every `output_contract` field.
- Secure a partial `result.json` first; budget target ≤12 model requests.

## Procedure

1. **Secure a partial result:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial
   ```

   (Find the install path with `ls /skills/*/scripts/` if different.)

2. **Define the concepts — your one high-value act.** From the case extract 3–6 concepts that together cover the research question. For each, list terms and expanded equivalents: abbreviation ↔ full name, spelling variants, Chinese ↔ English. Write `/app/work/terms.json`:

   ```json
   {"concepts": [{"name": "perovskite solar cell",
                  "terms": ["perovskite solar cell", "PSC"],
                  "expanded": ["halide perovskite photovoltaic", "钙钛矿太阳能电池"]},
                 {"name": "stability",
                  "terms": ["stability", "degradation"],
                  "expanded": ["lifetime", "durability", "稳定性"]}],
    "databases": ["crossref", "openalex"],
    "year_from": null, "year_to": null}
   ```

   Also add any domain terms to `/app/work/glossary_extra.md` using the table format of `resources/glossary.md` (the engine merges it). If you skip this step the engine auto-extracts concepts from the question text — worse; note it in `uncertainty`.

3. **Run the engine:**

   ```
   python3 /skills/weekly-skill/scripts/termxpand_screen.py --case /input/case.json --input /input --work /app/work --out /app/output
   ```

   Digest output: `ENGINE_STATUS`, identified/screened/included counts, E1/E2 exclusions, concepts, problems. It executes: term expansion (abbreviation pairs from the case text + variant rules + glossary) → bounded expanded query set (core-AND + per-concept OR, ≤12 queries) → Crossref/OpenAlex (+EuropePMC if you list it) + local-snapshot ingest → DOI/title dedup (E3) → type/year gates (E4/E5) → stage-1 title screen (E1) → stage-2 abstract screen (E2) with a fixed formula → ranked `candidates.md`, `screening_ledger.csv`, `prisma_flow.md`, `omissions.md`, `expansion_report.md`, `evidence/search_log.jsonl`.

4. **Verify, tune once if needed.** Open `omissions.md`: any concept with **zero** retrieved records is a coverage gap — if a better synonym would fix it, add it to `terms.json` and re-run once. Skim the top of `screening_ledger.csv` E2 rows: if obviously on-topic papers sit just below the threshold, lower it (`--threshold 0.25`) and re-run once, stating the chosen value. Do not edit the ledger by hand.

5. **Finalize and validate:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --status success
   python3 /skills/weekly-skill/scripts/make_result.py --case /input/case.json --out /app/output/result.json --validate
   ```

   Fill stubborn contract fields with `--set 'field=/app/output/<file>'`; record real limitations (uncovered concepts, source failures, offline fallback) with `--uncertainty "..."` and keep `status` `partial` when material.

## What the engine guarantees (and what you must not break)

- **Every record accounted for:** `identified = included + E1 + E2 + E3 + E4 + E5` holds exactly; `prisma_flow.md` shows the counts. Never delete ledger rows.
- **Decisions carry evidence:** each ledger row has the title/abstract snippet the decision was based on. Reviewers re-check decisions without re-running.
- **No fabrication:** records come only from real API responses or local snapshots; missing metadata is `null`. Do not hand-edit `candidates.*` — fix terms and re-run.
- **Expansion is visible:** `expansion_report.md` lists every concept's full term set and every executed query, so recall gains are attributable to specific expansions.

## Exception handling

| Situation | Handling |
|-|-|
| Engine exits non-zero | Usually malformed `terms.json` — validate with `python3 -c "import json;json.load(open('/app/work/terms.json'))"`; fix and re-run once. |
| No network / all sources fail | Re-run with `--offline` (local snapshots only); status `partial`, state it in `uncertainty`. |
| Zero included records | Check `expansion_report.md`: are the concepts too narrow or the threshold too high? Broaden terms or lower `--threshold`, re-run once. If still zero, keep `status=partial` and document queries tried. |
| Huge result set (≥ thousands) | Normal for broad questions; the ledger handles it. Consider raising `--threshold` for precision and say so. |
| Rate limiting (HTTP 429) | Drop the affected source from `databases` in `terms.json`, re-run once; record in `uncertainty`. |
| Case question in an unusual field | Add the right terms directly in `terms.json`; the engine scores against concepts, not the raw question. |

## Resources

- `scripts/termxpand_screen.py` — the engine (expansion → queries → dedup → two-stage screening → ledger). Stdlib only.
- `scripts/make_result.py` — output_contract-driven result.json builder/validator.
- `resources/glossary.md` — built-in zh↔en scientific glossary and abbreviation seed table; extend via `/app/work/glossary_extra.md`.
- `resources/screening_rubric.md` — reason codes, scoring formula, decision order, tuning guidance.
- `resources/selfcheck.md` — final checklist.
- `examples/minimal_example.md` — minimal end-to-end invocation with illustrative (clearly marked) output.

## Limits

- Screening is lexical (term coverage + citations), not embedding-based semantic similarity; paraphrased relevance can be missed — mitigate with generous concept expansion.
- Abstract-less records are included only as I3 (uncertain) or excluded as E1; full-text judgement is out of scope — state it in `uncertainty` when the task requires it.
- The built-in glossary covers common materials/chemistry/CS/biomed vocabulary; specialized domains need agent-added entries in `terms.json`/`glossary_extra.md`.
