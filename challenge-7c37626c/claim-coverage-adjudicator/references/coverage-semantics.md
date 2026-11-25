# Coverage and status semantics

## Four-linked coverage

Coverage is a conjunction of four links, not a count of files or nonempty keys:

1. **Task atom:** an exact requested clause with a stable ID and output target.
2. **Claim:** a substantive answer, type, origin, and completion state.
3. **Evidence:** source identity, exact locator, and verbatim quote at that
   excerpt, with supports/refutes/context kept distinct.
4. **Output field:** the exact field in the case's own contract, populated with
   the authored answer and declared JSON type.

A break in any link prevents `success`. Evidence at a different locator,
well-formed but unsupported prose, a first-formula-only answer, or a populated
field with placeholder text is not complete coverage.

## Mechanical success predicate

The adjudicator recommends `success` only if all predicates hold:

- at least one authored atom exists and every atom has a completed central claim
  with a substantive answer and verified support;
- every substantive answer needing support has at least one verified `supports`
  record; inference also has explicit nonempty prerequisites and rationale;
- evidence references a real source excerpt ID, matching source file and
  locator, and the quote occurs verbatim in that exact excerpt;
- formula claims have source IDs and matching MathML support, and every
  requested formula ID has a completed supported claim (there is no “first one
  is enough” shortcut);
- every non-system required content field is targeted by an atom/claim and is
  nonempty and nonplaceholder; required `case_id` and all declared field types
  match, and status belongs to `status_enum`;
- no unresolved declared contradiction, divergent completed central answers in
  a shared contradiction group, or refuted central claim exists.

`case_id`, `status`, `evidence`, `uncertainty`, and `artifacts` are system
fields. Their coverage is supplied by exact case identity, adjudicated status,
and finalizer aggregation rather than artificial scientific claims. All other
required fields require atom/claim output targeting.

## Placeholders and emptiness

Null, empty strings/arrays/objects in content fields, and common non-answers
(`TBD`, `TODO`, `unknown`, `not reported`, `pending`, `N/A`, `placeholder`,
`insufficient_evidence`, XML-like insertion markers, and similar) cannot satisfy
success. Nested occurrences are reported by path. Numeric zero and boolean false
are valid values. Nonempty filler is not enough; central placeholder answers
also block atom completion. Uncertainty text may explain a genuine gap, but that
naturally accompanies partial/insufficient status rather than success.

## Partial versus insufficient evidence

- Any defect with at least one substantive central answer object produces
  `partial`, with machine-detected gaps and authored missing objects retained in
  object-valued `uncertainty`.
- No substantive central answer object produces `insufficient_evidence`, even
  when the result draft claims success. This includes an empty atom list and
  all-placeholder answers.
- The scaffold always banks `partial` before analysis, because adjudication has
  not yet established whether answer objects exist.
- Unexpected I/O usage errors return process exit 2 and leave the prior output
  checkpoint alone; they are not relabeled scientific conclusions.

The finalizer ignores a draft's optimistic status and independently applies the
adjudicator's recommendation. It does not convert a failure into success by
adding boilerplate.

## Formula-all semantics

When `case.target_formulas` is a list, those exact IDs are requested. Otherwise,
the IDs discovered in MathML formula excerpts form the requested set. Each must
actually occur in the source ledger and have a completed formula claim with a
matching source-ID support record. A prose-only quote, another formula's XML,
or a source-ID mismatch cannot close it. If the requested ID is absent, that is
a named evidence gap rather than an invitation to invent it.

For C01/C03, MathML structure and prose definitions play different roles.
Formula support must come from matching MathML. Variable definitions,
conditions, derivations, and reported numbers need their own supporting prose
or numeric records. A formula catalog never counts as a derivation.

## Metrics-only/C02 semantics

Scaffolding names missing formula/derivation/recalculation objects when the
actual task asks for them and no MathML representation exists. With explicit
reported metrics but no artifacts, it also names missing per-item predictions.

An explicit aggregate metric can be a completed **reported** numeric/statement
claim with a direct quote. A completed derivation is blocked when derivation
objects are missing. A completed inferred numeric recalculation is blocked when
recalculable inputs/raw data are missing. The allowed honest outcomes are:

- explicit metric answered + formula/derivation/recalculation missing:
  `partial`;
- no substantive answer objects: `insufficient_evidence`.

The metric value itself is not retroactively converted into raw observations,
per-item predictions, a formula, or zero-filled unknowns. These missing-object
rules are intentionally conservative and do not prohibit a valid recalculation
when the actual source supplies all required formulas and numeric inputs.

## Contradictions and refutations

Evidence relations are retained in final `evidence`, including `refutes` and
`context`; aggregation does not erase the losing side. A verified refutation of
a central answer blocks success. Equal-subject claims are opted into automatic
comparison with `contradiction_group`; different normalized completed central
answers block success. The checker deliberately does not infer that arbitrary
different atom answers conflict.

Resolution requires both a substantive explanation and valid supports evidence.
The rejected alternative must no longer be delivered as a completed central
answer; preserve it as noncentral/refuted. A resolution label alone is not
adjudication.
