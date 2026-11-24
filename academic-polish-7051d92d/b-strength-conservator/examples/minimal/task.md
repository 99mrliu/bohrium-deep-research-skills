# Task (SYNTHETIC example / 合成示例)

Polish the English biomedical abstract in `source.md` for grammar and
readability. The abstract contains at least six grammar defects.

Hard constraints:

1. Fix grammar, agreement, tense and countability errors.
2. Do NOT change the author's claim strength: hedges (`may`, `suggest`),
   quantifier scope (`some`, `several`), negation scope (`did not reach`),
   causality framing (`is associated with`, NOT `causes`), and scope
   conditions (`in vitro`, `in vivo`, `in this cohort`, `in human samples`)
   must all survive editing.
3. Every edit must be reviewed (decision + reason) before it is applied.
4. Any intentional strength change requires explicit authorization
   (`strength_change.authorized_by`: `task` or `user`, plus an explanation).
5. Deliver the full polished text, the per-unit change record, a strength
   audit, and a conservation report; mirror the `output_contract` in
   `case.json` into `result.json`.
