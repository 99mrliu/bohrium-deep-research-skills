# Examples — route-matrix-synthesis

**SYNTHETIC EXAMPLE — invented material, demonstrates the interface only; not
a platform test answer.** Every author, journal, DOI, abstract, number and
"manuscript fact" under `synthetic-case/` is fabricated. Nothing here may be
submitted as an answer to one of the organizers' fixed cases.

## What the example shows

The full pipeline on a 6-reference mini case about an invented method
"PermaLig" (binding-site prediction on low-identity templates):

1. `build_matrix.py` classifies each reference into a method route via
   keyword rules, ranks references by closeness to the manuscript's problem
   terms, and emits a fillable `matrix.json` + `matrix.md` scaffold.
2. A human/agent-filled matrix (`synthetic-case/filled/matrix.json`) where
   every cell carries a verbatim quote from the synthetic abstracts.
3. `matrix_lint.py` verifies quote fidelity, route coverage and matrix
   completeness (expected: PASS with one `single_ref_route` warning for the
   `survey` route).
4. `gap_check.py` verifies that the gap paragraph of the filled introduction
   (`synthetic-case/filled/introduction.md`) is derivable from the matrix's
   limitation column, that counterexamples (ConsenSite, MultiTempl) are
   scoped in the gap, that each contribution carries an anchor (Fig 1 /
   Fig 2), and that all citations map to the bibliography.

## Run it

```bash
bash examples/run_example.sh
```

Equivalent explicit commands (run from anywhere):

```bash
python3 <skill-dir>/scripts/build_matrix.py \
  --case <skill-dir>/examples/synthetic-case/case.json \
  --bib <skill-dir>/examples/synthetic-case/material/references.json \
  --facts <skill-dir>/examples/synthetic-case/material/manuscript-facts.md \
  --route-keywords <skill-dir>/references/route_keywords.json \
  --out-dir <skill-dir>/examples/sample-output

python3 <skill-dir>/scripts/matrix_lint.py \
  --matrix <skill-dir>/examples/synthetic-case/filled/matrix.json \
  --bib <skill-dir>/examples/synthetic-case/material/references.json \
  --out <skill-dir>/examples/sample-output/lint_report.json

python3 <skill-dir>/scripts/gap_check.py \
  --case <skill-dir>/examples/synthetic-case/case.json \
  --matrix <skill-dir>/examples/synthetic-case/filled/matrix.json \
  --draft <skill-dir>/examples/synthetic-case/filled/introduction.md \
  --out <skill-dir>/examples/sample-output/gap_report.json
```

`sample-output/` contains the real outputs of the last actual run:
`matrix.json`, `matrix.md` (scaffolds), `lint_report.json`, `gap_report.json`.

Exit codes for all scripts: `0` = pass, `1` = findings/fail, `2` = usage or
IO error.
