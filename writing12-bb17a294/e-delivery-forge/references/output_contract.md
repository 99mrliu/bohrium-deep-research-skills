# Filling `/app/output/result.json` (输出合同填写规范)

## 1. Read the real contract first (先读真合同)

`case.json` carries the case's **actual** `output_contract`. It may be:

- a **list** of field names: `"output_contract": ["deliverable", ...]`
- a **dict** of field → description: `"output_contract": {"deliverable": "...", ...}`
- an object wrapping `fields` / `required` / `required_fields` (list or dict)

`validate_contract.py` discovers field names from whichever shape is
present. **Never assume a fixed schema.** If (and only if) the case file
has NO explicit contract, the documented fallback is this topic's standard
field set:

```
deliverable, fact_source_map, version_boundary, status, sources,
uncertainty, change_log
```

The validator records which origin was used (`explicit` vs `fallback`) in
`contract_check.json` and warns on fallback.

## 2. Field semantics (字段语义)

| Field | Honest content |
|---|---|
| `case_id` | copied verbatim from the case file; a mismatch is a violation |
| `deliverable` | list (or object) of the real deliverable files, paths relative to the output dir |
| `fact_source_map` | mapping of each claim/segment to its source location (upstream fact ledger feeds this; here we only place it) |
| `version_boundary` | version id + scope statement + explicit out-of-scope list (boundary record feeds this) |
| `status` | exactly one of `success` / `partial` / `failed` |
| `sources` | non-empty list of every input actually used |
| `uncertainty` | what is missing or unsure, and why; empty string only when truly nothing |
| `change_log` | list of change records (stage → detail); `change_log.md` mirrors it |

## 3. Honesty rules (诚实规则)

- **Every contract field must be present and non-null** — with ONE
  exception: when `status` is `partial` or `failed`, a field may be
  null/empty **only if that gap is named inside `uncertainty`** (the
  validator string-matches the field name there).
- `status: "success"` means: all gates passed, nothing is missing. Do not
  claim success with an open gap.
- Every file referenced anywhere in `result.json` (except provenance/prose
  fields `sources`, `uncertainty`, `change_log`, `case_id`) must **exist**
  in the output dir; the validator checks this. So list only files you
  actually wrote.
- Never fabricate missing software state, previews, or scientific data.

## 4. Early partial save + atomic updates (早期部分保存与原子更新)

1. **Before** any long work, write a valid partial `result.json`: real
   `case_id`, all contract fields present (empty lists/objects where not
   done yet), `status: "partial"`, `uncertainty` naming what is pending,
   `sources` listing inputs read so far.
2. **After each stage** (translation section, render, census, contract),
   rewrite it: build the new JSON in memory → write
   `result.json.tmp` → `os.replace("result.json.tmp", "result.json")`.
   Atomic replace means a crash never leaves a torn file.
3. The final write sets the honest terminal `status` and the complete
   change records, then `validate_contract.py` is the last gate.

```python
import json, os
def atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```
