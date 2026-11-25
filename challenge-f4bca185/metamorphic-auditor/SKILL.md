---
name: metamorphic-auditor
description: Independently audit literature-data cleaning and standardization with raw/candidate disk reloads, row lineage, metamorphic tests, unit recomputation, counterexamples, and risk-ranked human review. Use when Challenge-f4bca185 or another tabular literature-cleaning task needs process quality control, candidate generation only if absent, or verify-existing validation. Not a checksum-only delivery checker and not an automated scientific-conflict resolver.
---

# Metamorphic Auditor

Independent **process quality control** for literature cleaning. Generate a deliberately small conservative candidate when no candidate exists, then discard any reliance on in-memory output and test the raw inputs and candidate artifacts as reloaded evidence. A matching hash alone says nothing about row conservation, altered values, fabricated missingness, or metamorphic behavior.

## Trigger

Use this Skill when the request involves one or more of:

- Challenge-f4bca185 literature-data cleaning, normalization, CSV/JSON candidate production, or delivery QA;
- independent verification of cleaned CSV/JSON against raw CSV/TSV/JSON/JSONL materials;
- row lineage/disposition, no-fabrication, exact-context dedup, unit arithmetic, rerun determinism, column/row permutation, whitespace/noise, finite JSON, review coverage, or locator tests;
- counterexamples, change ledgers, human review prioritization, or `--verify-existing`.

## Do not trigger / do not claim

Do not use as a citation finder, bibliographic fact checker, source-credibility ranker, domain unit ontology, probabilistic fuzzy deduplicator, checksum-only auditor, or scientific-conflict adjudicator. Passing tests supports only declared process invariants. It never proves that selected literature is scientifically correct, complete, or reconciled. Approximate identity and contradictory source claims remain open human review questions.

## Runtime contract

Python 3 standard library only. The script has no network, random, or wall-clock dependency.

```sh
python3 scripts/metamorphic_auditor.py
```

Defaults: `--input /input --work /app/work --output /app/output`. Optional flags:

- `--case PATH`: explicit case JSON/text;
- `--task PATH`: explicit task JSON/text;
- `--verify-existing`: never generate; audit the candidate already in `--output` after fresh raw and candidate reloads.

See `references/io_contract.md` for discovery, wrappers, unit/dedup declarations, output-contract projection, and exit codes. `references/invariants.md` is normative for each check and severity.

## Required procedure

1. **Read and checkpoint.** Read actual case/task and `output_contract`; write an early partial `result.json`. Discover material files independently, excluding case/task wrappers as files, while accepting explicit embedded `records`/`rows`/`items`/`extractions`/`observations`/`data` containers. Invalid/missing cases still produce reports and return nonzero.
2. **Conservative candidate only if absent.** Outside verify-existing, when both cleaned files are absent, apply only outer whitespace trimming and explicit decimal unit derivations into missing targets. Exact duplicate exclusion occurs only with configured keys/context and identical complete normalized rows. Retain all original columns plus source lineage. Do not overwrite an existing candidate.
3. **Reload independently.** Reparse raw files, `cleaned.csv`, `cleaned.json`, and `changes.jsonl` from disk. Map kept rows by explicit source IDs or tightly constrained exact matching. Never consult generation objects as verification truth.
4. **Test all eleven invariants.** Row partition, raw immutability, no fabricated missingness, declared conversion recomputation, dedup context isolation, deterministic rerun, row/column order, whitespace/noise, JSON finiteness/completeness, review coverage after queue reload, and source locators.
5. **Explain failures.** Emit structured counterexamples with check, severity, blocking impact, locator, expected/raw/candidate evidence. Rank review by blocking impact, then severity and stable identifiers. Include all blocking items and one deterministic representative per other check in the minimal human sample.
6. **Report honestly.** `status` is `success`, `partial`, or `input_error`; `verification_status` is independently `pass` or `fail`. A passing run with blocking human source-context review is `partial/pass`. Exit 0 only for verification pass, 1 for process-verification failure, 2 for input error. Unknown output-contract keys are null and listed unresolved. Never fabricate a schema value.

## Output contract

Always target:

- `cleaned.csv` and `cleaned.json`;
- `verification.json` with every named check;
- `counterexamples.jsonl` with debugging evidence;
- `changes.jsonl` with trim/derivation/exclusion lineage;
- `review_queue.csv` with blocking rank and minimal sample;
- `audit.md` with scope and limits;
- `result.json` with `case_id`, statuses, sources, uncertainty, change records, review queue, artifact inventory, and every declared output-contract field.

Hashes in the artifact inventory are supporting evidence only. They do not replace any metamorphic/invariant check.

## Executable example

`examples/synthetic-input` and `examples/synthetic-output` are wholly labelled **SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE**, including notice files and example case/result metadata. They are not official challenge data or submissions.

```sh
bash examples/run.sh
```

The harness generates in a temporary directory, checks fresh verify-existing determinism, tampers both candidate representations and demands nonzero/counterexamples, and tests malformed and missing cases. It uses only Python 3 and POSIX shell utilities.
