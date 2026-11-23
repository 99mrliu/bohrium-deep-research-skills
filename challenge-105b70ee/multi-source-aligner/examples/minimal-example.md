# Minimal example (SYNTHETIC — 合成示例, not a formal test case)

Synthetic input only: a 3-page artificial main paper PDF **plus a 1-page
artificial supplementary PDF** (deliberately corroborating the main
paper's `152 mAh g-1` capacity and diverging on the ICE value: main
`91.2%` vs SI `90.8%`), plus a synthetic 6-field `target-fields.json`.
All outputs below are 示例 from that synthetic run.

## Commands and observed behaviour (示例)

```bash
python3 scripts/source_scan.py --input-dir /input --work-dir /app/work
# -> scan -> 39 records from MAIN(3p), SI1(1p)

python3 scripts/align.py propose --work-dir /app/work --input-dir /input \
    --output /app/output/result.json
```

Machine proposals on the synthetic inputs (示例):

```text
capacity_composite_100cyc    corroborated   readings=4 values=[['152', 'mahg-1']]
retention_composite_100cyc   single_source  readings=5 values=[['93', '%']]
ice_first_cycle              conflict       readings=8 values=[['90.8', '%'], ['91.2', '%']]
electrode_loading            single_source  readings=1 values=[['12', 'mgcm-2']]
retention_composite_500cyc   none           readings=1 values=[]
high_temp_retention_60c      none           readings=0 values=[]
```

Note what the alignment surfaced automatically: the capacity value is
**corroborated across MAIN and SI1**; the ICE field is a genuine
**cross-source conflict** (main text `91.2%` first formation cycle vs SI
Table S1 `90.8%` duplicate batch); the benchmark line "Retention above 90%
… is a common target" was excluded from grouping as a benchmark-risk line
(kept in `readings` for review); the 500-cycle retention resolves to
`none` because the table cell is `n.d.`.

## After adjudication (示例)

The synthetic run's adjudicated statuses: capacity `reported` (MAIN+SI1
agree), retention/100 `reported` (single source, range `92–95` in the
table noted), ICE `source_conflict` (both readings kept, never averaged),
loading `reported`, 500-cycle retention `not_reported` (`n.d.` cell
quoted), 60 °C retention `not_reported` (paper states high-temperature
behaviour is unreported). Final:

```bash
python3 scripts/align.py check --output /app/output/result.json --work-dir /app/work
# -> check: PASS (6 fields, 0 errors)
```
