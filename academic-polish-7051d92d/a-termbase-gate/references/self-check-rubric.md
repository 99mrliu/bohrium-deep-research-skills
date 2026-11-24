# Self-Check Rubric — 改得对 / 说得像 / 没改坏 / 讲得清

Run this checklist before finalizing `result.json`. Every "no" is either a
fix or an honest entry in `uncertainty`. Machine gates answer some items
automatically — the rest are yours.

## 1. 改得对 (real fixes, not cosmetic reshuffling)

- [ ] Every error-level finding of the baseline `lint` is either fixed in
      `polished.md` or explicitly listed as unresolved in `uncertainty`.
- [ ] Each applied edit maps to a genuine defect (terminology, grammar,
      collocation, register), not a synonym swap that hides the problem.
- [ ] Abbreviations are defined exactly once, at true first use, in the
      `Full Name (ABBR)` form — verified by the post-edit `lint` (0 errors).
- [ ] No banned variant survives anywhere, including headings, captions,
      and the conclusion.

## 2. 说得像 (register and uniformity)

- [ ] One canonical surface per concept across ALL sections (the
      cross-section drift check passes).
- [ ] Sentence-initial capitalization and heading title-case are the only
      casing deviations, and they are the tolerated ones.
- [ ] The text still sounds like the target genre (journal abstract /
      thesis / grant); terminology fixes did not make sentences wooden.
- [ ] Final full read-through done with your own eyes — the gate proves
      uniformity, not elegance.

## 3. 没改坏 (nothing silently broken)

- [ ] `audit.json` shows `reverted_protected_token_lost` applied to every
      edit that dropped a number+unit / citation / Fig./Eq. / URL / DOI;
      none of those edits slipped through.
- [ ] Numbers, units, citation markers, and figure/equation pointers in the
      polished text match the source one-to-one (spot-check at least the
      edited units).
- [ ] Claim strength, negation, and causality were NOT altered — the
      protected-token gate does not cover these; check by reading.
- [ ] Re-running the whole pipeline on the same input reproduces identical
      artifacts (determinism), and re-linting the polished text yields 0
      mandatory fixes (idempotence).

## 4. 讲得清 (auditable by a third party)

- [ ] Every change in `changes.json` has: unit id, original text, new text,
      change type, reason, and a review record (decision + reason).
- [ ] Reverted edits are visible with their revert reason (missing review,
      lost protected token) — nothing was silently dropped.
- [ ] `terminology-report.md` shows the locked termbase, conflicts (or
      their absence), and the full-text lint outcome.
- [ ] `result.json` mirrors the case `output_contract`, passes
      `validate-result`, and its `status`/`uncertainty`/`notes` honestly
      describe limits (unregistered terms, unresolved conflicts, partial
      coverage).
