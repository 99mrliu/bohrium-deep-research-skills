# Terminology Failure Modes — casebook

Real, recurring ways terminology breaks when a base agent polishes academic
text paragraph by paragraph. Each case: symptom → why agents cause it → how
the termbase gate catches it. Use these as review patterns in Step 1 and as
lint-finding interpretations in Step 4.

## F1. Abbreviation used before it is defined ("EIS appears first")

- Symptom: Introduction says "EIS has become a standard tool..."; the
  expansion "electrochemical impedance spectroscopy (EIS)" only shows up in
  Methods.
- Why: the agent rewrites sections independently; moving or duplicating the
  parenthetical definition is invisible at paragraph scope.
- Gate: `late_definition` (or `never_defined` if the full name vanished
  entirely) with the exact first-use position.
- Fix pattern: put `Full Name (ABBR)` at the true first occurrence, use the
  bare abbreviation afterwards.

## F2. Synonymous long forms mixed ("Li-ion" vs "Lithium-ion")

- Symptom: "Lithium-ion batteries (LIBs)" in the Introduction, "Li-ion
  diffusion" in Results, "lithium ion batteries" in the Conclusion.
- Why: both forms are idiomatic; nothing at sentence level prefers one.
- Gate: one entry with `canonical: Li-ion battery` and the long forms in
  `banned`; every occurrence of the long form is a `banned_variant` error,
  caught regardless of case or hyphenation.
- Fix pattern: rewrite to the canonical short form everywhere, keeping the
  `(ABBR)` definition at first use.

## F3. Capitalization drift ("li-ion", "Li-Ion")

- Symptom: mid-sentence "li-ion cells"; title "Li-Ion Battery".
- Why: casing fixes look trivial and get applied inconsistently.
- Gate: `spelling_inconsistency` — normalized form matches a registered
  surface but exact casing does not. Sentence-initial first-letter
  capitalization and heading title-case are tolerated automatically.

## F4. Hyphenation drift ("solid-electrolyte interphase", "Li ion")

- Symptom: the same compound appears hyphenated in one section, open in
  another.
- Why: both are attested in the literature; the agent mirrors whatever the
  local paragraph had.
- Gate: same mechanism as F2/F3 — register the accepted hyphenation as
  canonical/variant, ban the rejected one.

## F5. Definition phrased with a banned full form

- Symptom: "Lithium-ion batteries (LIBs) are widely used..." — the
  abbreviation IS defined at first use, but through a banned variant.
- Why: an agent fixes "define at first use" without fixing WHICH full form
  carries the definition.
- Gate: `definition_uses_banned_variant` — distinct from `late_definition`
  so the fix targets the definition phrase, not its position.

## F6. Cross-section drift

- Symptom: term correct within each paragraph, but Introduction uses
  "solid electrolyte interphase" while Results uses "solid-electrolyte
  interphase".
- Why: paragraph-local optimization; no whole-document view.
- Gate: `cross_section_drift` aggregates one entry's errors across the
  Markdown/LaTeX section map and reports exactly which sections disagree.

## F7. Abbreviation defined but never used again

- Symptom: "atomic layer deposition (ALD)" appears once; "ALD" never again.
- Why: harmless but noisy; reviewers flag it.
- Gate: `abbrev_defined_but_unused` warning (does not fail the gate).
- Fix pattern: either use the abbreviation later or drop the parenthetical.

## F8. Plural abbreviation ambiguity

- Symptom: "(LIBs)" defined, then "LIB" and "LIBs" used interchangeably.
- Gate: `abbrev` and `abbrev + "s"` are both registered surfaces; any other
  inflection ("LIB's") is a `spelling_inconsistency`.

## F9. Silent numeric loss during a "terminology" edit

- Symptom: fixing a term in "coatings of 2 nm were deposited" accidentally
  drops "2 nm".
- Why: term edits ride along with stylistic rewrites.
- Gate: `pipeline.py apply-edits` protected tokens (number+unit, citations,
  Fig./Eq., URL/DOI, bare numbers) are compared per unit; loss reverts the
  edit even when the review approved it.

## F10. Unregistered acronym escapes all checks

- Symptom: "GITT" used once, never expanded, nobody locked it.
- Gate: `extract` surfaces it as an `acronym` candidate; if the agent cannot
  source its expansion, the honest move is to record the gap in
  `uncertainty` — not to invent a full name. This is a stated boundary of
  the machine gate.
