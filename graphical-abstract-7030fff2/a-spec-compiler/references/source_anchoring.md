# Source anchoring rules (Bundle A)

The spec gate treats `source_pool.txt` as the only quotable truth. Rules:

1. **Verbatim means verbatim.** Copy the characters from the pool. You may
   collapse line breaks and repeated whitespace (the checker normalises
   whitespace); you may not fix grammar, change a number, re-round, translate,
   or swap units. `42%` and `42 %` are different strings.
2. **One claim, one quote.** A node's quote must contain what the node says.
   "Caspase-3 activation" needs a quote containing that activation, not just
   the word "caspase-3" in a list of measured targets — if the source only
   says it was measured, the node must say "measured", not "activated".
3. **Numbers live in quotes or data files.** Every number token in labels,
   titles, annotations and series values must appear in the element's own
   quote or in the `data_ref` file. Derived numbers (ratios, fold-changes
   you computed) are NOT anchored by the raw data: either label them as
   computed ("2.4-fold, computed from ...") and add an exception, or drop them.
4. **Schematic vs. data.** Sentences with "schematic / illustration /
   overview / pipeline / model of" describe drawings, not measurements.
   Encoding a schematic's impression as a quantitative bar is a category
   error the gate cannot catch — you must. When the case ships biological
   source figures (e.g. figure03), inspect the rendered page and mark panels
   derived from schematics with role `note` plus an exception.
5. **Other people's results.** A sentence ending in a citation marker
   (`[12]`, `(Smith et al., 2020)`) reports prior art. If it must appear in
   the figure at all, label it as such; the headline result of a graphical
   abstract is never prior art.
6. **Uncertainty is a deliverable.** Anything you could not anchor goes to
   `result.json.uncertainty` with the reason, and the corresponding element
   is downgraded (role `note`, dashed edge, or removed).
7. **Locator discipline.** `locator` is for humans: file + page/section/
   line region, e.g. `material.pdf page 3, Results ¶2` or
   `viability.csv rows 1-2`. The machine checks the quote; the locator is
   how a reviewer re-finds it in 10 seconds.
