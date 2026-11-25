# Semantic review checklist

Use this checklist after a complete draft exists and before the schema gate. Record each
finding against an answer-matrix `item_id` and JSON Pointer. A check can be machine-assisted,
but semantic acceptance requires human judgment; an exact quotation is not automatic proof
of truth or whole-answer entailment.

## A. Obligation and direct-answer review

- [ ] Every explicit question and subquestion appears once in the answer matrix.
- [ ] Conjoined obligations (value + interpretation, comparison + generalizability, etc.)
      have been split or explicitly covered in one row.
- [ ] Every required contract field maps to a question, case metadata obligation, or other
      explicit deliverable requirement; no required field is silently ornamental.
- [ ] The first sentence of each answer directly answers the question before citation or
      background.
- [ ] The user need not calculate a requested comparison or infer a negative from sources.
- [ ] The requested language, precision, and level of detail are respected.

## B. Qualifier, comparator, negation, and condition review

- [ ] Population, site, sample/analysis set, time point, intervention/exposure, endpoint,
      table/figure/section, dose, and follow-up are preserved where relevant.
- [ ] Qualifiers such as `only`, `exploratory`, `unadjusted`, `adjusted`, `reported`,
      `estimated`, `may`, and `among` are attached to the clauses they constrain.
- [ ] Comparator direction and baseline are explicit; absolute and relative differences are
      not interchanged.
- [ ] Values include their units, denominators, and rounding context where requested.
- [ ] Negations, exclusions, exceptions, and limiting clauses survive paraphrase/translation.
- [ ] Non-significance is not rewritten as equivalence or proof of no effect.
- [ ] Table-specific and subgroup-specific results remain restricted to that exact scope.

## C. Whole-answer evidence-entailment review

For every material clause, ask “which exact words in this quote support this clause?”

- [ ] The evidence `source_id` and `anchor` are correct, the quote occurs there verbatim,
      and that exact pair is inside the row's declared `checked_source_scope`.
- [ ] The quote supports the values, units, population, time, conditions, comparator, and
      direction in the answer—not just the broad topic.
- [ ] Multiple clauses have joint coverage; one supporting quote is not treated as support
      for every clause.
- [ ] Context-only evidence is not presented as outcome support.
- [ ] Quotation ellipses or selective extraction do not remove a limiting condition.
- [ ] The answer does not introduce causality, statistical significance, safety, efficacy,
      or universality beyond the source.
- [ ] If the source and answer disagree, the answer is corrected or the uncertainty is made
      explicit; the citation is not used to launder the mismatch.

## D. Derived values and conflicts

- [ ] Author-reported numbers are identified as reported where that distinction matters.
- [ ] Every calculated number has a formula, quoted inputs, compatible units, and stated
      rounding in the matrix or allowed output field.
- [ ] A derived number is not called an author-reported result.
- [ ] Derived uncertainty intervals are not invented when a reported interval was requested.
- [ ] Conflicting passages/sources are represented two-sidedly with values and source scope.
- [ ] Different populations, times, definitions, and units are checked before declaring a
      true conflict.
- [ ] Adjudication, if requested, explains its basis and residual uncertainty.

## E. Absence and source-scope review

- [ ] `not_reported` means the defined, readable source scope was actually checked.
- [ ] Checked scope names all relevant source IDs and anchors, including likely tables and
      methods/statistics sections.
- [ ] Near-miss measures (for example SEM when a 95% CI was requested) are not substituted.
- [ ] The statement is “not reported in checked scope,” not “unknown worldwide.”
- [ ] `unreadable` identifies the unreadable object/page and the platform-tool limitation.
- [ ] `missing` identifies absent case material rather than claiming non-reporting. An empty
      checked source scope is permitted only for this status and requires a specific
      `inventory_gap` explanation; it is never valid for answered/not-reported/unreadable rows.
- [ ] Evidence arrays for absence states remain honest. If `minItems: 1` conflicts with an
      empty evidence array, checked scope is recorded elsewhere and the conflict stays
      visible; no placeholder evidence is invented.
- [ ] Any unchecked material and its consequence are explicit in an honest partial result.

## F. Adversarial generalization review

Search the draft for `all`, `always`, `never`, `universal`, `proves`, `demonstrates`,
`safe`, `effective`, `superior`, `significant`, and causal verbs. For each:

- [ ] Is the wording explicitly licensed by the source and requested task?
- [ ] Does a single-site/table/subgroup result leak into a paper-wide conclusion?
- [ ] Does absence of a reported item become a factual claim that the item does not exist?
- [ ] Does statistical non-significance become clinical or practical equivalence?
- [ ] Does an association become causation?

Record the narrower replacement wording and the condition that triggered the revision.

## G. Task-mode review

- [ ] Notes retain original section hierarchy, order, headings, and scope.
- [ ] Extraction contains only requested fields and values; no unsolicited synthesis.
- [ ] Verification evaluates atomic propositions and distinguishes mixed/unchecked support.
- [ ] Translation covers exactly the requested span, with no extra summary or commentary.
- [ ] QA includes no mandatory paper cards, graphs, or bibliographic padding.

## H. Final gate and disclosure

- [ ] Semantic findings are resolved or explicitly disclosed before schema validation.
- [ ] Root/nested required keys and every other declared property, types, enums, string
      lengths, item counts, exact IDs, and `additionalProperties: false` are validated against
      the actual case output contract (task-only fallback only if that key is absent).
- [ ] Case, plan, and fenced task schemas agree; any contract drift fails rather than being
      resolved by silently selecting the looser schema.
- [ ] `case_id` matches the actual case.
- [ ] No helper metadata appears in a closed result object; allowed sidecars hold review data.
- [ ] Sources, uncertainty, and change records are in allowed fields or sidecars.
- [ ] Structural PASS is not described as semantic truth; semantic findings stay visible.
