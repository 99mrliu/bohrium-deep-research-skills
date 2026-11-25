# Synthetic example (合成示例)

Everything in this directory is **INVENTED** and marked `SYNTHETIC`:
the "SynGraph: Graph Kernels for Molecule Property Prediction" study does
not exist.

## Files

| file | role |
|---|---|
| `make_fixture.py` | Builds `work/input/starting-deck.pptx` (5 slides, written through the bundle's own `deck_io` machinery), `work/paper.txt`, `work/input/case.json`, `work/input/task.md`, `work/workorder.json`, `work/refit_ops.json` (honest ops) and `work/refit_ops_bad.json` (fabricates 97.1%). |
| `run_example.sh` | Runs the full pipeline: fixture → read → terms → brief → apply → audit (must PASS) → **negative demo** (audit must FAIL, exit 1) → result.json. |
| `expected_output.md` | What each artifact proves, with the real failure line. |

## Run

```bash
bash run_example.sh
```

Expected: exit 0 overall; the negative-demo `conserve_check` prints
`verdict: FAIL` and exits 1 **by design** — the script asserts that.

## The refit being demonstrated

Peer-audience 5-slide deck → advisor progress meeting, English kept,
4 slides: background+gap merge, results re-voiced as progress milestones,
backup slide dropped (numbers declared), new next-steps slide cloned from
the title slide.
