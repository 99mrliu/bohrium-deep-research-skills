# Contract field semantics in figure-reading cases

How to interpret common `output_contract` field families, what evidence each one needs,
and how to behave when the evidence is not there. Field *names* vary per case; match by
shape and role, not by exact spelling.

## axes

Typical shape: `figure.axes.x.{type, unit, range}`, same for `y` (sometimes `z`).

- **Evidence**: the figure's axis labels, tick labels, and any axis title. `type` is
  `linear`/`log`/`categorical`/`time` — read it from tick spacing, not from the label
  text. `range` is [min, max] of the *plotted* axis, not of the data.
- **Etiquette**: units go in `unit` exactly as printed (e.g. `"nm"`, `"s"`, not
  "nanometers"). If an axis has no visible unit, `unit: null` + uncertainty entry; do
  not guess from domain knowledge.

## series

Typical shape: `figure.series[]` with `{name, unit, data_points[]}` per element.

- **Evidence**: legend entries, line/marker styles, captions. `name` is the legend text
  verbatim. One element per visually distinct series; if the contract template has one
  element but the figure has three series, emit three elements (the fill merge replaces
  the template list).
- **Etiquette**: an unlabeled series gets a positional name like `"series 2 (unlabeled, dashed)"`
  plus an uncertainty entry — never a fabricated biological/physical name.

## data_points

Typical shape: `[{x, y}, ...]` inside a series.

- **Evidence**: digitized positions read off the axes. Sample the points the question
  actually needs (extrema, crossings, named x values) rather than exhaustively tracing;
  each point you assert must be defensible from pixels or from a shipped table.
- **Etiquette**: values read from pixels are approximate — prefer few honest points over
  many pretend-precise ones. If a shipped table contains the same series, copy from the
  table (exact) and set the locator to the table, not the figure.

## peaks / features

Typical shape: `peaks[]` with `{position, height, width?}` or `{x, value}`.

- **Evidence**: local extrema of a plotted series, peak tables in shipped tables.
- **Etiquette**: report only peaks actually visible/listed. A `value`-bearing dict is
  claim-like: lint requires a `source`/`locator` sibling or a non-empty top-level
  `sources` list — always attach where the number came from.

## statistics

Typical shape: `{n_comparisons, alpha, p_value?, effect_size?}`.

- **Evidence**: the task text (what test was requested), shipped statistics tables, or
  values printed on the figure (p-value annotations, error bars legend).
- **Etiquette**: if the task asks for a comparison you cannot compute from shipped
  materials, set the statistic `null` with a reason; do not run invented tests on
  digitized noise. `alpha` usually comes from the task text — quote it as the locator.

## answers

Typical shape: `answers[]` with `{question, answer, evidence}`.

- **Evidence**: the task.md questions restated in `question`, your conclusion in
  `answer`, and a concrete locator in `evidence` (e.g. `"figure.png series 1, x=4..6"`,
  `"table.csv row 3"`, `"task.md Q2"`).
- **Etiquette**: `answer` states the finding; `evidence` states where it was seen. An
  answer without evidence is a locator violation waiting to happen.

## translations

Typical shape: `{source_text, translated_text, target_language}` or `translations[]`.

- **Evidence**: text in the figure/captions that the task asks to translate.
- **Etiquette**: translate only text that is actually present; quote the original in
  `source_text` verbatim. Do not translate text from figures that were never shipped
  (that is a gap, see below).

## gaps

Typical shape: `gaps[]` (list of strings or `{item, reason}`).

- **Evidence**: figures/tables *mentioned* in text or captions whose pixels/files were
  not shipped; fields of the contract you could not fill.
- **Etiquette**: list declared gaps — never reconstruct a missing figure. An empty
  `gaps: []` is a positive statement ("no gaps"), which is fine when true; a null
  `gaps` is an unfilled field and will be flagged.

## Null-vs-reason etiquette (all families)

1. A required field you cannot fill stays `null` **plus** an `uncertainty` entry
   carrying the field path and the reason, e.g.
   `{"path": "/figure/axes/y/unit", "reason": "y axis unit not printed on figure", "resolved": false}`.
2. Documented nulls pass lint coverage but still block `status: "success"` — that is
   the intended honesty ratchet, not a bug.
3. Never invent a value to make lint pass. A fabricated number is worse than a null:
   the null is auditable, the fabrication is not.
4. When the reason is resolved later (e.g. the unit turns up in a shipped table), fill
   the field via a new fragment and mark the uncertainty entry `"resolved": true`.
