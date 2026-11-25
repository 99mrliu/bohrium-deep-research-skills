# Synthetic audit report / 合成审计报告

**SYNTHETIC / 合成示例. This audits a fictional study and authored records.**

## Deterministic results

- Scope records valid: `True`; records=5; evidence items=5; errors=0.
- Claim-audit input valid: `True`; claims=3; errors=0.
- Result contract valid: `True`; case_id=`synthetic-aster17-scope-001`; errors=0.
- Required contract fields, nesting, types, array counts, and `additionalProperties: false` were checked against the supplied synthetic case schema.
- Every scope-record and universal-coverage evidence quotation was checked for exact containment in its named source anchor.

## Universal-claim flags

- C-UNIVERSAL: UNIVERSAL_COUNTEREXAMPLE_FOUND, UNSUPPORTED_GENERALIZATION
- C-BOUNDED: none
- C-SERVICE: none

`UNSUPPORTED_GENERALIZATION` is an expected scientific audit finding, not a malformed-input error. The contrary thin-coupon record prevents the universal from being accepted; the bounded restatement is used in `result.json`.

## Errors and caveats

- Scope errors: []
- Claim-input errors: []
- Contract errors: []
- No automatic semantic validation is claimed. Exact quotation matching does not show that a quotation supports an interpretation.
- The exception search is closed over the supplied synthetic source only; it is not a literature search and cannot prove absence of other exceptions.
- Numeric values are retained as fictional report content, not recomputed. No real paper, comparison set, or external dataset was used.
- Source, uncertainty, and change records are retained inside the contract-permitted result; detailed mesh and this audit are sidecars.
