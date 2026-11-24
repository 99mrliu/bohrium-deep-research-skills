# Comparison axes — taxonomy and filling guidance

The comparison matrix forces related work to be written as a *same-axis*
comparison instead of a paper-by-paper chronology. Every reference is scored
on the same six axes, so the reader can see routes (method families) and the
one axis where the gap lives. All examples below are **SYNTHETIC** — they use
the invented PermaLig demonstration material shipped under `examples/`.

## The six axes

### 1. problem_setting
What task the work actually solves, in one phrase: input modality, output
granularity, and the regime it targets (e.g. "low-identity template transfer"
vs "template-rich refinement"). Two papers with similar titles often differ
here, and the difference decides whether they are competitors at all.

*Fill guidance:* quote the sentence that states the task, usually the first
sentence of the abstract. Do not paraphrase a title-only reference into a
task claim.

### 2. inputs_required
What must exist before the method runs: templates, multiple experimental
structures, MSAs, sequence only, pre-computed features. Inputs are the most
common *scope* difference: a method whose inputs are unavailable in your
setting is not a counterexample to your gap — say so explicitly, with the
quote.

### 3. scoring_or_integration_stage
Where the method commits: single prediction, pooling, re-ranking, consensus
voting, weighting. This axis separates "what information is used" from "how
it is combined", which is where most incremental contributions live.

### 4. evaluation_setting
Benchmark, split, metric, and — critically — the regime evaluated (identity
bands, difficulty subsets). An evaluation that never touches your regime
limits what the work can claim against you; record that as a fact about the
evidence, not as a criticism.

### 5. stated_limitation
A limitation *documented in the provided text* — an explicit author note, a
dropped metric in a sub-regime, or a missing evaluation the text itself
acknowledges. Never invent a limitation; if none is documented, write
"none stated in provided text" and leave the quote empty. This column is the
only legitimate source of the research gap.

### 6. decisive_comparison
One sentence per reference (at least one per route) of the form:
**shared task + meaningful distinction + consequence under this manuscript's
conditions.** Not "X is better/worse" but "on the task this manuscript
shares with X, X differs in Y, therefore under our conditions Z follows".

## Synthetic filled examples (from the PermaLig demo — invented material)

**synth03 / MultiTempl (route: template-based-transfer + consensus-scoring)**
- problem_setting: "Naive pocket pooling from multiple templates." —
  quote: "pools predicted pockets from up to 8 template structures and ranks
  them by pocket frequency" (abstract)
- scoring_or_integration_stage: "Frequency ranking; equal weight per
  template." — quote: "ranks them by pocket frequency" (abstract)
- stated_limitation: quote: "precision on low-identity targets stays flat
  because low-quality templates vote with equal weight" (abstract)
- decisive_comparison: "Same multi-template pooling idea as the present
  work, but frequency ranking gives low-quality templates equal votes;
  under this manuscript's sub-30%-identity conditions that leaves precision
  flat, which is what quality-weighted voting is designed to change."

**synth05 / ConsenSite (route: consensus-scoring — the nearest alternative)**
- inputs_required: quote: "requires multiple experimental structures of the
  target itself" (abstract)
- evaluation_setting: quote: "improves precision by 0.07 over
  single-structure scoring" (abstract)
- decisive_comparison: "Nearest consensus alternative: it shows consensus
  scoring helps (+0.07 precision) but only when the target already has
  several experimental structures, so its capability does not reach the
  low-identity template-transfer setting this manuscript addresses."

**synth04 / GeoScore (route: geometry-based)**
- stated_limitation: "Evidence gap, not a defect." — quote: "the abstract
  reports no comparison against template-based predictors and no
  low-identity evaluation" (abstract)
- decisive_comparison: "Template-free and fast, but with no reported
  comparison against template-based predictors it cannot be ranked in this
  manuscript's setting and is treated as orthogonal rather than as a
  counterexample to the gap."

## Practical rules

- One quote per cell minimum; the linter verifies quotes as
  whitespace-normalized substrings of the bibliography text.
- A reference may sit in several routes; fill cells once, and let the route
  grouping reuse them.
- Title-only references: fill problem_setting at most, mark the rest
  "not documented (title-only)".
- If an axis is genuinely not discussed, say so in the cell — "no
  low-identity evaluation reported" is information, not a gap in your table.
