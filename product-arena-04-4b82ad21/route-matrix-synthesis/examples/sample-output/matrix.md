# Comparison matrix (EDITABLE SCAFFOLD)

Case: `synthetic-intro-demo-0001`

How to fill this matrix:

- Every filled cell MUST end with a verbatim quote copied from
  that reference's provided text plus a location label, e.g.
  `... [quote: "..." — abstract]`. Quotes are verified by
  matrix_lint.py as whitespace-normalized substrings.
- Cells for references marked `title-only` must not attribute
  findings; state at most what the title supports.
- `decisive_comparison` = one sentence per route: shared task +
  meaningful distinction + consequence under THIS manuscript's
  conditions. At least one filled decisive_comparison per route
  is required by matrix_lint.py.
- Keep matrix.json and this file in sync; matrix.json is the
  authoritative machine-readable form.

## Route: consensus-scoring

| Ref | Evidence | Closest? | problem_setting | inputs_required | scoring_or_integration_stage | evaluation_setting | stated_limitation | decisive_comparison |
|---|---|---|---|---|---|---|---|---|
| `synth03` | abstract-available |  | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |
| `synth05` | abstract-available | yes | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |

## Route: geometry-based

| Ref | Evidence | Closest? | problem_setting | inputs_required | scoring_or_integration_stage | evaluation_setting | stated_limitation | decisive_comparison |
|---|---|---|---|---|---|---|---|---|
| `synth04` | abstract-available |  | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |
| `synth06` | abstract-available |  | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |

## Route: sequence-only

| Ref | Evidence | Closest? | problem_setting | inputs_required | scoring_or_integration_stage | evaluation_setting | stated_limitation | decisive_comparison |
|---|---|---|---|---|---|---|---|---|
| `synth02` | abstract-available |  | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |
| `synth06` | abstract-available |  | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |

## Route: survey

| Ref | Evidence | Closest? | problem_setting | inputs_required | scoring_or_integration_stage | evaluation_setting | stated_limitation | decisive_comparison |
|---|---|---|---|---|---|---|---|---|
| `synth06` | abstract-available |  | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |

## Route: template-based-transfer

| Ref | Evidence | Closest? | problem_setting | inputs_required | scoring_or_integration_stage | evaluation_setting | stated_limitation | decisive_comparison |
|---|---|---|---|---|---|---|---|---|
| `synth01` | abstract-available | yes | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |
| `synth03` | abstract-available |  | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ | _(to fill)_ |

## Closeness ranking (keyword overlap with the manuscript problem terms)

- rank 1: `synth05` (score 12) CLOSEST-ALTERNATIVE CANDIDATE — shared terms: candidate, consensus, improve, multiple, pocket, protein, score, scoring, structure, target, template, transfer
- rank 2: `synth01` (score 11) CLOSEST-ALTERNATIVE CANDIDATE — shared terms: benchmark, binding, identity, invented, ligand, pocket, site, structure, target, template, top
- rank 3: `synth03` (score 10) — shared terms: identity, low, multiple, pocket, quality, structure, target, template, transfer, vote
- rank 4: `synth06` (score 8) — shared terms: binding, identity, low, sequence, setting, site, template, transfer
- rank 5: `synth02` (score 7) — shared terms: binding, pocket, sequence, site, target, template, top
- rank 6: `synth04` (score 6) — shared terms: binding, candidate, identity, low, pocket, template
