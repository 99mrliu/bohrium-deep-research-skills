# Task (synthetic example / 合成示例)

Polish the manuscript draft in `source.md` (a synthetic electrochemistry
short communication). You must:

1. Enforce the case-provided glossary (`case.json -> materials.glossary`):
   unify every term to its canonical form, eliminate banned variants, and
   keep abbreviation usage consistent with `first_use_policy`.
2. Fix language-level problems (grammar, concision) with **minimal edits**;
   do not alter any number, unit, citation marker, or figure/equation
   reference.
3. Deliver a complete polished text plus a per-sentence change record
   (original, revised, change type, reason, review decision) that a third
   party can audit.
4. Produce a terminology consistency report covering the whole text,
   including cross-section drift.
5. Write `result.json` mirroring every field of `output_contract` in
   `case.json`, with an honest `status` and `uncertainty`.

Everything in this directory is a **synthetic example** produced to
demonstrate the skill pipeline; it is not a formal evaluation result.
