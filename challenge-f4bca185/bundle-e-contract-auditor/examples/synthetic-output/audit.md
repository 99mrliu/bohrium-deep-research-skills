# Contract audit report

- case_id: `synthetic-contract-auditor-v1`
- status: `partial`
- deterministic rules: schema S001-S004, values V001-V004, units U001-U004, identity D001-D003, coverage C001

## Coverage reconciliation

| input rows | kept | flagged | deduplicated | rejected | cleaned rows |
|---:|---:|---:|---:|---:|---:|
| 8 | 1 | 6 | 1 | 0 | 7 |

Every input row has exactly one disposition. `flagged` rows remain in the statistical table; `deduplicated` and `rejected` rows are excluded only with the reason in `result.json.coverage.rows`.

## Severity ledger

| severity | count | meaning |
|---|---:|---|
| blocking | 0 | delivery cannot be treated as complete; result is input_error/partial and verifier exits nonzero if the failure is in the artifacts |
| error | 6 | a cell/row requires correction or reviewed configuration; row remains flagged when retained |
| warning | 1 | usable but uncertain; review queue entry required |
| info | 1 | deterministic no-loss action such as exact duplicate removal |

## Anomalies

| anomaly | severity | code | row | field | message |
|---|---|---|---|---|---|
| A000001 | error | MALFORMED_NUMBER | R000002 | value | numeric value could not be parsed; original text is retained only in raw_value |
| A000002 | error | UNKNOWN_UNIT | R000003 | unit | unit is not in the deterministic registry; normalized value remains null |
| A000003 | info | EXACT_DUPLICATE_REMOVED | R000004 | record_id | duplicate extraction removed by record_id plus full-context identity key |
| A000004 | warning | MISSING_VALUE | R000005 | value | numeric value is missing and remains null |
| A000005 | error | UNMAPPED_COLUMN | R000006 | Lab Note | column has no deterministic mapping and was retained with an unmapped__ prefix |
| A000006 | error | DUPLICATE_ID_CONFLICT | R000007 | record_id | same record_id has different scientific/context values; rows were kept separate and never merged |
| A000007 | error | UNMAPPED_COLUMN | R000007 | Lab Note | column has no deterministic mapping and was retained with an unmapped__ prefix |
| A000008 | error | UNMAPPED_COLUMN | R000008 | Lab Note | column has no deterministic mapping and was retained with an unmapped__ prefix |

## Review queue

Open items: 7. The queue is deliberately separate from the statistical table so uncertain values are not silently consumed.

## Artifact integrity

`checksums.sha256` covers the payload files. `manifest.json` records sizes and hashes and explicitly excludes only itself and the verification report; run `verify` after moving or editing any artifact.
