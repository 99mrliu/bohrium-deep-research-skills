# SYNTHETIC minimal source-span atlas example

**Every source, number, connection, and figure in this directory is SYNTHETIC. This is not a real biological experiment, not an official case, and not a prepared official answer.** The nominal artefact is merely a runnable verification of source-span matching, original-figure review bookkeeping, actual CSV mappings, editable layered SVG output, and failure gating.

- `input/sources/methods.txt`: synthetic methods fixture, one form-feed-free page.
- `input/sources/original_figure03.svg`: synthetic original Figure 03, editable text SVG used as the direct-visual-review fixture.
- `input/data/measurements.csv`: actual CSV bytes used by the renderer; `time_s` and `response` are bound case-sensitively, including source rows 2–4.
- `input/atlas.json`: assertions, unique source quotes/locators, separate semantic comparisons, direct figure review, and chart binding.
- `expected/`: deterministic expected text outputs. `<OUTPUT_DIR>` is a placeholder substituted for the caller's chosen output directory by `run_example.py`.

Run from any working directory using absolute paths (see `references/usage.md` at the bundle root). Optional `--preview-png` and `--preview-pdf` independently export real previews when installed tools are available. Rendering never adds the explicitly unspecified pump, waste, bypass, or recycle connections.
