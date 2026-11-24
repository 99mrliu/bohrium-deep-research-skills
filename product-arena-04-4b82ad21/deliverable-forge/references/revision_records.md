# Revision records

When the task is a revision, the change trail is a deliverable in its own
right: it is what lets a reviewer trust that the edit did what it claims and
nothing else.

## Record shape

```json
{"id": "chg3", "type": "modified",
 "old": "<sentence(s) before>", "new": "<sentence(s) after>",
 "location": "sentence block 7->7",
 "rationale": "corrected attribution: recall gain belongs to pooling, precision stayed flat"}
```

- `type`: `added` | `modified` | `deleted`.
- `old` / `new`: sentence-level text (empty on the side that did not exist).
- `location`: where in the manuscript the edit sits.
- `rationale`: the reason, in one sentence. `change_record.py` flags records
  whose rationale is still the `<TODO>` placeholder — an edit without a
  stated reason is not reviewable.

## Discipline

1. **One rationale per semantic edit, not per keystroke.** Batch purely
   mechanical edits (renumbering, whitespace) into one record with a mechanical
   rationale.
2. **Classify the edit honestly.** Copy edits (grammar, style, compression)
   must not change meaning. Scientific corrections (attribution, numbers,
   scope) must be labeled as corrections — they change what the manuscript
   claims and a reviewer must be able to find them first.
3. **Preserve intent.** After recording, re-read each modified pair and
   confirm: same modality (is/may), same causal strength (shows/suggests),
   same comparison conditions (same benchmark, same metric), same attribution
   targets — unless the edit exists precisely to fix one of those, in which
   case the rationale says so.
4. **Deletions need the strongest reasons.** Record what was removed and why
   (over budget, unsupported, duplicated). Silent deletion of a limitation or
   a counterexample is the worst revision failure.
5. The `changes` array in `result.json` comes from these records; open items
   that motivated edits stay in `open_items` until resolved, then their
   resolution is itself a change record.

## Anti-patterns (synthetic)

- "Improved the related work section." — not a rationale; name what changed
  and why.
- A 40-record diff where 36 records are renumbering — batch them.
- A modified pair where the new sentence upgrades "suggests" to
  "demonstrates" with no new evidence — an intent change smuggled in as a
  copy edit; revert or label as a scientific correction with its basis.
