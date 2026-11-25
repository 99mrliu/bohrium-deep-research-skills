# Expected SYNTHETIC example behavior

All inputs and outputs in this example are synthetic. They do not reproduce a real paper, and the programmatic pixel measurements are not Agent visual observation.

Run `scripts/run_example.sh OUTPUT_DIR` with one optional output directory. It copies `source.csv`, generates `original.png`, `paper.txt`, `claims-to-verify.json`, `case.json`, and an independent approximate-pixel `measurement.json`. It hashes and verifies the non-empty original PNG, computes `actual_readback.json`, compares readback against the CSV source, and truly writes both `annotated.png` and `annotated.svg`. It then writes and validates `result.json` plus `validation.json`.

The approximate treatment response at x=5 is supported at graphical precision. The negative-response claim is contradicted by affirmative positive visual data. The claim of exact 82.000 units is `insufficient_evidence`, because exactness exceeds demonstrated pixel precision; this makes the run `status` partial even though a source CSV comparison is supplied for demonstration.

`actual_readback.json` includes independent axis calibration points, residuals, pixel/figure coordinates, series/group/error-bar metadata, propagated uncertainty, and quantization. `comparison.csv` quantifies signed and absolute readback error against source data without redefining the readback as exact source data. Both annotated image formats must be non-empty, and `manifest.json` records output hashes.

Expected success exit code: 0. Expected failure tests, each exit 1: a missing/unrendered image receipt; duplicate/degenerate one-dimensional calibration; and collinear `affine2d` calibration controls. Generated PNG/SVG files must remain outside the bundle.
