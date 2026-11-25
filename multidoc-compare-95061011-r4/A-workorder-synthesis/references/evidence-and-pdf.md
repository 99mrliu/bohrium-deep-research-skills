# Evidence, PDF, and comparability guide

## PDF reading focused on the question

Use the response plan to locate only relevant passages first, then read enough surrounding context to interpret them. For each PDF:

1. Run `pdftotext -layout INPUT.pdf WORKING.txt` with explicit local paths.
2. Check that the expected pages and sections exist. Look for empty output, broken glyphs, split scientific notation, swapped table columns, and footnote markers detached from values.
3. Read table titles, headers, units, captions, and footnotes along with cells. A number without its denominator or time point is not yet a usable result.
4. When extraction fails or figure/table layout is ambiguous, render the relevant page and inspect it directly. If available, use OCR as a secondary route, then verify names, decimal points, signs, units, and row alignment against the rendering.
5. Preserve page details in working notes. Produce a UTF-8 working text with stable `[paragraph_id]` markers for validated spans. If a source already supplies paragraph IDs, use those exact IDs.

A read failure belongs in `completion.read_failures`, uncertainty, and change records. Do not hide it behind a guessed value.

## State decision examples

Assume a question asks for a variance estimate:

- The methods apply to variance but no variance appears: `not_reported`.
- The source is a single deterministic theoretical value for which replicate variance is outside the requested source design: `not_applicable`, with a reason; do not use this merely because variance is absent.
- A table contains an ambiguous `±` term whose caption does not distinguish standard deviation from standard error: `unclear`, with the quote and ambiguity.
- Two papers report the same metric but under different tasks/materials/pollutants/budgets: each value can be `reported`, while their proposed pooled result is `noncomparable` and excluded. Do not relabel either original source value as non-reported.

`not_reported` means absent, not zero, no effect, failure, or disagreement. `unclear` means something relevant is present but unresolved. `not_applicable` requires a definitional reason.

## Comparability is a claim requiring evidence

For each candidate quantitative synthesis, build a small comparison from the source cells:

| Axis | Question to resolve |
|---|---|
| task | Are the operations and evaluation protocol equivalent? |
| metric | Are definitions, denominators, and time points the same? |
| units | Are units identical or exactly and transparently convertible? |
| material | Is the material/system the same under the workorder's definition? |
| pollutant | Is the target pollutant/dye/analyte the same? |
| budget | Are cost/resource constraints and included components equivalent? |

Then check dataset identity and any workorder-specific condition. Similar names or units are insufficient when datasets differ. If a condition is not supplied, retain the uncertainty rather than assuming equivalence. If an axis is truly irrelevant, record the same explicit `not_applicable` value and the reason for every member.

For a failed axis, do not calculate the pool “just for reference.” Report the individual values and explain the failed comparability test. This fully answers a question asking whether pooling is defensible and does not make the run partial.

## Quotes and calculations

Quotes must be contiguous spans, not stitched fragments from different paragraphs. Keep the quote long enough to support the value and its conditions. The paragraph locator identifies the whole source paragraph; the quote identifies the supporting span.

For any synthesis, preserve member cell IDs, method, units, and result. Use an unweighted arithmetic mean only when that is what the question requests and no weighting basis is justified. Do not infer variance, sample size, uncertainty intervals, or statistical significance from point values alone.
