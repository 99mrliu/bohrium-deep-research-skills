# Reading case.json and Filling result.json

## Reading the case

`/input/case.json` is authoritative; `/input/task.md` is the human-readable restatement.
Read both files. `scaffold_output.py` automates the tolerant parse:

- `case_id`: first of `case_id` / `caseId` / `id` / `name`.
- Required output fields: `output_contract.required_fields` (also tolerates `required`,
  `fields`, `requiredFields`, `outputs`; list-of-strings or list-of-dicts with
  `name`/`field`/`key`/`id`).
- Constraints: `constraints.{audience,duration_minutes,slide_limit,language,template_path,
  starting_deck}` or the same keys at top level; slide limit may also be hinted in task.md
  ("12 slides", "12页").

**The case's own `output_contract` wins over any default.** If the contract names a field
`slide_deck_path`, that field must appear in result.json — even if this skill's examples use
different names.

## Field-mapping rules

1. Every required contract field → a real value of a plausible JSON type, derived from the
   actual artifacts (e.g. path strings point at files that exist; counts match the deck).
2. Before a field is truly filled, its value is the scaffold placeholder
   `{"status": "pending", "detail": "..."}`. Validate warns while placeholders remain.
3. Never invent values to silence the warning — a pending placeholder is honest and scores
   partial; a fabricated value is disqualifying.
4. Extra informative fields are allowed (slide_count, deck_path, preview_dir, etc.) unless
   the contract forbids extras.

## Status taxonomy

| status | When |
|---|---|
| `success` | All contract fields filled with real content; deck validated; render verified (or case didn't require it); no unresolved placeholders. |
| `partial` | Anything less, but a valid deliverable set exists: placeholders remain, render unavailable, template ignored, slide limit forced drops. **The limits must be enumerated in `uncertainty`.** |
| `unable_to_determine` | Content could not be extracted at all (encrypted/image-only PDF without OCR, missing paper). Skeleton still delivered. |

## Honesty rules

- Never fabricate paper content, figure/table numbers, metric values, software state
  ("rendered OK" when soffice was missing), or scores.
- Numbers on slides are verbatim from the paper and carry a §/Fig./Table anchor (slide footer).
- `sources`: list what was actually used — paper path, template path, tool names/versions
  (render manifest has them), starting deck if adapted.
- `uncertainty`: each entry a concrete limit, e.g.
  "Render verification not performed: LibreOffice unavailable in environment (see
  render_manifest.json).", "Slide 6 evidence values pending verification against Table 2.",
  "Organizer template not honored: python-pptx unavailable; stdlib skeleton used."
- A partial result must identify its limits; silently downgrading is worse than a loud
  `partial`.

## Change record

`result.json.change_record` is an append-only list of dated entries describing what the run
did to the deliverables. Format:

```json
"change_record": [
  {"ts": "2026-01-01T00:01:12+00:00", "phase": "P0", "action": "scaffold",
   "detail": "valid partial result.json + 9-slide stdlib skeleton created"},
  {"ts": "2026-01-01T00:04:40+00:00", "phase": "P2", "action": "patch_slide",
   "detail": "slide 2 (problem) filled from §1; footer anchor §1"},
  {"ts": "2026-01-01T00:12:03+00:00", "phase": "P2", "action": "compress_plan",
   "detail": "50% time checkpoint fired; dropped backup + limitations slides (9→7)"},
  {"ts": "2026-01-01T00:13:50+00:00", "phase": "P3", "action": "render",
   "detail": "soffice unavailable; manifest status renderer_unavailable; disclosed"}
]
```

One entry per phase-level action is enough; do not log every micro-edit.
