# 示例 / Worked EXAMPLE (synthetic data — all numbers illustrative)

This is a fully worked **示例** using invented data. It demonstrates the
draw → read-back → verify → repair loop, including a deliberately wrong
column mapping that the verifier CATCHES.

## 1. Synthetic source data `signals.csv`

```csv
group,WT,KO,WT_err,KO_err
Ctrl,1.20,0.90,0.10,0.08
Low,2.30,1.70,0.15,0.12
Mid,1.80,2.20,0.09,0.14
High,2.90,2.40,0.18,0.10
Max,3.40,3.00,0.20,0.16
```

## 2. `figure_plan.json`

```json
{
  "title": "示例 bar chart",
  "width_mm": 89, "height_mm": 70, "style": "default_pub", "mode": "chart",
  "panels": [{
    "id": "p0", "type": "bar",
    "categories": ["Ctrl", "Low", "Mid", "High", "Max"],
    "series": [
      {"name": "WT", "values": {"file": "signals.csv", "column": "WT"},
       "yerr": {"file": "signals.csv", "column": "WT_err"}},
      {"name": "KO", "values": {"file": "signals.csv", "column": "KO"},
       "yerr": {"file": "signals.csv", "column": "KO_err"}}
    ],
    "x_label": "Group", "y_label": "Signal", "y_unit": "a.u."
  }]
}
```

## 3. The four commands

```bash
python3 $SKILL_DIR/scripts/make_result.py --case case.json \
    --out /app/output/result.json --status partial --note "intake"
python3 $SKILL_DIR/scripts/draw_figure.py figure_plan.json \
    --out /app/output/figure --formats svg,png,pdf
python3 $SKILL_DIR/scripts/readback_verify.py --svg /app/output/figure.svg \
    --plan figure_plan.json --report /app/output/verify_report.json
python3 $SKILL_DIR/scripts/export_check.py /app/output/figure.svg \
    /app/output/figure.png /app/output/figure.pdf \
    --report /app/output/export_report.json
```

## 4. Expected verify_report.json excerpt (PASS)

```json
{
  "summary": {"pass": 13, "fail": 0, "warn": 0, "unverifiable": 0,
              "overall": "pass"},
  "transform": {"axes_1": {"y": {"a": -44.01, "b": 167.80}, "x": null,
                           "x_cats": [{"label": "Ctrl", "px": 49.9}, ...]}},
  "recovered_values": {
    "WT": [1.2, 2.3, 1.8, 2.9, 3.4],
    "KO": [0.9, 1.7, 2.2, 2.4, 3.0]}
}
```

Every recovered value equals the CSV cell it came from (deviation ≈ 1e-4
of the axis span; tolerance = 2 % of span).

## 5. Second run — deliberately corrupted plan (CAUGHT)

Swap the two series' column bindings (WT now reads column `KO` and vice
versa) but re-verify against the SAME, correct figure:

```json
{"name": "WT", "values": {"file": "signals.csv", "column": "KO"}, ...}
```

The verifier prints:

```
verify: overall=fail  pass=11 fail=2 warn=0 unverifiable=0
  [FAIL] bar_values@p0/WT: series 'WT' bars: 0/5 values match within
  tol=0.05; mismatches: [{"index": 0, "category": "Ctrl",
  "expected": 0.9, "recovered": 1.2, "abs_dev": 0.3}, ...
```

and the machine-readable repair directive says exactly what to do:

```json
{"id": "bar_values@p0/WT", "status": "fail",
 "repair": {"action": "fix_plan", "target": "series 'WT' bars",
  "suggestion": "re-bind 'values' to the correct source column; recovered
   values [1.2, 2.3, 1.8, 2.9, 3.4] came from the SVG, expected
   [0.9, 1.7, 2.2, 2.4, 3.0] came from signals.csv#KO. If recovered equals
   another series' expected values, that series' column was swapped in."}}
```

Note the anatomy: `recovered` (from the SVG geometry) equals the TRUE WT
column, while `expected` (from the corrupted plan) equals the KO column —
the directive tells you the two were swapped. Fix the plan binding,
re-draw, re-verify: round 2 passes. Save each round as
`verify_report_roundN.json` and record the rounds in `result.json`'s
`change_record`.

## 6. Negative-path behavior (also 示例)

- CSV with empty/`NaN` cells → drawer logs
  `"nan_gap: series 's' dropped 2 NaN/empty points"`; the verifier treats
  them as expected gaps and still passes the remaining points.
- Plan naming a missing column → drawer exits 2:
  `column 'nonexistent' missing in signals.csv (available: group, WT, KO, ...)`.
- Chinese labels with no CJK font installed → drawer continues and logs
  `cjk_font_missing`; the verifier warns that font rendering is
  unconfirmed so you inspect the PNG (tofu 口 risk).
- PNG re-saved at 96 dpi → `export_check` fails `png_dpi: dpi=96 <
  required 300`; PNG with the pHYs chunk stripped fails
  `dpi unspecified`.
