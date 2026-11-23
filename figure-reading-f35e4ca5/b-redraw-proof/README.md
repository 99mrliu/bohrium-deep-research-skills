# redraw-proof-figure-reading

Skill for challenge **阅读02｜科研图表解析** (challenge-f35e4ca5).
Center: **downstream rendering engineering** — extracted data is accepted
only if a deterministic re-render of the figure, pixel-diffed against the
original after affine plot-area registration, reproduces the ink
(fill recall / precision / edge recall / worst-cell gate). Ships the
reconstruction (PNG/PDF/SVG), the diff map and the metrics as proof.

- `SKILL.md` — the protocol (runtime contract, workflow, failure catalogue)
- `scripts/to_spec.py` — hard-validated figure_spec.json (stdlib)
- `scripts/replot.py` — deterministic re-render + plot-area meta (matplotlib)
- `scripts/overlay_diff.py` — registered overlay diff, per-series recall, verdicts (numpy+PIL)
- `scripts/make_result.py` — verdict-gated contract assembly (stdlib)
- `references/` — spec format, diff metrics and verdict rules
- `examples/` — runnable synthetic miniature (marked as example)

Run the example: `python examples/make_synthetic_case.py`
