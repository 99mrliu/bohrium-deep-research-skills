# Derivation step skeleton (`/app/work/steps.json`)

```json
{
  "steps": [
    {
      "step_id": "s1",
      "from": "eq2",
      "to": "eq1",
      "action": "substitute the zero-field value mu_0 for mu in the Einstein relation",
      "justification": "limiting case stated in sec s2: the field vanishes, exp(0)=1",
      "locator": "sec s2, paragraph 1, 'Equation (1) is recovered...'",
      "assumptions": ["electric field E = 0"],
      "approximations": [],
      "boundary_conditions": []
    }
  ]
}
```

## Field rules (enforced by `scripts/step_gate.py`)

- `from` / `to`: node ids from `graph.json` (e.g. `eq1`), or non-formula
  landmarks (`text:sec-s2`, `reported:table-1`). A reference to a formula id
  absent from the graph fails the gate.
- `action`: what this step does to the previous expression (substitute,
  differentiate, take a limit, apply a boundary condition).
- `justification`: why it is legal — the algebraic rule, the cited identity,
  or the paper's own statement, quoted or precisely located. A justification
  shorter than a real phrase fails the gate.
- `locator`: where in the source the reader verifies this step
  (section/paragraph/equation/table).
- `assumptions`, `approximations`, `boundary_conditions`: lists, possibly
  empty, but always present. Feed them from `assumptions.json` (the radar)
  and confirm by reading; quote evidence, do not paraphrase.

## Completeness expectations

- Every formula that the task asks to "derive" needs at least one step chain
  ending at it.
- Steps supplied by you (the reader) versus steps the authors state
  explicitly are distinguished by the locator: no source location means it is
  your reconstruction — say so in the justification.
- If the premises for a step are missing from the materials, stop the chain
  at the strongest supported conclusion and name the missing premise in
  `uncertainty`; do not fabricate the step.
