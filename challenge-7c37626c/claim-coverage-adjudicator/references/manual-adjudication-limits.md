# Manual adjudication and limits

The gate is intentionally fail-closed about mechanics, but mechanical validity
is not scientific validity. A quote can occur exactly at the claimed locator and
still not entail the answer. Before accepting success, review the following.

## Manual checklist

1. **Atom completeness:** compare every sentence, table cell, bullet, formula
   target, and output requirement in the actual task with the atom list. The
   automatic formula-ID check cannot prove that a human-authored atomization
   captured every variable, premise, derivation step, condition, translation,
   or comparison.
2. **Semantic entailment:** read the quote in surrounding source context. Check
   that subject, condition, direction, sign, scope, units, and numeric precision
   support the whole claim. Keyword overlap is not support.
3. **MathML fidelity:** inspect fraction numerator/denominator, subscript and
   superscript bases, roots, matrices, delimiters, Greek letters, equation
   labels, and repeated source IDs. An `alttext` attribute is additional source
   evidence, not a replacement for structural inspection.
4. **Inference and derivation:** validate every prerequisite claim, assumption,
   approximation, legitimate algebraic transformation, cross-formula link, and
   boundary condition. The script only checks that prerequisites/rationale are
   present and some support exists.
5. **Numerical work:** independently recalculate substitutions, significant
   figures, units, tolerance, domain restrictions, and conditions. The scripts
   do not perform symbolic math or numeric recomputation and must not be cited
   as proof that a calculation is correct.
6. **Contradictions:** ask whether two claims truly share subject and condition.
   Review automatic `contradiction_group` conflicts and inspect other atoms for
   conflicts the agent did not group. A supported procedural resolution does
   not establish which answer is scientifically correct.
7. **Output mapping:** inspect exact field names and nested content, especially
   custom fields outside the conventional `answers/evidence/uncertainty` set.
   Schema compliance does not establish answer quality.

## Extraction limits

- The source ledger reads actual UTF-8 task/text/JSON/XML files and normalizes
  only line endings. XML excerpts are regex-located source slices, not a full
  JATS/MathML parser; malformed or unusually nested XML may require manual
  excerpting and structural inspection.
- Binary files, including PDFs and images, are listed as skipped. This bundle
  neither performs OCR nor claims PDF extraction. Use another actual extraction
  tool when allowed, then preserve its source locators in an equivalent
  normalized ledger and manually inspect the original rendering.
- Target IDs are derived from actual MathML excerpts. When no target list is
  provided, treating discovered formula IDs as requested is conservative but
  may include incidental inline formulas; the agent should atomize the real
  task and report unreasonable scope rather than fabricate answers.

## Decision limits

The adjudicator cannot prove unseen evidence absent from a larger paper,
resolve ambiguous notation, test whether inference premises jointly entail a
conclusion, or determine whether a nonplaceholder string is boilerplate beyond
its conservative patterns. Its `success` means **all implemented coverage and
provenance checks passed**, not external truth or a benchmark score. Retain the
claims ledger, source excerpts, report, and change log for human review.
