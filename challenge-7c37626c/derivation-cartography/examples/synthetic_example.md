# Minimal example (SYNTHETIC — interface demonstration, not a platform case)

## Input

`examples/fixture/input/` contains a fabricated JATS-like
`publisher-source.xml` with two formulas (Einstein relation `eq1`, and the
labeled display formula `eq2` with label `(2)`) and prose that mentions
"Equation (1)", a substitution sentence, and the limiting case "when the
electric field vanishes". `examples/fixture/steps.json` ships a two-step
skeleton: step `s1` complete, step `s2` deliberately missing its
`justification`.

## Invocation

```bash
bash examples/run_synthetic_example.sh
```

## What a passing run looks like

- `graph.json`: 3 math nodes (eq1, eq2, eq1-k); symbol-flow edge `eq2 → eq1`
  (symbol `mu` introduced in eq2's context, used by eq1); the citation
  "Equation (1)" recorded under `unresolved_citations` because **no formula
  node carries label (1)** — an honest hole, not a guessed positional match.
- `graph.mmd` + `graph.png`: the dependency graph as Mermaid source and a
  rendered PNG (PNG skipped with a note if matplotlib is absent).
- `assumptions.json`: the sentence "Equation (1) is recovered when the
  electric field vanishes, since exp(0) = 1 …" flagged as a `limiting_case`
  hit anchored to section `s2`, quoted verbatim.
- `gate_report.json` + `result.json`: step `s1` accepted; step `s2` rejected
  ("justification too thin / empty") and named in
  `uncertainty.defective_steps`; status `partial` — the gate fails closed.

All materials, steps and outputs of this example are synthetic.
