<!-- OUTPUT_CONTRACT_START -->
```json
{"required_result_fields":["case_id","status","assertion_results","summary","sources","uncertainty","change_records","run_metadata"],"required_calculation_fields":["case_id","status","calculations","direct_assertions","qualitative_assertions","unresolved","summary"]}
```
<!-- OUTPUT_CONTRACT_END -->

# SYNTHETIC negative fixture: zero denominator

Expected behavior: preserve partial artifacts, leave the failed value pending, and exit 2.
