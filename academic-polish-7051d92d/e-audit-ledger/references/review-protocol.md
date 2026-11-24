# Review protocol (gate C04)

Review is **mandatory and not skippable**. An edit without a valid review
record is rolled back automatically by `ledger.py review`; so is an edit whose
hash no longer matches (stale). There is no "guard passed → auto-apply"
shortcut — a previous submission lost points for exactly that shortcut.

## Review record format

```json
{"reviews": [
  {"edit_id": "s0003-1a2b3c4d5e", "decision": "accept",
   "reason": "Re-read against frozen sentence: article fix is correct and minimal."}
]}
```

- `decision` ∈ `accept` | `reject` | `query`.
- `reason` ≥ 8 chars, concrete. "ok" is not a review.
- `edit_id` comes from `intake-report.json` — copy it, never retype.

## Per-edit checklist (re-read the frozen sentence, never review from memory)

For each accepted edit, in this order:

1. **Anchor**: open the frozen sentence (sXXXX in `job/state.json` or the
   intake report) and read `original` against it — character by character if
   the sentence carries tokens.
2. **Correctness**: is the diagnosed defect real? Consult
   `references/edit-taxonomy.md` for the type definition.
3. **Minimality**: does `revised` change only what the defect requires? Flag
   gratuitous rewording with a `query`.
4. **Conservation**: compare numbers, units, %, p-values, citations, figure
   pointers between original and revised. The machine gate C03 checks too, but
   the reviewer is responsible for notation the patterns miss (e.g. "κ = 0.8",
  "1H NMR").
5. **Strength & meaning**: claim strength, negation, conditionality and scope
   must be unchanged unless the edit is typed `hedging` with a cited basis.
6. **Decision**: `accept` only when 1–5 all pass; `reject` when the edit is
   wrong; `query` when anything is unclear — a query holds the edit back, it is
   never silently applied.

## Batch review etiquette

- Review in sid order; do not skip "obvious" edits — the rolled-back demo edit
  in `examples/minimal` is an "obvious" semicolon tweak, and the gate still
  (correctly) rolls it back when unreviewed.
- If you regenerate or modify an edit batch after reviewing, **re-review**:
  the hash changes and old records become stale by design.
- Invalid review records (bad decision value, short reason) are listed in
  `review-report.json` under `invalid_review_records` and count as no review.

## What the gate guarantees — and what it does not

The gate guarantees every applied edit was anchored, token-conserving and
explicitly reviewed. It does **not** guarantee the review itself was wise.
`review.html` exists so a human can re-do this checklist cheaply; treat it as a
self-check tool, not as a substitute for peer review.
