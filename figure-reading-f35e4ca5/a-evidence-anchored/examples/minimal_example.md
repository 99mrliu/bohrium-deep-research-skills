# Minimal runnable example (SYNTHETIC — illustrative, not an official case)

One command builds a toy case in `./synthetic_run_a/` and runs the full
pipeline end to end:

```bash
python scripts/../../examples/make_synthetic_case.py
# or from the skill root:
python examples/make_synthetic_case.py
```

What it does, step by step:

1. **Fabricates a toy case** — `table_response.csv` (dose–response data
   for two series) plus a matplotlib figure `fig_doseresp.png` plotted
   from that same table, `case.json` with a three-field output_contract,
   and a one-line `task.md`.
2. **Runs the real skill scripts** against it:
   - `scripts/mine_case.py` → `work/inventory.json` (table profiles,
     number index) + skeleton `output/result.json`;
   - the example then writes `axis_spec.json` and `figure_readings.json`
     simulating what the agent reads from the figure (with small, honest
     reading errors);
   - `scripts/anchor_figure.py` → `work/anchor_map.json` — gates pass;
   - `scripts/crosscheck.py` → `work/crosscheck_matrix.json` — series
     match their table columns within tolerance;
   - `scripts/make_result.py` → `output/result.json` with
     provenance-tagged claims and `status: success`.
3. **Negative control** — an axis card declaring the log dose axis
   "linear" is fed to `anchor_figure.py`, which must hard-fail the
   axis_type_gate; the example asserts on that.

Expected tail of the output:

```
{"anchor_map": ".../anchor_map.json", "hard_fail": 0, ...}
{"crosscheck": ".../crosscheck_matrix.json", "all_matched": true, ...}
{"written": ".../output/result.json", "status": "success", ...}
[example] negative control correctly rejected: axis_type_gate
[example] DONE. Inspect .../output/result.json
```

Nothing here is a pre-computed answer to any real case: the numbers come
from the synthetic table the example itself generated.
