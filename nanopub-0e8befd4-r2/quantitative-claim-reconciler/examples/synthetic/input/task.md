<!-- OUTPUT_CONTRACT_START -->
```json
{
  "required_result_fields": [
    "case_id", "status", "assertion_results", "summary", "sources",
    "uncertainty", "change_records", "run_metadata", "artifacts"
  ],
  "required_calculation_fields": [
    "case_id", "status", "calculations", "direct_assertions",
    "qualitative_assertions", "unresolved", "summary"
  ]
}
```
<!-- OUTPUT_CONTRACT_END -->

# SYNTHETIC task — not an official result

Apply the required output contract exactly. Reconcile only explicit source operands. Preserve direct versus calculated provenance and do not infer unknown numbers.
