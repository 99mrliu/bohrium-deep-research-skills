# Contract audit report

- case_id: `None`
- status: `input_error`
- deterministic rules: schema S001-S004, values V001-V004, units U001-U004, identity D001-D003, coverage C001

## Coverage reconciliation

| input rows | kept | flagged | deduplicated | rejected | cleaned rows |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 0 | 0 |

Every input row has exactly one disposition. `flagged` rows remain in the statistical table; `deduplicated` and `rejected` rows are excluded only with the reason in `result.json.coverage.rows`.

## Severity ledger

| severity | count | meaning |
|---|---:|---|
| blocking | 1 | delivery cannot be treated as complete; result is input_error/partial and verifier exits nonzero if the failure is in the artifacts |
| error | 0 | a cell/row requires correction or reviewed configuration; row remains flagged when retained |
| warning | 0 | usable but uncertain; review queue entry required |
| info | 0 | deterministic no-loss action such as exact duplicate removal |

## Anomalies

| anomaly | severity | code | row | field | message |
|---|---|---|---|---|---|
| A000001 | blocking | INPUT_CASE_INVALID |  |  | Expecting property name enclosed in double quotes: line 6 column 3 (char 122) |

## Review queue

Open items: 1. The queue is deliberately separate from the statistical table so uncertain values are not silently consumed.

## Artifact integrity

`checksums.sha256` covers the payload files. `manifest.json` records sizes and hashes and explicitly excludes only itself and the verification report; run `verify` after moving or editing any artifact.
