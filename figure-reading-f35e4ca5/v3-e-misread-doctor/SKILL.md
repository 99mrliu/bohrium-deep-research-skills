---
name: misread-doctor-figure-reading
description: 误读诊断 misread detection for scientific figures — named failure taxonomy (对数轴误判 log-as-linear, 单位词头 unit prefix mV/V, 双轴 dual axis, 截断纵轴 truncated axis, 显著性标记 stars-as-data, fit lines, insets, legend swap, %/fraction, cropped axis). Mechanical detectors (axis type check via tick geometry, unit strings, ink topology) fire before reading; each live mode maps to a repair recipe + self-check.
---

# Misread Doctor — 误读模式诊断与修复

Core idea: figure misreading is **not random**. It clusters into a small taxonomy of
named failure modes — log axis read as linear, mV read as V, dual axis bound to the
wrong series, truncated y-origin exaggerating bar differences, significance stars
digitized as data points, fit lines read as data, inset axes ignored, legend swapped,
percent read as fraction, cropped axis. Base agents fail *predictably* along these
modes. This skill is a **diagnostic-first layer, not a reading pipeline**: cheap
mechanical detectors (tick geometry, unit strings, ink topology) tell you **which
failure modes are live in THIS figure BEFORE you read it**, and each live mode maps
to one concrete repair recipe plus one post-read self-check. You still do the actual
reading, but you read *under* the repairs, with the traps already named.

## Runtime contract

Read `/input/case.json` and `/input/task.md` first; the case's `output_contract` defines the exact result fields (any shape — dict, list, or mixed). Work in `/app/work`; final artifacts belong in `/app/output`, including `result.json` carrying the original `case_id` and every output_contract field. Budget is tight (~900 s, 64 model calls): write a valid **partial** result.json early; improve it in place and keep `status` honest (`success` only when every contract field is filled and every claim is locatable; otherwise `partial` with explicit limits). The case ships ONE original figure image plus all original tables; any figure mentioned in text or captions whose pixels are not provided is a declared gap — list it, never reconstruct it. If paths differ outside the harness, pass the real paths with the CLI flags.

## Dependencies

Python 3 standard library + `numpy` (2.x) + `PIL` (12.x) only. The demo generator
additionally uses `matplotlib` (3.x). No network, no pip, no scipy.

## Workflow

0. **Partial result first.** Before any analysis, write `/app/output/result.json`
   with the original `case_id`, every `output_contract` field present (value `null`
   where unknown), `status: "partial"`, empty `sources`/`uncertainty`. Improve it in
   place afterwards.
1. **Write the figure card.** Inspect the figure (zoom liberally) and record
   `/app/work/figure_card.json` — schema in `references/failure_taxonomy.md`:
   verbatim axis labels and units, ≥3 tick labels **with pixel positions** per axis,
   legend entries with colors/markers, chart type, plot-area bounding box, an element
   inventory, and any unit strings found in tables/captions (`table_units`). The card
   is the contract between your eyes and the detectors; tick pixel positions must be
   measured, not guessed.
2. **Axis geometry & unit screen.**
   `python3 /skills/weekly-skill/scripts/detect_axis_geometry.py --card /app/work/figure_card.json --work /app/work`
   Fits each axis's ticks against linear and log models (linear vs log vs
   symlog-suspect), contradicts the declared type when geometry disagrees, detects
   dual-axis structure (two tick columns / two y-unit strings), checks bar charts for
   a truncated origin (with exaggeration ratio), and normalizes unit strings
   (m/µ/u/μ/k/M prefixes, %, ‰, ×10^n) flagging prefix mismatch vs `table_units`.
   Exit 2 means ≥1 live mode — read the flags before touching data.
3. **Non-data ink screen.**
   `python3 /skills/weekly-skill/scripts/detect_nondata_ink.py --image <figure.(png|jpg)> --card /app/work/figure_card.json --work /app/work --out /app/work/nondata_elements.json`
   Geometry heuristics inside the plot-area bbox find star-like blobs above bars,
   horizontal significance brackets, long straight fit lines (RANSAC on ink pixels),
   inset axis frames, and legend markers bleeding into the plot area. Output is a
   candidate list (`action: exclude_from_data`) plus an `agent_confirm` list — you
   MUST visually confirm each candidate on the zoomed image.
4. **Build the repair plan.**
   `python3 /skills/weekly-skill/scripts/repair_plan.py --axis-diag /app/work/axis_diagnosis.json --nondata /app/work/nondata_elements.json --card /app/work/figure_card.json --work /app/work --out /app/work/repair_plan.json`
   Merges both detector outputs into per-mode repair recipes (from the internal
   recipe table, expanded in `references/repair_recipes.md`) and a post-read
   self-check list; also writes a `misread_report.json` skeleton (per mode:
   applied yes/no + evidence) for you to complete.
5. **Read under the repairs, then self-audit.** Read the figure applying every
   repair; fill `misread_report.json` (one evidence line per mode); fold the findings
   into `result.json` — conversions and exclusions go in `sources`, residual doubt
   goes in `uncertainty`, and `status` becomes `success` only when every contract
   field is filled and every claim is locatable.

## Failure catalogue

The 12 named modes (full detail: `references/failure_taxonomy.md`; full recipes:
`references/repair_recipes.md`):

| id | fingerprint | detector | repair (summary) |
|---|---|---|---|
| LOG_AXIS_AS_LINEAR | tick labels 1,10,100 evenly spaced; declared "linear" | tick-geometry fit (log residual ≪ linear) | read values via 10^((py−b)/a); never average raw pixel positions |
| LINEAR_AXIS_AS_LOG | declared "log" but ticks fit linear better | tick-geometry fit | re-fit linear; state correction in uncertainty |
| SYMLOG_SUSPECT | ticks cross zero with log-like spacing of |v| | |v| log fit vs linear | split at 0; read each side with its own law |
| UNIT_PREFIX | axis says mV/µV/kV/ms, table or contract says V/s | unit-string parse vs `table_units` | normalize to contract unit; state factor (e.g. ×1e-3) in sources |
| PERCENT_FRACTION | axis in %, table in 0–1 fractions (or reverse) | unit parse (%/‰/×10^n) | convert once, explicitly; record which form is reported |
| DUAL_AXIS | two y tick columns or two y-unit strings | card structure scan | bind each series to its axis by legend color/marker BEFORE reading; record binding |
| TRUNCATED_ORIGIN | bar chart y-axis min > 0 | range check on bar-like axis | report absolute values AND distortion; never quote bar-height ratios as value ratios |
| CROPPED_AXIS | ticks end before data or panel edge cuts a curve | tick extent vs plot bbox & element inventory | state readable range; values outside are gaps, not extrapolations |
| NONDATA_STAR | small radial blobs floating above bars | component analysis + radial-symmetry test | exclude from data; record as significance annotation with its groups |
| NONDATA_BRACKET | long thin horizontal line (with end caps) above bar pairs | elongated-component heuristics | exclude; record which two groups it compares |
| FIT_LINE | long straight thin line crossing the plot | RANSAC line on ink pixels | exclude; report slope only if asked, labelled "fit", not data |
| INSET_AXIS | small rectangular frame inside plot area | rectangular-frame detection | read inset with its OWN axes; never mix its pixels into the main axes |
| LEGEND_SWAP | ≥2 similar series, legend inside/overlapping plot | legend-strip marker concentration | verify color/marker binding on the zoomed legend before attributing any value |

## Limits

Detectors are **heuristics**: a negative result does not prove absence of a failure
mode, and a positive one is a suspicion, not a verdict — every repair still requires
agent verification against the zoomed figure. Tick fits need ≥3 ticks; unit screening
needs verbatim strings; ink heuristics degrade on dense or low-resolution figures.
Honesty rules: never claim `success` with unresolved `agent_confirm` items; list
undelivered figures as gaps; record every conversion and exclusion in `sources`;
express residual doubt in `uncertainty` rather than silently dropping it.
