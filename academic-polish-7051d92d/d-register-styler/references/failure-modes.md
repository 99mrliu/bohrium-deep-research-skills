# Failure modes — register-styler

Real failure modes this skill is designed to catch, and the mitigation each
mechanism provides.

1. **Genre misdetection → wrong rule set applied.**
   A grant proposal polished like a journal abstract (or vice versa) is the
   core failure this bundle exists for. Mitigation: `register.py detect`
   prefers explicit task declarations, scores text signals, and reports
   `unknown` with `needs_confirmation=true` instead of guessing; `lint`
   *refuses* to run on `unknown` (exit 2). The agent must confirm the genre
   with the user and state the confirmation in its notes.

2. **Lint over-flagging (false positives).**
   Heuristic patterns hit legitimate usage: Roman-numeral “I”, possessive
   `'s`, 特别是, mathematical “never”. Mitigation: taxonomy boundaries in
   `register-taxonomy.md`; the agent adjudicates every hit and records keep/
   change decisions in the edit `reason`. Never bulk-rewrite from lint output.

3. **Lint under-flagging (false negatives).**
   No pattern list catches context-dependent hype (“our elegant framework”).
   Mitigation: machine gates only prove “not worse”; SKILL.md reserves budget
   for a final human-style read-through against `style-guides.md`.

4. **Scorecard gaming.**
   Deleting flagged sentences (or gutting claims) makes violations drop while
   destroying content. Mitigation: the scorecard is a *necessary, not
   sufficient* gate; protected-token guard keeps numbers/citations/figure
   pointers; minimal-edit principle; every deletion-level rewrite must be
   justified in `reason` and passes the review gate.

5. **Unreviewed edits silently applied.**
   Mitigation: `pipeline.py apply-edits` reverts any edit without
   `review.decision=approve` and a non-empty `review.reason`
   (`reverted-unreviewed`). The gate is not optional.

6. **Protected-token drift.**
   Register rewrites love to drop “12.5%”, “[7]”, “Figure 2”. Mitigation:
   per-unit protected tokens are frozen in `prepare`; `apply-edits` reverts
   edits that lose any of them (`reverted-protected-token`).

7. **Sentence-splitter errors.**
   Decimals (“12.5%”) and abbreviations (“Fig. 2”, “et al.”) can split
   mid-sentence. Mitigation: splitter guards in `pipeline.py`; the agent
   should sanity-check `unit_count` against a quick read and, if a split is
   wrong, edit at the paragraph level instead of fighting unit IDs.

8. **Register fixes that change claim strength.**
   “彻底解决问题” → “解决问题” silently *weakens* the claim; usually that is
   the *point* (de-absolutizing), but it must be explicit. Mitigation: any
   strength-changing edit states so in `reason`/`review_reason`; deep
   strength conservation is direction B's focus — here we only promise the
   change is declared, never silent.

9. **Multi-genre documents.**
   A thesis with an English abstract, or a response letter containing quoted
   comments, mixes registers. Mitigation: split the document by section and
   run detect/lint per section; quoted blocks are excluded as data.

10. **“Polished gets more colloquial.”**
    Synonym-swapping models sometimes drift informal (“obtain” → “get”).
    Mitigation: the scorecard gate exits non-zero whenever after-violations
    exceed before-violations, so the regression is caught before export.
