# Chart and visual-channel configuration

The workorder contains `chart`; this is visual configuration, not a source of numerical data. Allowed chart keys are `type`, `feature`, `title`, `width`, `height`, `x`, `y`, `error`, `channels`, `edges`. Minimum canvas is 800×500. If raw data has multiple features, select exactly one with `chart.feature`; the runner does not infer small multiples.

## Bar

`type: "bar"` uses `x: "group"` and `y: "group_mean"`. `error` can be `group_sem` (default), `group_sd`, or `none`. Each bar is a group mean and each overlaid circle is an independent sample mean. Bar height and error bars use derived statistics, never channel configuration values.

## Scatter

`type: "scatter"` has numeric `x` and `y`, each one of `sample_mean`, `group_mean`, `log2FC`, `neg_log10_p`. Each point is one independent sample mean. Null channel values follow channel policy, but axis values must be present and numeric.

## Edges

`edges` entries contain required `source`, `target`, optional unique `id` and boolean `directed`. In a bar chart, source/target are actual group names; in scatter, they are actual sample IDs. Unknown or self edges fail. Directed edges receive an arrow. Any nonempty edge list requires `channels.edge_width`.

## Channels

```json
"channels": {
  "fill": {
    "column": "group",
    "scale": "categorical",
    "range": ["#3b78a8", "#d17a32"],
    "missing": "skip",
    "out_of_range": "skip"
  },
  "size": {
    "column": "sample_mean",
    "scale": "linear",
    "range": [4, 11],
    "missing": "skip",
    "out_of_range": "clamp"
  },
  "edge_width": {
    "column": "abs_log2FC",
    "scale": "linear",
    "range": [1.2, 5],
    "missing": "skip",
    "out_of_range": "clamp"
  }
}
```

Allowed channel keys are `column`, `scale`, `range`, `domain`, `missing`, `out_of_range`. The column refers to actual derived/sample/group fields such as `group`, `sample_mean`, `group_mean`, `log2FC`, `abs_log2FC`, or `neg_log10_p`.

- If omitted, fill defaults to an actual `group` categorical mapping and default palette. Configured categorical range must cover the complete domain; no category is silently assigned an ambiguous reused color.
- Continuous fill has exactly two `#RRGGBB` colors and interpolates between them.
- Size maps to circle radius; edge_width maps to SVG stroke width. Both require two finite non-negative range numbers.
- Omit `domain` to compute actual observed min/max (or actual sorted categories). Optionally specify a two-number linear domain or string-array categorical domain to test clipping/out-of-range behavior. Both observed and effective domains are audited, with domain source declared.
- Fill `missing` is `skip` or a fallback color. Fill categorical `out_of_range` is `skip` or a fallback color; continuous fill can `clamp` or `skip`.
- Size/edge-width `missing` is `skip` or a non-negative numeric fallback; out-of-range is `clamp` or `skip`.

A skipped mark gets `visible: false`, no fabricated geometry value, and a missing/out-of-range reason in the mark registry. Counts are aggregated per channel. A run fails if every primary data mark is skipped. A degenerate numeric domain is explicitly flagged and maps valid values to range midpoint; its legend is not expanded with invented bounds.

## Stable IDs and SVG inspection

Bar IDs incorporate feature/group; sample/point IDs incorporate feature/group/sample; edge IDs incorporate feature/edge ID. Unsafe XML characters are deterministically escaped. Duplicate IDs fail. Value labels, axes, tick labels, and actual legend domain/range mappings remain text in SVG.

PNG/PDF conversion is actual rendering, not simply renaming text. Final visual checks should include axis range, value-label legibility, overlap, colors, circle radii, line widths, and arrow meaning. Multi-panel figures, arbitrary network layout, inferential model fitting, and general SVG animation are outside scope.
