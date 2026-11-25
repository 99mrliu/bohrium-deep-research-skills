# Source-span atlas report

**synthetic-minimal-source-span-atlas — SYNTHETIC example only; not scientific evidence.**

Verdict: **passed**

> A normalized quote hit establishes only a source span. Scientific meaning requires the separately recorded semantic comparison and, for original figures, direct visual inspection. This report does not automate scientific judgement.

## Sources

| Source | Kind | SHA-256 | Declared path | Version |
|---|---|---|---|---|
| methods | methods | `75ccb7e905bbca223dcb11488824b72df73c881f049c9d8d9f78615a3a43552f` | sources/methods.txt | synthetic-methods-v1 |
| figure03 | figure | `1f851fa3bc8acacd9c7a0df495314c79e71bc31084846dd3dc1a75c3b27bcfe2` | sources/original_figure03.svg | synthetic-figure03-v1 |
| measurements | csv | `d99cf28841a59a5f09e7ca2ba70dd776597d9223d6bab01a784407ceb1bb27e2` | data/measurements.csv | synthetic-csv-v1 |

## Assertion-to-source-to-visual coverage

### A_RESERVOIR — Sample reservoir

- Category/status: `entity` / `explicit`; visual: `visual-reservoir`.
- Separate semantic review: `match`. Methods name a sample reservoir and original Figure 03 panel a visibly shows the same leftmost entity; the visual node denotes that entity, not a pump or generic container.
- `methods`, page 1, lines 4–4, Synthetic Methods; original offsets `[69, 125]`; normalized offsets `[68, 124]`.
  - Exact source excerpt: “The sample reservoir is connected to the two-port valve.”
### A_VALVE — Two-port valve

- Category/status: `entity` / `explicit`; visual: `visual-valve`.
- Separate semantic review: `match`. The source explicitly specifies a two-port valve; original Figure 03 shows the labelled middle unit with one depicted inlet and one depicted outlet, matching this node without adding a bypass.
- `methods`, page 1, lines 4–4, Synthetic Methods; original offsets `[69, 125]`; normalized offsets `[68, 124]`.
  - Exact source excerpt: “The sample reservoir is connected to the two-port valve.”
### A_DETECTOR — Detector

- Category/status: `entity` / `explicit`; visual: `visual-detector`.
- Separate semantic review: `match`. The methods identify the detector downstream of the valve and direct inspection sees Detector as the rightmost unit; the output preserves direction and adds no return path.
- `methods`, page 1, lines 5–5, Synthetic Methods; original offsets `[126, 174]`; normalized offsets `[125, 173]`.
  - Exact source excerpt: “The two-port valve is connected to the detector.”
- `figure03`, page 1, lines 3–3, Figure 03, panel a; original offsets `[288, 335]`; normalized offsets `[284, 331]`.
  - Exact source excerpt: “Detector downstream of valve; no recycle arrow.”
### A_FLOW_RESERVOIR_VALVE — Reservoir to valve

- Category/status: `connection` / `explicit`; visual: `visual-edge-reservoir-valve`.
- Separate semantic review: `match`. The prose supplies the pair, while the original figure's visible left-to-right arrow supplies depicted direction; the drawn edge ends at Two-port valve and does not imply an unsupported pump.
- `methods`, page 1, lines 4–4, Synthetic Methods; original offsets `[69, 125]`; normalized offsets `[68, 124]`.
  - Exact source excerpt: “The sample reservoir is connected to the two-port valve.”
### A_FLOW_VALVE_DETECTOR — Valve to detector

- Category/status: `connection` / `explicit`; visual: `visual-edge-valve-detector`.
- Separate semantic review: `match`. The prose supplies the valve-detector pair and the original figure visibly shows the arrow from valve to Detector; the output follows that direction and does not reverse it.
- `methods`, page 1, lines 5–5, Synthetic Methods; original offsets `[126, 174]`; normalized offsets `[125, 173]`.
  - Exact source excerpt: “The two-port valve is connected to the detector.”
### A_LOAD — Load the sample

- Category/status: `step` / `explicit`; visual: `visual-step-load`.
- Separate semantic review: `match`. The verb sequence begins with load the sample; order badge 1 preserves the source order and does not introduce preparation or priming steps.
- `methods`, page 1, lines 6–6, Synthetic Methods; original offsets `[175, 232]`; normalized offsets `[174, 231]`.
  - Exact source excerpt: “The procedure is load the sample, then inject the sample.”
### A_INJECT — Inject the sample

- Category/status: `step` / `explicit`; visual: `visual-step-inject`.
- Separate semantic review: `match`. The word then places inject the sample after loading; order badge 2 preserves that sequence and no recycle or termination step is inferred.
- `methods`, page 1, lines 6–6, Synthetic Methods; original offsets `[175, 232]`; normalized offsets `[174, 231]`.
  - Exact source excerpt: “The procedure is load the sample, then inject the sample.”
### A_STEP_ORDER — Then

- Category/status: `connection` / `explicit`; visual: `visual-edge-step-order`.
- Separate semantic review: `match`. Then explicitly links injection after loading in this procedure; the arrow is temporal between steps, not an invented material connection between apparatus units.
- `methods`, page 1, lines 6–6, Synthetic Methods; original offsets `[209, 231]`; normalized offsets `[208, 230]`.
  - Exact source excerpt: “then inject the sample”
### A_NO_RECYCLE — No pump, waste, bypass, or recycle is added; none is specified.

- Category/status: `note` / `explicit`; visual: `visual-note-omissions`.
- Separate semantic review: `match`. The methods explicitly prohibit these additions and direct Figure 03 inspection sees no recycle arrow; the note records absence rather than drawing a speculative dashed connection.
- `methods`, page 1, lines 7–7, Synthetic Methods; original offsets `[233, 316]`; normalized offsets `[232, 315]`.
  - Exact source excerpt: “No pump, waste line, bypass, or recycle connection is specified; none may be added.”
### A_RESPONSE_CHART — Synthetic detector response

- Category/status: `data` / `explicit`; visual: `chart-response`.
- Separate semantic review: `match`. Methods define time_s and response semantics; actual CSV rows 2–4 encode 0.0/12.5, 1.0/19.0, 2.0/26.5 and exactly these pairs, units, ordering, and headers are plotted without fitting.
- `methods`, page 1, lines 8–8, Synthetic Methods; original offsets `[317, 486]`; normalized offsets `[316, 485]`.
  - Exact source excerpt: “For the synthetic response chart, time_s is elapsed time in seconds and response is detector response in arbitrary units. Measurements are shown for 0, 1, and 2 seconds.”

## Direct original-figure reviews

- `F03_DIRECT_REVIEW`: direct_visual; panels ['a']; reviewed SHA-256 `1f851fa3bc8acacd9c7a0df495314c79e71bc31084846dd3dc1a75c3b27bcfe2`. Panel a visibly places Sample reservoir left of Two-port valve and Detector right of the valve, with left-to-right arrows and no recycle arrow; this agrees with, but does not replace, the methods comparison.

## Actual CSV mappings

- `chart-response` binds **case-sensitive columns** `time_s` and `response` from `measurements`; no imputation.
  - CSV row 2: `time_s`=0.0, `response`=12.5 → `chart-response`.
  - CSV row 3: `time_s`=1.0, `response`=19.0 → `chart-response`.
  - CSV row 4: `time_s`=2.0, `response`=26.5 → `chart-response`.

## Conflicts

- `X_VALVE_SYNONYM` (resolved): A non-source draft synonym 'switch' conflicts with the source term 'two-port valve'. Resolution: Retain the explicit source term two-port valve; do not treat a possible synonym as equivalent without source support. Visual treatment: Only Two-port valve appears; the unsupported alias is omitted.

## Source-to-visual coverage

Bidirectional coverage passed: **True**. Expected/scientific visuals: 10/10.
- `figure03` → `visual-detector`
- `measurements` → `chart-response`
- `methods` → `chart-response`, `visual-detector`, `visual-edge-reservoir-valve`, `visual-edge-step-order`, `visual-edge-valve-detector`, `visual-note-omissions`, `visual-reservoir`, `visual-step-inject`, `visual-step-load`, `visual-valve`

## Gate findings

No gate errors. This is not a scientific correctness certificate.
