# Edit-mode versioning and change discipline

For any case that supplies a starting deck, the task is a controlled modification, not a rebuild. The goal: a reviewer can diff any two rounds and roll back to any state.

## Snapshot protocol

1. `/app/work/versions/v0_original.pptx` — untouched copy of the starting deck, SHA-256 recorded in `changelog.md`.
2. One revision round = one snapshot: `v1.pptx`, `v2.pptx`, … A round is a coherent set of edits answering one instruction, not one file save per action.
3. The deliverable is a copy of the last snapshot at the contract's output path; the snapshots stay in `/app/work` and the final one is also hashed into `result.json`.

## Changelog format (`/app/work/changelog.md`)

```
## v1 (round 1): compress methods 3 slides -> 2, per work order item 2
- slides touched: 4,5 (merged into new 4; old 5 removed)
- what: moved eq. block to backup; condensed bullet list; kept Figure 3 crop
- why: mandated slide count 8 -> 7 for methods section
- rollback: cp versions/v0_original.pptx ... (or v1->v0 diff is slides 4-5 only)
- verification: reopened; slide 4 layout 'Title and Content' on master 'Office Theme'; notes preserved
```

Every round lists touched slide indices, the instruction that authorized the change, and the verification performed after saving. A change without an authorizing instruction does not happen.

## Preservation guarantees (assert after every save)

- Untouched slides: count and order of the untouched set unchanged; spot-compare text of two untouched slides against `v0_original`.
- Masters/layouts: every slide's `slide_layout` name and its master match the pre-edit inspection, except slides the work order explicitly re-templates.
- Notes: preserved on untouched slides; updated only where the slide changed.
- Media: picture count per untouched slide unchanged (guards against silent image loss on save).

## Conflict handling

- Starting deck and a *separate* mandated target template: inspect both masters first. If python-pptx cannot apply the target layouts safely, do not fake inheritance — rebuild content on the target template only if the work order authorizes it, else report the incompatibility in `result.json.exceptions` with both inspection reports attached and deliver the best usable deck.
- Work order edits that contradict preservation rules (e.g. "restyle everything" + "keep slide 3 untouched"): follow the more specific instruction, record the interpretation in the changelog.
- If a round breaks the deck (corrupt save, lost master), roll back to the previous snapshot and redo the round in smaller steps; the failed attempt is logged, not deleted.
