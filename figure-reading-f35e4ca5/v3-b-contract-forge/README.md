# contract-forged-figure-reading — bundle README

## Purpose

Downstream **output-contract engineering** (交付契约工程) for a scientific-figure-reading
harness agent. The case's `output_contract` is treated as the governed artifact: it is
parsed into a flat field plan, a valid skeleton `result.json` is materialized at minute
zero, fields are filled through a logged merge mechanism, and the final deliverable is
machine-linted against the contract with automatic status downgrade. The skill does not
read figures; it guarantees that whatever the agent read is delivered completely,
in-contract, and auditably.

## Dependencies

- `scripts/contract_parse.py`, `scripts/contract_fill.py`, `scripts/contract_lint.py`:
  **python3 standard library only**. No numpy, no PIL, no matplotlib, no network, no pip.
- `examples/make_synthetic_case.py`: additionally requires matplotlib (present in the
  harness runtime) to draw the synthetic demo figure.

## Input requirements

- `case.json` — JSON object with `case_id` (required) and `output_contract` (any shape:
  dict, list, scalar, or mixed). If `output_contract` is absent, `contract_parse.py`
  degrades (exit 2) to a minimal contract derived from task.md question lines.
- `task.md` — optional for parsing; used only in degraded mode.
- Fill fragments — JSON objects matching (a subset of) the contract shape, optionally
  carrying a top-level `_source` map of `path -> locator string`.
- Optional-marking conventions in contracts: a key ending in `?`, a string value
  starting with `optional` or containing `(optional)`, or a dict with
  `"optional": true` marks a field as not required.

## Field definitions

### `contract_plan.json` (written by contract_parse.py into `--work`)

| field | meaning |
|---|---|
| `case_id` | copied from case.json |
| `generated_at` | UTC ISO timestamp |
| `degraded` | true if the contract was derived from task.md (output_contract missing) |
| `n_fields` / `n_required` | plan size / required count |
| `fields[]` | one entry per plan path |
| `fields[].path` | JSON-pointer-ish path; list element templates use `<path>[]` |
| `fields[].expected_type` | `string` / `number` / `boolean` / `object` / `array` / `any` |
| `fields[].required` | false only if the contract marks the field optional |
| `fields[].filled` | set true by contract_fill.py when a non-null value lands |
| `fields[].fill_source` | locator recorded by contract_fill.py |

### `change_log.jsonl` (appended by contract_fill.py into `--work`)

One JSON line per **changed leaf path**:

| field | meaning |
|---|---|
| `ts` | UTC ISO timestamp of the merge |
| `path` | concrete leaf path (list indices as `[i]`) |
| `old` / `new` | value before / after the merge |
| `source` | locator from the fragment's `_source` map (longest ancestor match; may be null) |

### `lint_report.json` (written by contract_lint.py to `--out`)

| field | meaning |
|---|---|
| `case_id` | from case.json |
| `fatal` | true on case_id mismatch |
| `downgraded` | true if status was auto-downgraded `success → partial` (result.json rewritten) |
| `n_violations` / `violations[]` | each violation: `{check, path, message}`; checks are `case_id`, `coverage`, `type`, `status`, `locator`, `unit` |
| `null_required_paths` | required plan paths still null/missing and undocumented |
| `unresolved_uncertainty` | count of uncertainty entries not marked `"resolved": true` |
| `final_status` | status of the (possibly rewritten) result |

## Exit-code semantics (all three scripts)

| code | meaning |
|---|---|
| 0 | pass / clean |
| 2 | non-fatal degradation or violations, deliverable still written: parse = degraded fallback contract; fill = warnings (e.g. refused case_id change); lint = violations found and/or status downgraded |
| 1 | fatal (unreadable/invalid input files; lint: case_id mismatch) |

## Limitations

- No perception: the scripts never open the figure or tables; all reading is the agent's.
- List handling: the contract's first list element is the element template; heterogeneous
  lists are treated via that template. Fragment lists merge by index only when lengths
  match, otherwise they replace wholesale.
- `uncertainty` documentation is matched by exact `path` (dict entries) or substring
  (string entries); keep paths verbatim.
- The lint's claim/unit heuristics key on the literal names `value`, `source`,
  `locator`, `unit`; contracts using other names are still coverage-checked but not
  locator/unit-checked.

## Maintenance

- Keep the three scripts stdlib-only; any new dependency defeats the harness guarantee.
- When changing plan-path syntax, update `resolve()` in contract_lint.py, the `[]`
  generalization in contract_fill.py, and this README together.
- Re-run `examples/minimal_example.md` end-to-end after any script change.
