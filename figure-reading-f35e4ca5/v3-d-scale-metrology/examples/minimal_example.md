# Minimal example — 合成示例 / synthetic 示意输出

Everything on this page is **synthetic / 合成** demo output produced by
`examples/make_synthetic_case.py`; it does not come from a real sample.

## 1. Generate the synthetic case

```
python3 examples/make_synthetic_case.py --out /tmp/f35e-d-demo
# SYNTHETIC case written to: /tmp/f35e-d-demo
#   blobs placed: 40 (mean equiv diameter 76.5 px = 191.2 nm)
#   bar: 200 px at bbox [764, 698, 200, 12], label '500 nm'
```

## 2. Detect the scale bar

```
python3 /skills/weekly-skill/scripts/find_scalebar.py \
    --image /tmp/f35e-d-demo/synthetic_figure.png \
    --work /tmp/f35e-d-demo/work --out /tmp/f35e-d-demo/work
# Found 1 candidate(s). Wrote .../scalebar_candidates.json
#   cand 0: horizontal len=200.0 px bbox=[764, 698, 200, 12] crop=.../label_crop_cand0.png
# exit code 0
```

Open `label_crop_cand0.png` (3× zoom, contrast-stretched) and read the label
verbatim: **"500 nm"**.

## 3. Write calibration.json (agent step)

```json
{"length_value": 500, "unit": "nm", "length_px": 200.0,
 "endpoint_uncertainty_px": 2, "candidate_index": 0,
 "verbatim_label": "500 nm",
 "bar_bbox": [764, 698, 200, 12],
 "label_region": [750, 658, 228, 66]}
```

## 4. Measure

```
python3 /skills/weekly-skill/scripts/measure_features.py \
    --image /tmp/f35e-d-demo/synthetic_figure.png \
    --calibration /tmp/f35e-d-demo/work/calibration.json \
    --work /tmp/f35e-d-demo/work --out /tmp/f35e-d-demo/work
# objects: 40 (excluded: 0), segments: 0
# count=40  mean diameter=193.5 ± 56.4 (sd) nm  median=175.2 nm  (calibration rel. unc 1.00%)
# exit code 0
```

Excerpt of `measurements.json` summary (合成示例 / synthetic):

```json
"summary": {
  "count": 40,
  "mean_diameter": {"value": 193.48, "sd": 56.45, "sem": 8.93,
                    "calibration_unc": 1.93, "unit": "nm", "n": 40},
  "median_diameter": {"value": 175.22, "unit": "nm"}
}
```

## 5. Assemble the fragment + preview

```
python3 /skills/weekly-skill/scripts/metrology_result.py \
    --image /tmp/f35e-d-demo/synthetic_figure.png \
    --measurements /tmp/f35e-d-demo/work/measurements.json \
    --out /tmp/f35e-d-demo/output
# calibration: 500 nm = 200.00 px (±2.0 px), 2.5 nm/px
# status_suggestion: success
# exit code 0
```

`annotated_preview.png` shows every particle outlined and numbered 001–040,
the scale bar outlined in red, and the calibration caption. Inspect it before
trusting the numbers.

## Accuracy note (synthetic ground truth)

The synthetic ground truth (`ground_truth.json`, not shipped to the agent in
a real case) says: count 40, mean equivalent diameter 191.25 nm, sd 56.40 nm,
median 172.16 nm. The pipeline recovered **40 / 40 particles** and a mean of
**193.48 nm** — a +2.24 nm (+1.2%) deviation, consistent with the ground
truth within the standard error of the mean (8.93 nm) and essentially at the
calibration floor (±1.93 nm, from ±2 px over 200 px); the small residual is
threshold-edge bias, exactly the kind of effect the annotated preview exists
to catch.
