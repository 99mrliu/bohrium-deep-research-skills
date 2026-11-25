# Synthetic example (not an official case or prepared answer)

Everything under `examples/fixture` is fabricated solely to exercise the
interfaces. The toy formulas and values are not official answers and do not
constitute a benchmark result.

Run from this directory or any other working directory:

```bash
bash examples/run_synthetic_example.sh
```

Optional: set `CCA_RUN_ROOT` to a path beginning
`/tmp/claim-coverage-adjudicator-example-`. The script rejects other roots before
cleaning prior demonstration output.

## What actually runs

1. **Scaffold and early partial:** a three-line task becomes three authored
   atoms: eq1 transcription, eq2 transcription, and a held-out-score claim. The
   case uses `required_fields`, `field_types`, and `status_enum`. The scaffold
   extracts actual task, prose, and MathML excerpts.
2. **Defective ledger:** `claims.defective.json` has no evidence record for eq2.
   Adjudication returns 1; finalization yields `partial`, reports unsupported
   eq2 and incomplete formula coverage, and retains its named missing object.
3. **Repaired ledger:** `claims.repaired.json` attaches the exact eq2 MathML
   `<m:mfrac>` quote at its real source ID. Adjudication and finalization succeed
   only after both eq1 and eq2 have support. Final evidence quotes are checked
   again against the normalized excerpts.
4. **Legacy contract:** `required_fields` is renamed to `fields`; the same
   successful authored draft remains typed and valid.
5. **Deliberate contradiction:** a second completed central score answer shares
   `toy-held-out-score` but has a different value. Both records have valid quote
   mechanics. The automatic group check and explicit unresolved record force
   `partial`; aggregation does not delete the refuted side.
6. **C02-like branch:** no formula or raw-data artifacts exist. The explicitly
   reported metric can be answered, while derivation/recalculation is
   `insufficient_evidence` with formula representation, derivation objects,
   recalculable data, and per-item predictions named as missing. Overall status
   is `partial`. Removing the last substantive claim answer then demonstrates
   overall `insufficient_evidence`.

The generated files are under `/tmp/claim-coverage-adjudicator-example` by
default, including `main-partial-result.json`, `main-success-result.json`,
`main-success-adjudication.json`, `contradiction-result.json`,
`c02-partial-result.json`, and `c02-insufficient-result.json`. These are runtime
artifacts, not precomputed official outputs. The script exits nonzero on the
first failed assertion.
