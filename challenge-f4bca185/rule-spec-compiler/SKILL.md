---
name: rule-spec-compiler
description: Compile case-specific field, missing-value, numeric, range, unit, identity, mapping, and precedence declarations into a frozen execution plan, then conservatively clean tabular literature data with complete provenance and review artifacts.
---

# Rule-spec compiler

## Trigger

Use this Skill when a task supplies `case.json`, `task.md`, tabular records, or JSON rule resources and asks for literature-data cleaning, normalization, standardization, schema mapping, unit conversion, or an auditable review queue and the exact challenge is **Challenge-f4bca185 文献数据清洗与标准化**. Use it especially when rules differ per case and must be compiled rather than inferred from a fixed vocabulary.

## Do not trigger

Do not use it as a generic exploratory-data-analysis pipeline, an imputation/entity-resolution service, a free-form scientific fact extractor, a large terminology dictionary, or a substitute for source review. It does not invent missing contract fields, resolve incompatible rules by preference, guess units, deduplicate identities, or silently overwrite occupied target fields.

## Center of operation

1. Read the actual case/task declarations and optional resources; do not infer rules from column names alone.
2. Discover only explicitly labeled mappings, missing tokens, numeric/range conventions, unit targets, identity keys, custom rules, and overrides.
3. Compile a content-addressed rule register. Each rule has a stable `rule_id`, explicit priority, and source pointer. Detect incompatibility before reading values for transformation.
4. Freeze `execution_plan.json`; execute enabled, declared built-ins in priority order. Hold every member of an incompatible set and create review items. Precedence orders compatible operations; it is not permission to overwrite a conflicting rule.
5. Emit the cleaned records, direct CSV, cell-level changes, review queue, audit, statistics, and contract-complete result.

Read [references/rule-dsl.md](references/rule-dsl.md) for accepted declarations, [references/semantics.md](references/semantics.md) for precedence/failure behavior, and [references/maintenance.md](references/maintenance.md) for safe extension.

## Runtime contract

Python **3 standard library only**, no network, random source, wall clock, external package, or service.

```sh
python3 scripts/rule_spec_compiler.py \
  --input /input --work /app/work --output /app/output
```

Defaults are exactly those paths. Optional `--case`, `--task`, repeatable `--rules`, and repeatable `--config` select explicit resources or JSON overrides. Input discovery supports CSV (including conservative delimiter detection), TSV, JSON arrays/common object wrappers, JSONL, and explicit record containers embedded in `case.json`. The implementation reads actual inputs; examples are not embedded proxy results.

Every completed run writes directly:

- `cleaned.csv` — one direct flat statistical/data table, no JSON wrapper;
- `cleaned.json` — array of flat record objects;
- `execution_plan.json` — frozen, content-hashed immutable plan (also copied to work);
- `changes.jsonl` — deterministic cell changes with rule provenance;
- `review_queue.csv` — stable review IDs, rule IDs, row identity, and reasons;
- `audit.md` — rule execution/hold state and contract accounting;
- `statistics.csv` — direct `metric,value` statistical CSV;
- `result.json` — complete run envelope and artifacts.

`result.json` always aims to contain `case_id`, `status`, `sources`, `uncertainty`, `change_records`, `change_log`, `review_queue`, and `artifacts`, plus every field declared by `output_contract`. Unknown required fields are `null` and named in `unresolved_fields`; they are never fabricated. Empty/missing cells remain empty; NaN and Infinity are rejected rather than emitted.

Statuses and exit codes: `success`/0 means no actionable open review item; `partial`/0 means usable records remain but conflicts, conversion errors, unresolved required contract fields, or invalid overrides need review; `input_error`/2 means no usable records or an unrecoverable case/input. An early `partial` result is saved before compilation. Invalid cases and failures still produce the complete artifact set when filesystem access permits. Expected data-quality reviews therefore do not masquerade as process failures.

## Synthetic example

All example fixtures and generated artifacts are visibly labeled `SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE`; none is an official competition case.

```sh
sh examples/run.sh
```

The runner executes standard-library self-tests, a full successful example, an independent byte-for-byte deterministic rerun, a conflict producing `partial`/exit 0 with held rules, and a no-data conflict producing `input_error`/exit 2. It operates only below this Skill's `examples/` directory.
