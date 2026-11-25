---
name: refgraph-snowball
description: Offline citation-graph snowballing for source-bound literature retrieval. Instead of planning queries against live APIs, this skill reconstructs the retained reference graph from organizer-local snapshots under /input (Crossref message.items, EuropePMC resultList.result, OpenAlex results) plus standalone reference exports (.bib/.ris/.txt/.md), resolves every reference to local records by exact DOI / OpenAlex-id / fuzzy title (difflib ratio >= 0.92), and snowballs from the seed set - backward over references that resolve locally, forward over local records that cite a seed - up to a configurable hop limit. Candidates are ranked by a fully documented deterministic graph score (seed base 10, reach weighted 4/hop, +2 per extra connected seed, small question-term tie-breaker) with every component shown per candidate. References that cannot resolve are ledgered with reason codes as coverage findings, never silently dropped. A contract-driven builder fills result.json with the original case_id and every output_contract field. Use for 学术文献检索/literature-search cases where seed papers and local snapshots carry reference lists, no live remote coverage exists, and recall must come from graph traversal with per-record traceability.
---

# refgraph-snowball — the retained reference graph is the recall engine

Philosophy: **in a source-bound case the highest-precision expansion signal is
not a better query — it is the reference graph the organizers already shipped.**
A seed paper's reference list is a hand-curated, expert-selected candidate set;
the local records that cite the seed are its natural forward neighbourhood.
Both are deterministic, offline, and fully auditable. This skill treats graph
traversal as the recall mechanism and question-term matching only as a
tie-breaker — never the other way round.

The agent contributes judgment (reading the case, confirming seeds, deciding
whether a gap is material); the engine does everything mechanical
deterministically, offline, stdlib-only.

## Runtime contract

- Platform installs this skill at `/skills/weekly-skill` and runs fixed cases:
  input `/input/case.json` + `/input/task.md` (+ snapshot material, possibly
  reference exports and PDFs), work under `/app/work`, deliverables under
  `/app/output`, including `result.json` with the original `case_id` and
  **every** field named by `output_contract`.
- First action in any run: `ls -R /input` and read `case.json` — note
  `case_id`, every `output_contract` field name, any explicit seed keys
  (`seed_dois`/`seeds`/`seed_papers`) or seeds file, and what snapshot
  material actually exists.
- Save a partial `result.json` before searching; improve incrementally; keep
  `status=partial` whenever anything material is missing.

## Procedure

1. **Secure a partial result immediately:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status partial
   ```

   (If the skill landed elsewhere, locate it with `ls /skills/*/scripts/`.)

2. **(Optional, only if platform search tools are available) widen the corpus.**
   If you can fetch extra raw API responses for the research question, save
   them **unmodified** under `/app/work/corpus/` (one file per response). The
   engine ingests them through the same normalization path as organizer
   snapshots, so any references they carry extend the local graph. Never
   hand-edit a response; if no search tools exist, skip — organizer snapshots
   alone are a valid corpus.

3. **Run the snowball engine:**

   ```
   python3 /skills/weekly-skill/scripts/refgraph.py \
       --case /input/case.json --input /input \
       --corpus /app/work/corpus --work /app/work --out /app/output
   ```

   It prints a one-line JSON digest: snapshots seen, records loaded, seeds
   matched (and their origin), references extracted/resolved/unresolved with
   reason counts, graph density, candidates. Exit 2 means zero records —
   deliver partial with the digest in `uncertainty`. Tune hop depth with
   `--max-hops` (default 2).

4. **Read the reports, act only on what they say.**
   `search_report.md` — digest + honest gaps: seeds with zero resolvable
   references, unmatched seed specifications, zero-density graphs.
   `unresolved_references.md` — the unresolved ledger with reason codes
   (`doi-not-in-corpus`, `title-not-in-corpus`,
   `openalex-id-not-in-corpus`, `no-identifier`, `ambiguous`). Unresolved
   references are **findings about corpus coverage** — copy the counts into
   `result.json` uncertainty; do not treat them as failures to hide.
   `candidates.md` — check the top rows are on-topic; each row's
   `score_breakdown` must show why it ranks where it does. If the seed set
   looks wrong (e.g. seeds were derived, not given), fix the seeds at the
   source (case keys or a seeds file) and re-run — never edit outputs.

5. **Finalize and validate:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status success
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --validate
   ```

   Fill any unmapped contract field with
   `--set 'field=/app/output/<file>'`. Record real limitations with
   `--uncertainty "..."` and keep `--status partial` if any gap is material
   (unmatched seeds, zero resolved references, sparse graph). The validator
   fails loudly on empty contract fields, `case_id` mismatch, dangling paths,
   or `success` with non-empty uncertainty.

## What the graph guarantees (do not break these)

- **Graph-first recall:** every non-seed candidate is justified by a resolved
  citation path from a seed, with hop distance and direction shown. Relevance
  terms only break ties — they cannot manufacture a connection.
- **No fabrication:** candidates come only from local files; missing metadata
  stays `null`. Never hand-edit `candidates.*` or `graph.json` — fix inputs
  and re-run.
- **Traceability:** every record carries `{file, json_index, sha256_12}`;
  `evidence/evidence_index.json` hashes every consulted file.
- **Unresolved references are findings:** the ledger with reason counts is a
  deliverable, and material counts belong in `uncertainty`.

## Exception handling

| Situation | Handling |
|-|-|
| No snapshots under /input at all | Engine exits 2. State plainly that the case shipped no local corpus; if platform search tools exist, do step 2, else deliver partial. |
| Records loaded but no seeds derivable | Engine reports `ENGINE_STATUS=partial`, `seed_origin=none`. Check whether seeds exist under another case key or a seeds file; if truly absent, deliver partial with the gap in `uncertainty`. |
| Seed DOIs given but none match local records | Ledgered in `seeds_unmatched`. Check DOI normalization in the snapshots; if the corpus genuinely lacks the seeds, deliver partial and say so. |
| References present but zero resolve locally | This IS a finding: report it via the unresolved ledger and `graph_density=0`, keep partial. Do not loosen thresholds silently. |
| Fuzzy title match looks wrong | Threshold is 0.92 with an ambiguity tie-rule (methodology §4). If a mismatch slipped through, note it in `uncertainty`; do not edit `graph.json`. |
| result.json validation fails | Fix exactly the reported field with `--set`; never blank a contract field. |

## Resources

- `scripts/refgraph.py` — the snowball engine (stdlib only, offline).
- `scripts/make_result.py` — output_contract-driven result.json builder/validator.
- `references/methodology.md` — every recognition shape, extraction rule,
  matching threshold, snowball semantic and the exact scoring formula, so each
  decision can be defended.
- `references/selfcheck.md` — pre-submission checklist.
- `examples/minimal_example.md` — a real local run on a synthetic case
  (outputs marked as synthetic example, not a formal case result).
