# Residual and tolerance rules

1. **Default relative tolerance 0.02** (2%). Override per claim with
   `tolerance_rel` when the paper's own precision justifies it (e.g. values
   rounded to two significant figures -> 0.05 or 0.1). The chosen tolerance is
   recorded in the ledger row.
2. **A genuine MISMATCH is a result, not an embarrassment.** It usually means
   one of: (a) the binding value was misread (re-open the source location),
   (b) the paper rounded aggressively, (c) the paper's arithmetic is wrong.
   Distinguish by re-reading; never "fix" a mismatch by loosening the
   tolerance without naming the reason.
3. **DIM_MISMATCH always wins over numbers.** If dimensions disagree, the
   numeric residual is meaningless; report the structural problem.
4. **Order-of-magnitude shifts** (power-of-ten errors, e.g. eV vs J, cm vs m)
   are computed and reported on MISMATCH rows in decades; a near-integer
   decades shift points at a unit-prefix or exponent slip.
5. **Dimensionless arguments are enforced**: `exp`, `log`, `ln`, `sin`, `cos`,
   `tan` of a dimensional quantity, or a dimensional exponent, BLOCK the row
   with the offending dimension printed.
6. **No reverse engineering.** If the formula, values or per-item predictions
   are absent from the materials (missing-formula branch), the correct outcome
   is `insufficient_evidence` with the missing objects named — not an invented
   equation and not zeros.
