# Minimal runnable example (SYNTHETIC — illustrative, not an official case)

From the skill root:

```bash
python examples/make_synthetic_case.py
```

It builds a toy case under `./synthetic_run_b/` and runs the real
pipeline end to end:

1. **Fabricates** a grouped-bar figure `fig_viability.png` (two series,
   error bars) plus `case.json` (three-field output_contract), `task.md`
   and a `caption.txt` that states the error-bar semantics (SD) — the
   caption settles what pixels cannot.
2. **Positive run** — a spec authored with honest ±0.8% reading errors:
   - `scripts/to_spec.py` validates it;
   - `scripts/replot.py` renders `output/reconstruction.{png,pdf,svg}`;
   - `scripts/overlay_diff.py` registers the reconstruction onto the
     original via the two plot-area boxes and computes ink recall /
     precision — expected verdict `verified` or `plausible`;
   - `scripts/make_result.py` ships `output/result.json` with the
     verification block and `status: success`.
3. **Negative control** — the WT "high" bar misread by +30%:
   the diff verdict degrades (`rejected` or recall collapse), and
   `make_result.py` refuses `status: success` on the rejected metrics.

Inspect `synthetic_run_b/output/verify.diff.png`: green = covered ink,
red = original ink the reconstruction missed, blue = reconstruction ink
the original does not support.

All numbers come from the synthetic ground truth the example itself
generated — nothing is a pre-computed answer to any real case.
