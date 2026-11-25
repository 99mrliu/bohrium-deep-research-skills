# result.json contract notes

`structure_report.py` reads the case file (`--case case.json`) and produces a
contract-aware `result.json`.

## Case file shape

```json
{
  "case_id": "synthetic-mini-001",
  "output_contract": {
    "toc": "...description...",
    "references": "...",
    "captions": "...",
    "structure_issues": "...",
    "uncertainty": "..."
  }
}
```

`output_contract` is a dict: each key is a required output field. Any key is
allowed; the five above have built-in producers.

## result.json shape

| key | meaning |
|---|---|
| `case_id` | copied verbatim from the case file (null only when `--case` missing) |
| `status` | `success` = every contract field produced; `partial` = some field empty or no case file; `failed` = neither headings/toc nor references could be produced |
| `output_contract` | echoed verbatim |
| `outputs.<field>` | `{status: ok, data: ...}` or `{status: empty, explanation, data: null}` — unknown contract fields are reported empty-with-explanation, never dropped |
| `findings` | counts: heading inconsistencies, both caption gaps, raw references |
| `sources` | basenames of all inputs consumed |
| `uncertainty` | free-text caveats (raw refs, heuristic leveling, caption misread risk) |
| `change_record` | ordered pipeline steps: heading_tree → refs_parse → structure_report, each consumed/produced/missing |

## Honesty rules

1. Never omit a contract field — an empty field with an explanation is a
   valid deliverable; a silently missing field is not.
2. `status` describes contract fulfillment, not paper quality: planted
   numbering gaps or raw references are *findings*, they do not downgrade a
   `success`.
3. `references.raw` count > 0 is surfaced in `uncertainty` so consumers know
   verbatim entries exist.
4. Outputs embed only data actually produced by the scripts in this run
   (paths are passed explicitly; nothing is regenerated from memory).
