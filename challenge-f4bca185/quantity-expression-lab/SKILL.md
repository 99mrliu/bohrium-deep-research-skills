---
name: quantity-expression-lab
description: Compile messy typed quantity expressions into dimension-checked SI or specified units with an algebraic per-cell measurement ledger. Trigger for literature-table cleaning involving numbers with units, Unicode ranges, uncertainties, scientific notation, decimal/thousands locales, unit conversion, formula traces, or review queues. Do not trigger for entity resolution alone, field renaming without quantities, scientific conflict adjudication, or general PDF question answering with no quantity standardization.
---

# Quantity Expression Lab

## Exact trigger and non-trigger boundaries

**Trigger when** the requested work includes at least one typed measurement to parse or standardize: temperature, time, pressure, energy, amount concentration, volume, or a prefixed compound rate. Typical cues are `10–20 °C`, `2.50 ± 0.05 kJ`, `1 mmol L^-1 min^-1`, `1,234`, `单位换算`, `区间`, `不确定度`, `数量级前缀`, `保留原值`, or `逐单元格公式追踪`. End-to-end table cleaning is supported with deliberately minimal identity handling.

**Do not trigger when** the task is only substance/entity merging, synonym mapping, deduplication, statistical inference, filling missing values, resolving scientific disagreements, or reading prose without quantity conversion. Never use this Skill to guess a unit from a column name, infer a number region when ambiguous, turn a blank into zero, or overwrite evidence with a scientific judgment.

Read `references/failure-boundaries.md` before accepting a borderline task.

## Runtime contract

Python 3 standard library only. No installation, network, credentials, random generator, clock, external packages, or precomputed case answers are used.

The installed entry point is `scripts/quantity_expression_lab.py`, relative to this Skill directory:

```sh
python3 scripts/quantity_expression_lab.py --input /input --work /app/work --output /app/output
```

All five arguments are available; defaults are exactly:

- `--input /input`: actual case/material directory, or a material file.
- `--work /app/work`: contractual scratch location; this deterministic implementation creates no cache there.
- `--output /app/output`: editable results.
- `--case CASE.json`: optional case path; otherwise `/input/case.json` is read when present.
- `--task TASK.md`: optional task path; the actual task prose is read and source-hashed. Otherwise `task.md` under the input is included.

Read the actual `case.json`, actual task, and actual CSV/TSV/JSON/JSONL materials. Common nested `records`, `rows`, `items`, `measurements`, `extractions`, `observations`, `data`, `materials`, `table`, and `entries` are supported. Never assume content from a filename or domain label. Original fields and row identities are retained; there is no automatic row merge.

The actual case's `unit_conversions`, target-unit rules, `number_region`, explicit separators, and rounding configuration take precedence over material defaults. Use `references/grammar.md`, `references/unit-registry.md`, and `references/rounding.md` as the executable contract.

## Required run and inspection procedure

1. Run the entry point. It first writes all seven required artifacts with `status: partial`; failure is reported, not concealed.
2. Inspect `result.json` and `review_queue.csv`. Confirm `case_id`, honest `status`, `sources`, `uncertainty`, `change_records`, `review_queue`, and `artifacts` are present.
3. Every original `output_contract` top-level key is retained. Direct mappings, lists, and common `fields`/`properties`/`schema`/`result`/`outputs` wrappers are supported. A recognized producer fills known keys; an unknown key remains JSON `null` and is explicitly listed in `contract_unresolved` and `uncertainty`.
4. Inspect successful calculations in `quantity_ledger.jsonl`: raw lexeme, parsed quantity shape, raw/target units, dimension vector, uncertainty, exact multiplier/offset formula, rounding, source file and row/cell locator. Each changed cell has a corresponding `changes.jsonl` record.
5. Failed cells remain raw, never zero, and receive stable review codes. Malformed case/material input exits nonzero and still writes honest error artifacts when the output directory is writable. Cell-level quantity failures permit a partial result with exit code zero.
6. Require valid UTF-8 JSON with `allow_nan=false`; NaN and Infinity are neither consumed as JSON constants nor emitted.

The complete artifact set is `cleaned.csv`, `cleaned.json`, `quantity_ledger.jsonl`, `changes.jsonl`, `review_queue.csv`, `audit.md`, and `result.json`.

## Method map

- `scripts/quantity_core.py`: stateful tokenizer, recursive-descent parsers, dimension algebra, linear/affine Decimal conversion, interval/uncertainty handling and rounding.
- `scripts/quantity_expression_lab.py`: file adapter, case-rule precedence, sparse nested-record extraction, early partial output, ledger/change/review/audit/result generation.
- `scripts/self_test.py`: standard-library tests for affine and reverse-affine conversion, compound prefixes, interval reversal under a negative multiplier, ambiguous decimal rejection, unknown units, missing values and dimension mismatch.
- `references/failure-boundaries.md`: supported input, conservative rejection, and deliberately unimplemented identity/scientific decisions.

Run `PYTHONDONTWRITEBYTECODE=1 python3 scripts/self_test.py` for self-checks.

## Labelled synthetic example

`examples/synthetic-input` and `examples/synthetic-output` are **SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE**, not fixed cases, whiteboards, benchmark results, or prepared official answers. Inspect the actual calculated Celsius→Kelvin, interval, and compound-prefix results there.

```sh
sh examples/run.sh
```

The script reruns both the end-to-end synthetic example and self-tests. Deterministic reruns replace the same seven output files byte-for-byte for unchanged input.
