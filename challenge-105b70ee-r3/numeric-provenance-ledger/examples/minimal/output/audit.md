# Numeric provenance audit

Case: `SYNTHETIC-NUMERIC-LEDGER-MINIMAL`  
Overall status: **answered**  
Field statuses: `{"extraction_failed": 0, "not_reported": 1, "reported": 1, "source_conflict": 1}`

Every reported representation below is copied from selected ledger tokens. Statement-level condition binding is checked mechanically; semantic target matching and absence decisions remain Agent responsibilities.

| Field | Status | Verbatim scalar | Verbatim units | Verbatim statistic | Condition | Comparator | Ledger IDs |
|---|---|---|---|---|---|---|---|
| treatment_response_37c | reported | 4.8 ± 0.3 | mV | — | 37 °C | — | N000005, N000004 |
| recovery_half_time | not_reported | — | — | — | — | — | — |
| replicated_treatment_response_37c | source_conflict | — | — | — | 37 °C | — | N000005, N000016, N000004, N000015, N000017 |

## Evidence and unresolved readings

### treatment_response_37c — reported

Notes: Selected the treated 37 °C statement, not the 25 °C control decoy (N000002).
Primary quote (p-treatment): Under 37 °C, the treated response was 4.8 ± 0.3 mV;
- Evidence 1: source=synthetic-main; page=1; paragraph=p-treatment; tokens=['N000004', 'N000005']
  > Under 37 °C, the treated response was 4.8 ± 0.3 mV;
  Exact spans: `[{"token_id": "N000004", "start": 6, "end": 11}, {"token_id": "N000005", "start": 38, "end": 50}]`

### recovery_half_time — not_reported

Notes: The requested measurement is explicitly absent in the scoped synthetic source; this is not zero or an unreadable value.
Primary quote (p-absence): The study did not report the recovery half-time.
- Evidence 1: source=synthetic-main; page=2; paragraph=p-absence; tokens=[]
  > The study did not report the recovery half-time.
  Exact spans: `[{"start": 0, "end": 48}]`

### replicated_treatment_response_37c — source_conflict

Notes: Both sources use 37 °C and mV but report different exact central values and uncertainties; neither is preferred or averaged.
- Evidence 1: source=synthetic-main; page=1; paragraph=p-treatment; tokens=['N000004', 'N000005']
  > Under 37 °C, the treated response was 4.8 ± 0.3 mV;
  Exact spans: `[{"token_id": "N000004", "start": 6, "end": 11}, {"token_id": "N000005", "start": 38, "end": 50}]`
- Evidence 2: source=synthetic-replication; page=4; paragraph=r-treatment; tokens=['N000015', 'N000016', 'N000017']
  > Under 37 °C, the treated response was 5.0 ± 0.4 mV (Table 2).
  Exact spans: `[{"token_id": "N000015", "start": 6, "end": 11}, {"token_id": "N000016", "start": 38, "end": 50}, {"token_id": "N000017", "start": 52, "end": 59}]`
- Conflict variant 1: scalar='4.8 ± 0.3'; units='mV'; condition='37 °C'; quote=Under 37 °C, the treated response was 4.8 ± 0.3 mV;
- Conflict variant 2: scalar='5.0 ± 0.4'; units='mV'; condition='37 °C'; quote=Under 37 °C, the treated response was 5.0 ± 0.4 mV (Table 2).

## Mechanical boundary

`not_reported` is not inferred by a script from a failed regex match; its coverage quote scopes a human/Agent absence decision. `extraction_failed` names an unreadable or failed operation. `source_conflict` preserves all selected variants without choosing by similarity.

Requested field count: 3. Emitted field count: 3.
