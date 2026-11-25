# Verification and reading policy

## Mechanical guarantees

Given unchanged canonical sources, targets, selection, and append-only ledger, the scripts verify:

1. Each current source harvest row is byte-value equivalent as decoded JSON to its stored ledger row; changed old IDs are not silently rewritten.
2. Raw expressions, component text, scalar text, unit text, context, and statement quotes derive from exact Unicode-codepoint source spans.
3. Only the Agent-selected value ID supplies a reported scalar/unit. An edit such as `4.8` → `4.9`, `mV` → `µV`, `%` → `percentage points`, or `p<0.01` → `p=0.01` fails `check`.
4. Condition IDs must share the value's statement, output condition aliases must agree, and the check reconstructs condition text from exact offsets.
5. References cannot be used as scalar values. Statistic/reference lists have type checks. Distinct selected comparators are rejected.
6. Exactly one top-level record per requested field is emitted, with all required keys and evidence locations.
7. `source_conflict` retains differing variants; `not_reported` has searched-scope quotes; `extraction_failed` names a failure. A placeholder or regex miss cannot silently become a reported zero.
8. Full-result comparison catches edits outside scalar/unit too, including quotations, evidence, claims, hashes, and notes.

These checks do not use target-string similarity and do not select answers.

## Agent semantic checklist

For each target, document the following in selection notes and inspect the final audit:

- **Quantity and population:** Does the statement measure the requested endpoint for the requested group, rather than a baseline, control, decoy, different cohort, or different material?
- **Condition binding:** Are dose, temperature, duration, sample, time point, and comparator attached by the source itself? A nearby numeric token is not automatically a condition. Explicitly reject decoys under other conditions.
- **Representational completeness:** Retain central value, range endpoints, uncertainty, inequality, units, percent versus percentage-point language, and n/p/CI statistics. Do not reduce `4.8 ± 0.3` to `4.8` or `2–4` to `4`.
- **Source location:** Quote the exact statement and preserve source/page/paragraph. Use table row/header and figure-caption context rather than an orphaned number.
- **Multiplicity:** Repeated identical support is not conflict. Different applicable values remain conflict; different conditions are not conflicting measurements of one condition.
- **Missing versus unreadable:** Absence requires a readable scoped review. No text layer, bad OCR, failed table extraction, or inaccessible material is `extraction_failed`, not `not_reported`.
- **No repair:** Do not “fix” apparent source errors, calculate derived values, average conflicts, convert units or percentages, or replace missing values with typical values.

## Known limits and manual review

- Statement-level co-location is a guardrail, not a complete semantic parser. Two measurements in one sentence can still require clause/coreference judgment. If unsure, use `extraction_failed` with `ambiguous_scope` and evidence rather than guessing.
- The statement splitter treats semicolons and likely sentence punctuation as boundaries; unusual abbreviations can produce imperfect statements. Raw token and paragraph spans remain exact, but condition binding should be inspected.
- The lexer supports common forms, not every mathematical expression or language. Residual digits reduce omission risk but can include IDs/chemical-subscript numbers that are not target measurements.
- PDF tables, merged cells, superscripts, and OCR output are only as reliable as the inspected canonical transcription. The standard-library scripts do not themselves render or OCR PDFs.
- The verifier proves consistency with selected IDs and exact strings, not that the Agent chose the semantically correct ID, searched every necessary supplement, or established global absence.
- Conflict conditions must match lexically. Source-equivalent but typographically different conditions need human-scoped handling, not conversion.

## Negative-test expectation

A valid synthetic result must pass `check`. Then independently alter one scalar, one unit, and a condition binding: each must fail nonzero. Finally rerun harvest and compare ledger bytes; an unchanged corpus must append no rows. `examples/minimal/INSPECTION.md` records the actual execution of these checks.
