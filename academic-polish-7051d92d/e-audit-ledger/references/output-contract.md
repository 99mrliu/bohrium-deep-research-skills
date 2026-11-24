# Output-contract mirroring (result.py)

Hand-writing contract fields is the biggest structural risk in this contest:
field names and types differ per case, and a hand-written result.json drifts
from the case's real `output_contract`. The two-step cure:

1. `result.py result-skeleton --case case.json --out skeleton.json` — builds
   the skeleton from the **real** case.json, preserving every nested key and
   declared type.
2. `result.py validate-result --case case.json --result result.json` — checks
   required fields, types and `case_id` consistency (exit 1 on any failure).

`fill-result` additionally maps produced artifacts onto contract fields so the
filled result can be validated immediately.

## Contract dialect

```json
"output_contract": {"fields": {
  "polished_text": {"type": "string", "required": true,
                    "aliases": ["polished", "final_text"],
                    "description": "..."},
  "uncertainty":   {"type": ["string", "null"], "required": true}
}}
```

- `type`: string or list of strings (`string | array | object | number |
  integer | boolean | null`). A list is a union — any listed type passes.
- `required`: default true.
- `aliases`: alternative names a case might use for the same concept.
- A bare `{name: spec}` `output_contract` (no `fields` wrapper) is also
  accepted.

## Alias table and type coercion

`fill-result` resolves fields through a canonical artifact map
(`polished_text`→`polished.md`, `changes`→`changes.json` entries,
`review_html`→`review.html`, `change_log`→`change-log.md`,
`status`→derived, `uncertainty`→null). A field matches a canonical name when
its own name **or any alias** matches (case-insensitive).

Coercion is best-effort and always recorded in `notes`:

- value is `list`/`dict` but contract says `string` → JSON-serialize;
- value is `string` but contract says `array`/`object` → try `json.loads`;
- value is `string` but contract says `number` → try `float`;
- otherwise the value is left as-is and validation decides.

## Three-state semantics for every field

| state | meaning | rule |
|---|---|---|
| filled | real content mapped from a produced artifact | preferred |
| null + note | field exists in the contract but nothing real maps to it | write `null`, add a `notes` entry naming the field — **honest null** |
| fabricated | invented content to make the field look complete | **forbidden** |

`validate-result` fails a required field that is `null` without a `notes`
entry explaining it, and fails any missing required field or type mismatch.

## Honesty keys (always present)

- `status`: `success | partial | blocked`. `partial` must enumerate concrete
  limitations in `notes`; `blocked` must not ship fabricated body text.
- `sources`: what was actually read.
- `uncertainty`: residual doubts (e.g. notation the token patterns may miss),
  or `null` when the contract allows it.
