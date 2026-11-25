# Synthetic quantity challenge

Recalculate the explicitly synthetic reported energy interval and run only the independently authored invariants. Keep injected-fault diagnoses separate from the source-claim verdict. This example does not describe a real paper.

## Output contract

```json
{
  "required_fields": [
    "case_id",
    "status",
    "answers",
    "artifacts",
    "source_claim_verdict",
    "diagnostic_fault_injection_verdict"
  ],
  "field_types": {
    "case_id": "string",
    "status": {"type": "string", "enum": ["completed", "partial", "failed"]},
    "answers": {
      "type": "object",
      "required_fields": ["reproduction", "metamorphic_assessment", "fault_diagnosis", "limitations"],
      "field_types": {
        "reproduction": "string",
        "metamorphic_assessment": "string",
        "fault_diagnosis": "string",
        "limitations": "string"
      }
    },
    "artifacts": {"type": "array", "items": {"type": "string"}},
    "source_claim_verdict": "string",
    "diagnostic_fault_injection_verdict": "object"
  },
  "status_enum": ["completed", "partial", "failed"]
}
```
