# Observed corruption and divergence patterns in publisher formula sources

Patterns this skill's checks are designed to catch (extend when seen in the
wild; cite the file and node id that demonstrated each new pattern):

1. **Truncated XML** — document ends mid-node; parse error with a byte offset
   far from the start. Salvage recovers the leading `<math>` fragments.
2. **Flattened subset** — `source-formulas.xml` contains only `mi/mn` runs
   with no `mfrac/msup` although the alttext shows fractions and powers:
   signature statistics expose the flattening.
3. **Namespace stripping** — fragments lose `xmlns:mml`; standalone parsing
   fails. The salvager re-declares the namespace before parsing.
4. **alttext drift** — publisher alttext disagrees with the MathML (usually a
   lost subscript or a merged symbol). Report both token sets; never pick one.
5. **Unicode/entity mixture** — `&#956;` (Greek mu) in MathML but `u` or `mu`
   in prose; signature normalization maps Greek code points to names so the
   two layers can be compared.
6. **Scientific-notation fragmentation** — `1.602×10⁻¹⁹` split across
   runs/superscripts in the text layer; the constant regex accepts
   `x`, `×` and optional `^`.
7. **Copy-diverged catalog** — a subset node keeps the same id but its
   structure differs from the source node (e.g. denominator dropped).
   `subset_vs_source` marks it `divergent` with the differing features.
8. **Empty formula branch** — metrics or prose only, no formula artifact:
   the correct verdict is `insufficient_evidence` for formula tasks, never a
   reverse-engineered equation.
