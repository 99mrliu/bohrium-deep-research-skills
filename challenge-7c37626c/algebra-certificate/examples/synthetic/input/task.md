# Fully synthetic algebra-certificate demonstration

This is executable package test data, **not formal/platform data** and not C01/C02/C03 case material. It does not emulate a paper answer. The agent-authored synthetic answers and transition list are stored beside this task.

```json
{
  "case_id": "synthetic-algebra-certificate-001",
  "output_contract": {
    "required_fields": ["case_id", "status", "answer", "derivation_summary", "certificate_summary"],
    "field_types": {
      "case_id": "string",
      "status": "string",
      "answer": "string",
      "derivation_summary": "string",
      "certificate_summary": "string"
    },
    "status_enum": ["success", "partial", "failed"]
  }
}
```
