# Provenance record schema (claims.json)

Every number reported to the user must be traceable through one of these
records. `make_result.py` refuses `status: success` while any claim lacks
locatable evidence.

## Claim object

```json
{
  "claim": "The control group mean at day 7 is 0.42",
  "value": 0.42,
  "unit": "OD600",
  "evidence": [
    {
      "source_type": "table_cell",
      "locator": "table_s2.csv#row-8#col-mean",
      "verbatim": "day7,control,0.42,0.05"
    },
    {
      "source_type": "figure_region",
      "locator": "fig_3b.png#axes(34,410)-(520,40)#x[6.5,7.5]#y[0.36,0.48]",
      "verbatim": "blue bar top at ~0.42 with error bar to 0.47"
    }
  ],
  "crosscheck": "matched"
}
```

## Fields

- `source_type` — one of:
  - `table_cell` — value copied from an original table shipped with the
    case. `locator` = `<file>#row-<n>#col-<name>` (1-based data rows).
  - `figure_region` — value read from the figure image. `locator` must
    name the figure file, the plot-area pixel box, and the data-region
    rectangle the reading was taken from, e.g.
    `fig_3b.png#axes(34,410)-(520,40)#x[6.5,7.5]#y[0.36,0.48]`. Plain
    "figure 3" is NOT a locator.
  - `caption_verbatim` — the figure caption states it. `verbatim` must be
    an exact quote.
  - `text_sentence` — stated in body text. `verbatim` must be an exact
    quote plus `locator` = `<file-or-page>#para-<n>` or `#page-<n>#line-<n>`.
  - `derived` — computed from other claims (ratios, slopes, AUC). List the
    input claims in `verbatim` ("= slope of claim-3 over x in [0.2, 0.8]").
- `locator` — machine-checkable pointer into the actual case files; never
  a paraphrase.
- `verbatim` — the exact characters / observed pixels the value came from.
- `crosscheck` — `matched` (figure reading confirmed against a table/caption
  within tolerance), `unmatched` (no confirming source found; the value is
  reported but flagged), `no_anchor` (nothing to check against).

## Anti-fabrication rules

1. If the figure and a table disagree, report BOTH values and mark the
   claim `unmatched` with the disagreement spelled out. Never average them.
2. A value that appears in no case material is not reported, full stop.
   Domain priors ("typical band gaps are 1–3 eV") are not evidence.
3. "Not reported" is a deliverable answer: record it as a claim with
   `value: null`, evidence of type `text_sentence` quoting the caption or
   noting the absence, and `crosscheck: "no_anchor"`.
4. Reading error (from `anchor_map.json` calibration residuals) travels
   with every figure-sourced value: `±` half the residual scale, stated in
   the answer text.
