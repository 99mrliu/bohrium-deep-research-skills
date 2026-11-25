---
name: snapshot-trust-gate
description: Offline-first integrity gating for source-bound literature retrieval. Before any record enters the candidate pool, every local snapshot under /input (organizer-provided Crossref/EuropePMC/OpenAlex responses, reference exports) plus any raw search responses the agent saves during the run is hashed, parsed, schema-checked per source type, and screened for truncation, duplicate payloads, empty record lists and record-level defects (invalid DOI, missing title, implausible year). Only verified snapshots build the retrieval corpus; quarantined files are reported with reason codes instead of silently polluting results. Retrieval is deterministic (field-weighted term scoring, DOI/normalized-title dedup), every candidate carries provenance {file, json_index, sha256_12}, and zero-hit query terms are reported as honest coverage gaps. A contract-driven builder fills result.json with the original case_id and every output_contract field. Use for 学术文献检索/literature-search cases where inputs are organizer-local snapshots, live remote coverage is unavailable, and data authenticity plus per-record traceability decide the score.
---

# snapshot-trust-gate — verify the snapshots, then retrieve

Philosophy: **in a source-bound evaluation the biggest failure mode is not a missing
query — it is trusting a corrupt input.** A truncated Crossref page, a duplicated
snapshot, or a record with a malformed DOI silently poisons dedup, ranking and every
downstream claim. This skill puts a verification gate *upstream* of retrieval:
nothing enters the corpus until its source snapshot has been parsed, hashed and
schema-checked, and every exclusion is written down with a reason code.

The agent contributes judgment (reading the case, optionally fetching extra raw
responses with its own search tools); the engine does everything mechanical
deterministically, offline, stdlib-only.

## Runtime contract

- Platform installs this skill at `/skills/weekly-skill` and runs fixed cases:
  input `/input/case.json` + `/input/task.md` (+ snapshot material), work under
  `/app/work`, deliverables under `/app/output`, including `result.json` with the
  original `case_id` and **every** field named by `output_contract`.
- First action in any run: `ls -R /input` and read `case.json` — note `case_id`,
  every `output_contract` field name, and what snapshot material actually exists.
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
   Use your native literature-search tools for the research question and save
   **raw, unmodified** JSON responses under `/app/work/corpus/` (one file per
   response). The engine ingests them through the same gate as organizer
   snapshots. Never hand-edit a response; a doctored file fails hashing
   reproducibility and defeats the gate. If no search tools exist, skip — the
   organizer snapshots alone are a valid corpus.

3. **Run the gate + retrieval engine:**

   ```
   python3 /skills/weekly-skill/scripts/trust_gate.py \
       --case /input/case.json --input /input \
       --corpus /app/work/corpus --work /app/work --out /app/output
   ```

   It prints a one-line JSON digest: snapshots seen/verified/quarantined, unique
   records, ranked candidates, `zero_hit_terms`. Exit 2 means zero verified
   records — deliver partial with the digest in `uncertainty`.

4. **Read the reports, act only on what they say.**
   `quarantine_report.md` — why each file was excluded (PARSE_ERROR,
   DUPLICATE_PAYLOAD, SCHEMA_UNRECOGNIZED, EMPTY_RECORD_LIST). If a quarantined
   file looks important and you can see a fixable cause (e.g. agent saved a
   truncated response), re-save that one file and re-run once. Do not repair
   organizer snapshots by hand — record the defect in `uncertainty` instead.
   `search_report.md` — `zero_hit_terms` are honest coverage gaps; copy them into
   `result.json` uncertainty. Check the top rows of `candidates.md` are on-topic;
   if not, the question extraction may have failed — pass the real question by
   ensuring `case.json` carries it, do not edit outputs.

5. **Finalize and validate:**

   ```
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --status success
   python3 /skills/weekly-skill/scripts/make_result.py \
       --case /input/case.json --out /app/output/result.json --validate
   ```

   Fill any unmapped contract field with
   `--set 'field=/app/output/<file>'`. Record real limitations with
   `--uncertainty "..."` and keep `--status partial` if any quarantine or
   zero-hit gap is material. The validator fails loudly on empty contract
   fields, `case_id` mismatch, dangling paths, or `success` with non-empty
   uncertainty.

## What the gate guarantees (do not break these)

- **Authenticity first:** quarantined snapshots contribute zero records; the
  quarantine ledger is itself a deliverable a reviewer can audit.
- **No fabrication:** candidates come only from verified local files. Missing
  metadata stays `null`. Never hand-edit `candidates.*` — fix inputs and re-run.
- **Traceability:** every record carries `{file, json_index, sha256_12}`;
  `evidence/evidence_index.json` hashes every consulted file.
- **Honest gaps:** zero-hit terms and quarantined files belong in `uncertainty`,
  not in the trash.

## Exception handling

| Situation | Handling |
|-|-|
| No snapshots under /input at all | Engine exits 2 with `ENGINE_STATUS=partial`. State plainly that the case shipped no local corpus; if platform search tools exist, do step 2, else deliver partial. |
| All snapshots quarantined | Read reason codes; PARSE_ERROR on agent-saved files → re-save once; on organizer files → deliver partial, defect goes to `uncertainty`. |
| Zero ranked candidates but verified records exist | Question/term mismatch — check `query_terms` in the digest; Chinese questions are bigram-tokenized automatically. If truly nothing matches, report the gap; do not loosen silently. |
| Duplicate payloads of an important snapshot | Normal (organizers often ship both .json copies); the first copy wins, the rest are ledgered. No action. |
| result.json validation fails | Fix exactly the reported field with `--set`; never blank a contract field. |

## Resources

- `scripts/trust_gate.py` — the gate + retrieval engine (stdlib only, offline).
- `scripts/make_result.py` — output_contract-driven result.json builder/validator.
- `references/methodology.md` — every check, reason code, trust tier and the
  scoring formula, so each decision can be defended.
- `references/selfcheck.md` — pre-submission checklist.
- `examples/minimal_example.md` — a real local run on a synthetic case
  (outputs marked as synthetic example, not a formal case result).
