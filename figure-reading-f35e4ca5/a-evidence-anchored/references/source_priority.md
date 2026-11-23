# Source priority and conflict rules

The fixed cases ship the original figure image AND all original tables
(and, per case, caption/text via the task materials). Treat these layers
by authenticity, not by convenience.

## Priority ladder (highest first)

1. **Original tables** (`*.csv`/`*.tsv` in the case) — machine-exact;
   they are the numbers the figure was plotted from. `mine_case.py`
   profiles every column (range, unit guess) so they are queryable.
2. **Caption and body-text verbatim** — exact quotes beat any reading.
   A caption that says "n = 5, error bars denote SD" settles the
   error-bar semantics question that pixels can never settle.
3. **Figure pixels** — a *hypothesis* about the numbers. A pixel reading
   becomes a fact only after `crosscheck.py` matches it to layer 1 or 2.
4. **Derived quantities** — computed from validated claims; label them
   `derived` and show the inputs.

## Conflicts between layers

- Table value ≠ caption value: report both with locators; mark the claim
  `unmatched`; the caption usually describes a *processed* version of the
  table (normalized, averaged) — say which layer you answered from and why.
- Figure reading ≠ table value beyond tolerance: the figure wins only if
  the table row is demonstrably out of the figure's scope (different
  condition, different panel); otherwise suspect your calibration
  (`anchor_map.json` residuals) and re-measure before reporting anything.
- Missing layer: a figure element with no table counterpart gets
  `crosscheck: no_anchor` and a written justification; it is still
  reportable as a figure reading, but with its reading error and the
  absence of confirmation stated.

## What the gates catch

- **Axis-type gate** — declaring "linear" on log-spaced ticks (or the
  reverse) corrupts every downstream value; `anchor_figure.py` hard-fails.
- **Unit-prefix gate** — mV read as V shows up as a 10^3 range mismatch
  against the tables; `candidate_columns` expose it. Copy unit characters
  verbatim, including `µ`/`μ` and `°`.
- **Series-legend gate** — a series with no anchor and a table column with
  no series is the fingerprint of a swapped legend mapping; check the
  `unexplained_table_rows` list before finalizing.

## Language of the answer

- Table- or caption-confirmed values: state as fact with unit.
- Figure-only readings: state with `±` reading error and
  "(read from figure, unconfirmed by table)".
- Derived values: state with the formula and input claims.
- Absent information: "the figure and tables do not report X" — a finding,
  not a gap to be guessed.
