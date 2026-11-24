# figure-render-forge

Figure production as an engineering discipline for the Bohrium Playground
challenge `challenge-9ec929fe` (科研代码生成与执行：科研数据分析). Every
figure is declared in a plan, hard-bound to the data dictionary (axis label =
display name + unit; unknown units fail loudly instead of being guessed),
rendered deterministically, shipped with the exact rows plotted
(`<id>.figure_data.csv`), and guarded by an independent QC pass that
re-derives every numeric claim the figure makes from the source CSV.

## Requirements

- Python 3.9+ (standard library only for plan / manifest / QC logic).
- matplotlib is **optional at runtime**: it is imported lazily inside
  `render`. Without it, figforge still delivers the validated plan echo,
  `figure_data.csv` files and `figures_manifest.json` with status
  `figure_not_rendered`, records a `matplotlib_missing` anomaly, and exits 3.
- No network access. No RNG anywhere. UTF-8 text only.

## Subcommands

```text
figforge.py plan   --csv F --dictionary D --task task.md --out plan.json
figforge.py render --csv F --dictionary D --plan plan.json --outdir DIR [--formats png,svg]
figforge.py qc     --manifest M --csv F [--outdir DIR]
```

Exit codes: `0` ok · `1` QC failure · `2` usage/validation error ·
`3` degraded render (matplotlib unavailable). All diagnostics are prefixed
with `[figforge]`.

- `plan` drafts a plan heuristically (target-like column → histogram, plus a
  box-by-group if a class column exists; first two numeric columns →
  scatter). The agent must review and edit the plan; figforge never rewrites
  it, `render` only validates it strictly.
- `render` validates column existence and type compatibility, enumerates
  group levels (sorted, stringified), writes `<id>.png`, `<id>.figure_data.csv`
  and `figures_manifest.json` (per-figure axes with
  column/label/unit/n_plotted/min/max, group counts, source sha256,
  matplotlib version, `needs_review` flags).
- `qc` re-derives n_plotted / min / max / group counts from the CSV via an
  independent code path (exact comparison), checks PNG existence, size and
  magic bytes, checks that axis labels contain the dictionary unit string,
  and checks that each `figure_data.csv` row count equals `n_plotted`.

## File map

```text
SKILL.md                          skill contract (Chinese, formal)
README.md                         this file
GITHUB_URL.txt                    source repository URL
scripts/figforge.py               stdlib core; lazy matplotlib; plan/render/qc
references/figure_engineering.md  binding rules, silent-error catalog, QC checklists
examples/synthetic_case/concrete_like_syn.csv   120 invented rows (5 missing strengths)
examples/synthetic_case/data_dictionary.json    labels+units; `water` unit deliberately empty
examples/synthetic_case/figure_plan.json        4 curated figures (incl. water demo)
examples/run_example.sh           draft-plan → render → qc → print manifest
```

`examples/output_demo/` is created at runtime by `run_example.sh` and is not
part of the bundle. Runtime PNGs are binary artifacts produced into the
output directory; they are never shipped inside the bundle.

## Quick start

```bash
bash examples/run_example.sh
```

Expected: render exits 0, `qc` prints all-PASS and exits 0, and the
`water` histogram figure is flagged `needs_review` with a `unit_unknown`
anomaly.
