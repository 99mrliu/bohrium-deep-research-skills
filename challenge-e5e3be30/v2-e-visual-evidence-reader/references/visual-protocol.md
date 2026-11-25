# Visual evidence protocol

## 1. Evidence identity and actual observation

For each rendered page retain the source PDF SHA-256, page number, DPI, PNG SHA-256, dimensions, and non-empty byte count. `render-pdf` uses `pdftoppm` and refuses missing or empty output. Verify the receipt before calibration. Opening a receipt, inspecting a filename, extracting a PDF text layer, or generating a thumbnail is not the same as the Agent seeing the figure.

An Agent visual assertion requires an actual image-opening/vision operation on that rendered PNG. Only after that operation may the Agent run `mark-opened --actually-opened --observer '...'` on the verified non-synthetic receipt; rendering never sets the observation flag automatically. The attestation does not replace or retroactively prove vision-tool use. If that operation is unavailable or fails, say so and use `insufficient_evidence` for vision-dependent claims. The synthetic example uses programmatic coordinates on synthetic data and must never be described as Agent vision or a real-paper reproduction.

## 2. Figure reading before numbers

Record source/page/panel, figure title and caption, axis labels and units, tick values, scale (`linear` or `log`), legend entries, group/series identity, marker/color mapping, and error-bar presence and stated meaning. A conventional-looking error bar is not automatically a standard deviation or 95% interval. Note occlusion, clipping, antialiasing, low resolution, overlapping series, and ambiguous ticks. Separate directly read labels from inference.

## 3. Measurement JSON

A one-dimensional axis example:

```json
{
  "schema_version": "1.0",
  "measurement_origin": "agent_visual_measurement",
  "observer": "Agent; image opened with vision tool",
  "figure": {"source": "paper.pdf", "page": 3, "panel": "b"},
  "pixel_space": {"origin": "top_left", "x_direction": "right", "y_direction": "down", "units": "pixel"},
  "calibration": {
    "x": {"scale": "linear", "units": "dose (mg)", "max_residual_data_units": 0.05, "points": [{"pixel": 91.2, "value": 0}, {"pixel": 781.4, "value": 10}]},
    "y": {"scale": "log", "base": 10, "units": "response", "max_residual_data_units": 0.05, "points": [{"pixel": 622.1, "value": 1}, {"pixel": 91.7, "value": 1000}]}
  },
  "points": [{
    "label": "treated, 10 mg, central marker",
    "pixel": [780.9, 220.4],
    "figure_coordinate": {"space": "figure_fraction", "x": 0.84, "y": 0.68},
    "pixel_sigma": [1.0, 1.5],
    "series": "treated",
    "legend_label": "treated",
    "group": "cohort A",
    "error_bar": {"present": true, "meaning": "caption states standard error", "read": false}
  }]
}
```

`figure_coordinate` is descriptive and is never substituted for pixels in the calibration calculation. Pixel uncertainty should reflect marker width, line width, zoom, resolution, and observer repeatability; do not default to implausibly perfect precision. Use `measurement_origin: synthetic_programmatic_measurement` only for the marked synthetic example. An origin string cannot prove Agent observation, so retain the actual observation in the run record.

For a two-dimensional affine rectification, replace `calibration.x` and `.y` with:

```json
"calibration": {"mode": "affine2d", "points": [{"pixel": [10, 20], "value": [0, 0]}, {"pixel": [110, 20], "value": [1, 0]}, {"pixel": [10, 120], "value": [0, 1]}]}
```

At least three non-collinear control points are required; more points yield least-squares estimates and residuals. Collinear or duplicate controls are degenerate and must fail. One-dimensional controls must be distinct and well separated. Log scales fit the logarithm of value, require positive values, and must not pass through a hidden linear transform without disclosure.

## 4. Readback and uncertainty

`readback` fits `linear` value = `a * pixel + b`; `log` fits `log_base(value) = a * pixel + b`; `affine2d` fits both coordinates from both pixel coordinates. It recomputes fitted controls and residuals, then reports estimated values and uncertainty propagated from `pixel_sigma`. Data-unit residual thresholds are mandatory for axis calibration. The tool does not replace visual judgment with an optimizer.

Quantization is reported separately from calibration residuals. A readback such as 81.9 ± 1.2 is compatible with a source value of 82, but cannot prove an exact value of 82.000. Report a range when asymmetric resolution/occlusion dominates. Never promote graph readback to an exact original table value.

## 5. Tables and captions

For each table cell record PDF/page/table, zero-based or explicitly declared row and column indices, raw cell text/value, row-header path, and ordered column-header path. Example:

```json
{"page": 8, "row_index": 4, "column_index": 2, "row_header_path": ["Treatment", "Cohort A"], "column_header_path": ["Change from baseline", "Week 12", "Mean (SE)"], "value": "-2.1 (0.4)"}
```

Retain header hierarchy and units. On continuation pages copy only headers visibly carried forward or unambiguously identified by a continued-table caption; cite both the original and continuation pages when needed. Never infer a blank cell is zero.

## 6. Verdict discipline

- `supported`: every material part is affirmatively supported at the stated precision.
- `partially_supported`: at least one material part is supported and another is unsupported, uncertain, or only bounded. Explain the split.
- `contradicted`: affirmative evidence is incompatible with the claim. Absence of a mention is not contradiction.
- `insufficient_evidence`: the available evidence cannot decide the claim, including exactness beyond graphical precision or an unreadable/occluded region.

Topic similarity is never support. Preserve competing measurements, panels, legends, or captions as parallel conflict entries with source identity; do not silently average or select one.

## 7. Adaptive result contract

`scaffold` accepts dictionary and list contracts. Dictionary keys are output field names; simple `type`, `fields`, or `properties` hints guide empty values. List entries may be field-name strings or objects containing `name`, `key`, or `field`. All are emitted at the top level with `case_id`, `status`, `sources`, `uncertainty`, and `change_records`. Reserved runtime fields cannot be overridden by a contract.

`validate-result` checks required keys, case identity, allowed verdict values where claim assessments are present, source/uncertainty/change-record container types, and partial-status honesty for unresolved claim assessments. It checks structure, not scientific truth; Agent review remains required. Every material change should append a timestamped or sequenced change record describing evidence and uncertainty changes.
