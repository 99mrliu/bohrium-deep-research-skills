# route-matrix-synthesis

An agent skill for scientific-writing competitions: write the Related Work +
research gap of a manuscript introduction by first building a **comparison
matrix** of prior works (grouped by method route, compared on shared axes),
then **deriving the gap from documented limitations** in that matrix.

Start with `SKILL.md` — it is the operative instruction set, including the
runtime contract (`/input`, `/app/work`, `/app/output`, `result.json`).

## Layout

```
SKILL.md                      skill instructions (graded artifact)
README.md                     this file
GITHUB_URL.txt                upstream repository location
scripts/build_matrix.py       route classification + matrix scaffold
scripts/matrix_lint.py        verbatim-quote and coverage lint (exit 0/1/2)
scripts/gap_check.py          gap<-limitation, counterexample, anchor, citation checks
references/comparison_axes.md the six comparison axes, with filled synthetic examples
references/gap_patterns.md    four-link gap chain + anti-patterns
references/route_keywords.json editable keyword rules for route classification
examples/README.md            what the demo shows + exact commands
examples/run_example.sh       end-to-end demo run
examples/synthetic-case/      invented 6-reference mini case (PermaLig)
examples/sample-output/       real outputs of the last demo run
```

All scripts are pure Python 3.9+ stdlib. Quick smoke test:

```bash
bash examples/run_example.sh
```

Everything under `examples/` is a synthetic demonstration with invented
material — never submit it as an answer to a real case.
