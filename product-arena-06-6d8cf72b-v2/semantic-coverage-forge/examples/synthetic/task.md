# SYNTHETIC task — semantic coverage auditor example

All content is fictional and for software testing only. Read `case.json` and all of
`source.json`. Answer exactly the following three QA tasks using only that excerpt.

1. **Q1:** At 12 weeks, what mean orientation score did the authors report, and was that
   number author-reported or calculated from the excerpt?
2. **Q2:** In Table 1 at the Reed site, how did Compass A's mean completion time compare
   with Compass B's, including the exploratory/unadjusted conditions and units, and can the
   comparison be generalized to other sites?
3. **Q3:** What 95% confidence interval is reported for the 12-week mean orientation score?

For Q3, do not convert SEM into a confidence interval. If the interval is not reported, use
`not_reported`, leave `evidence` empty, and enumerate the checked source scope in
`checked_scope`. `not_reported` applies only to this supplied excerpt.

## output_contract

`result.json` must contain `case_id` and exactly Q1, Q2, and Q3. Every nested object is
closed. Evidence is required for `answered` rows by the semantic plan, not fabricated for
`not_reported`. The Q2 difference may be derived from reported inputs but must not be called
an author-reported difference.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["case_id", "Q1", "Q2", "Q3"],
  "properties": {
    "case_id": {"type": "string", "const": "synthetic-lumenfen-semantic-coverage-001"},
    "Q1": {
      "type": "object",
      "additionalProperties": false,
      "required": ["item_id", "question", "answer", "status", "evidence", "checked_scope"],
      "properties": {
        "item_id": {"type": "string", "const": "Q1"},
        "question": {"type": "string", "minLength": 1, "maxLength": 500},
        "answer": {"type": "string", "minLength": 1, "maxLength": 900},
        "status": {"type": "string", "enum": ["answered", "not_reported", "unreadable", "missing"]},
        "evidence": {
          "type": "array",
          "minItems": 0,
          "maxItems": 4,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["evidence_id", "source_id", "anchor", "quote", "evidence_role"],
            "properties": {
              "evidence_id": {"type": "string", "minLength": 1, "maxLength": 60},
              "source_id": {"type": "string", "const": "SYNTH-LUMENFEN-2026"},
              "anchor": {"type": "string", "enum": ["S1", "S2", "T1"]},
              "quote": {"type": "string", "minLength": 1, "maxLength": 1200},
              "evidence_role": {"type": "string", "enum": ["author_reported", "formula_derived_from_reported", "mixed", "context_only"]}
            }
          }
        },
        "checked_scope": {"type": "string", "minLength": 20, "maxLength": 1200}
      }
    },
    "Q2": {
      "type": "object",
      "additionalProperties": false,
      "required": ["item_id", "question", "answer", "status", "evidence", "checked_scope"],
      "properties": {
        "item_id": {"type": "string", "const": "Q2"},
        "question": {"type": "string", "minLength": 1, "maxLength": 500},
        "answer": {"type": "string", "minLength": 1, "maxLength": 900},
        "status": {"type": "string", "enum": ["answered", "not_reported", "unreadable", "missing"]},
        "evidence": {
          "type": "array",
          "minItems": 0,
          "maxItems": 4,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["evidence_id", "source_id", "anchor", "quote", "evidence_role"],
            "properties": {
              "evidence_id": {"type": "string", "minLength": 1, "maxLength": 60},
              "source_id": {"type": "string", "const": "SYNTH-LUMENFEN-2026"},
              "anchor": {"type": "string", "enum": ["S1", "S2", "T1"]},
              "quote": {"type": "string", "minLength": 1, "maxLength": 1200},
              "evidence_role": {"type": "string", "enum": ["author_reported", "formula_derived_from_reported", "mixed", "context_only"]}
            }
          }
        },
        "checked_scope": {"type": "string", "minLength": 20, "maxLength": 1200}
      }
    },
    "Q3": {
      "type": "object",
      "additionalProperties": false,
      "required": ["item_id", "question", "answer", "status", "evidence", "checked_scope"],
      "properties": {
        "item_id": {"type": "string", "const": "Q3"},
        "question": {"type": "string", "minLength": 1, "maxLength": 500},
        "answer": {"type": "string", "minLength": 1, "maxLength": 900},
        "status": {"type": "string", "enum": ["answered", "not_reported", "unreadable", "missing"]},
        "evidence": {
          "type": "array",
          "minItems": 0,
          "maxItems": 4,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["evidence_id", "source_id", "anchor", "quote", "evidence_role"],
            "properties": {
              "evidence_id": {"type": "string", "minLength": 1, "maxLength": 60},
              "source_id": {"type": "string", "const": "SYNTH-LUMENFEN-2026"},
              "anchor": {"type": "string", "enum": ["S1", "S2", "T1"]},
              "quote": {"type": "string", "minLength": 1, "maxLength": 1200},
              "evidence_role": {"type": "string", "enum": ["author_reported", "formula_derived_from_reported", "mixed", "context_only"]}
            }
          }
        },
        "checked_scope": {"type": "string", "minLength": 20, "maxLength": 1200}
      }
    }
  }
}
```
