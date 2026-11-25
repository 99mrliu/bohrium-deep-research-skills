# Actual runnable inspection — SYNTHETIC minimal example

Date: 2026-11-25. Runtime used for the recorded run: **Python 3.12.14**. The commands were run from the Skill root with the standard library only. This is an explicitly synthetic test, not a formal-case result or benchmark claim.

## 1. Real artifact creation and reconstruction

The following commands were actually executed (ledger creation was run before this idempotent verification run):

```sh
python3 -B scripts/numeric_ledger.py \
  --sources examples/minimal/input/sources.json \
  --ledger examples/minimal/output/numeric_ledger.jsonl \
  --audit examples/minimal/output/ledger_inventory.md

python3 -B scripts/numeric_result.py check \
  --case examples/minimal/input/case.json \
  --targets examples/minimal/input/target-fields.json \
  --sources examples/minimal/input/sources.json \
  --ledger examples/minimal/output/numeric_ledger.jsonl \
  --selection examples/minimal/selection.json \
  --output examples/minimal/output/result.json \
  --audit examples/minimal/output/audit.md
```

Observed output:

```text
{"status": "ok", "harvested_tokens": 17, "appended_tokens": 0, "existing_tokens_preserved": 17, "ledger": "examples/minimal/output/numeric_ledger.jsonl"}
{"status": "verified", "fields": 3}
```

The preceding build really wrote `numeric_ledger.jsonl`, `result.json`, and `audit.md`; this rerun independently reconstructed and exactly compared the result. Direct file inspection confirmed:

- `output/numeric_ledger.jsonl`: 17 UTF-8 JSONL records.
- `output/result.json`: case ID `SYNTHETIC-NUMERIC-LEDGER-MINIMAL`, overall `answered`, exactly three unique target-field records; the scoped non-report and documented conflict are completed adjudications.
- `treatment_response_37c`: `reported`; scalar `4.8 ± 0.3`; units `mV`; both condition keys `37 °C`; value ID `N000005` and condition ID `N000004`.
- `recovery_half_time`: `not_reported`, null scalar/units/statistic, with the exact scoped non-reporting quotation rather than a numeric placeholder.
- `replicated_treatment_response_37c`: `source_conflict`, null top-level scalar/units/statistic, two exact variants (`4.8 ± 0.3 mV` and `5.0 ± 0.4 mV`) under `37 °C`, with no averaging or preferred value.
- `output/audit.md`: readable field table, evidence quotes, page/paragraph/token IDs, exact spans, conflict alternatives, and mechanical/semantic boundary notes.

## 2. Typography and offset inspection

`ledger_inventory.md` was read against `input/sources.json`. Confirmed exact harvested forms include:

| ID | Exact raw | Verified decomposition/location |
|---|---|---|
| `N000002` | `3.2 ± 0.2 mV` | Deliberate 25 °C control decoy, not selected for treated 37 °C |
| `N000004` | `37 °C` | `p-treatment`, half-open offsets 6–11, scalar `37`, units `°C` |
| `N000005` | `4.8 ± 0.3 mV` | `p-treatment`, offsets 38–50, scalar `4.8 ± 0.3`, units `mV` |
| `N000006` | `2–4 ms` | En dash retained; kind `range`; units `ms` |
| `N000007` | `p<0.01` | Statistic and scalar `0.01`, comparator `<` |
| `N000008` | `n=18` | n statistic retained |
| `N000009` | `Fig. 2` | Figure reference, not scalar |
| `N000010` | `5 × 10⁻³ mol·L⁻¹` | Superscript minus and unit superscript/middle dot retained |
| `N000011` | `8%` | Units exactly `%` |
| `N000012` | `(95% CI 0.4–1.1)` | Confidence/lower/upper components; exact parentheses and range retained |
| `N000013` | `0.6 percentage points` | Units exactly `percentage points`, distinct from `%` |
| `N000014` | `<0.2 °C` | Inequality comparator `<`, units `°C` |
| `N000017` | `Table 2` | Table reference, not scalar |

## 3. Positive and negative test execution

Executed:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
```

Observed:

```text
Ran 12 tests in 1.591s

OK
```

Every test reported `ok`:

1. `test_end_to_end_real_artifacts_and_statuses` — build/check, all three artifacts, statuses, exact treated value, conflict variants.
2. `test_all_requested_typography_is_harvested_losslessly` — all tricky raw strings, spans/components, `%` versus percentage points, p comparator.
3. `test_identifier_digits_are_not_silently_lost` — `C6H12O6` and `ID7` become explicit numeric residuals, not silent omissions.
4. `test_append_only_rerun_is_byte_identical` — second harvest appends zero rows and preserves SHA-256/bytes.
5. `test_changed_existing_source_cannot_rewrite_ledger` — changed old source produces `append-only collision`; original bytes remain.
6. `test_early_partial_is_immediate_complete_field_envelope` — immediate `partial`, three `pending_read` records.
7. `test_reject_altered_scalar` — changing `4.8 ± 0.3` to `4.9 ± 0.3` exits 2 at `.scalar`.
8. `test_reject_altered_unit` — changing `mV` to `µV` exits 2 at `.units`.
9. `test_reject_altered_condition_text` — changing both condition aliases to the decoy `25 °C` exits 2 at `experimental_condition`.
10. `test_reject_wrong_condition_binding_in_selection` — treated value `N000005` plus control condition `N000001` exits 2 with `wrong condition binding`.
11. `test_reject_decoy_value_under_other_condition` — control value `N000002` plus treated condition `N000004` exits 2 with `wrong condition binding`.
12. `test_unreadable_is_not_relabelled_absent` — `extraction_failed`/`unreadable_source` remains distinct from `not_reported` and keeps null value fields.

Negative tests run in temporary directories under `examples/minimal` and clean up after themselves. They therefore reject mutated copies without corrupting the delivered passing ledger/result.

## 4. Reviewed limitations

- The checks reject cross-statement condition substitutions, but cannot resolve every same-sentence clause/coreference ambiguity.
- The verifier proves fidelity to selected IDs, not completeness of an Agent's semantic search or global absence claim.
- Canonical text is only as trustworthy as inspected PDF/table/OCR transcription; stdlib scripts do not provide OCR.
- Residual tokens intentionally include chemical/identifier digits and must not automatically become answers.
- The synthetic run demonstrates mechanics and failure handling, not real-paper extraction accuracy or comparative performance.
