# PDF visual inspection and region protocol

## 1. Establish physical pages

Run both extraction modes through the CLI, not just prose-oriented extraction:

```bash
pdftotext -enc UTF-8 source.pdf normal.txt
pdftotext -layout -enc UTF-8 source.pdf layout.txt
```

The supplied `ingest` command does this and fails clearly if Poppler is unavailable. Do not pass `-nopgbrk`: form feed (`U+000C`) is the page boundary. PDF logical page labels can differ from physical page numbers. Region `page` is always the one-indexed physical page in the PDF. Compare normal/layout streams for dropped lines, reordered columns, or missing caption adjacency; the two streams are complementary, not independent confirmation.

## 2. Recover table rows with their ancestors

Inspect the header above a value before interpreting it. For grouped headers record an ordered path such as:

```json
["Adsorption", "Methyl orange", "Removal (%)"]
```

For this bundle's simple layout drafts, `>` separates header ancestors, a final parenthesis or bracket supplies units, and `{test}` supplies a sample split, for example `Removal (%) {test}`. These are parsing conventions, not universal unit semantics. Do not infer units that are absent.

Alignment matters. A blank leading cell in a visually grouped second row can inherit a material, sample, or condition from the preceding row. Preserve both the literal `source_value` and the carried `value`, and put inherited entries in `multirow_context`. Never forward-fill across a new section, sample split, or header without visual confirmation. `NR`, blank, em dash, and zero are not interchangeable; classify their meaning from source context.

Recommended IDs when the workorder supplies none:

- prose: original extraction paragraph ID, e.g. `DOC17:p0042`;
- table: `DOC17:table-002-row-003`;
- figure: `DOC17:figure-001-panel-b`;
- caption: `DOC17:caption-001`.

Supplied IDs override these conventions. Do not renumber existing IDs during cleanup.

## 3. See the figure

Render only relevant physical pages, initially at 180–220 dpi; increase resolution when ticks or panel labels are small:

```bash
python3 scripts/visual_evidence.py render-pages \
  --pdf /input/source.pdf --pages 7 --output-dir /app/work/page-images --dpi 220
```

Inspect the PNG with agent vision and/or OCR. Identify panel label, axes, units, transformations, legend/group, sample definition, error bars, and nearby caption before reading a point. Trace each read-off to the precise panel region. A caption saying “about twice” or “stable” supplies context, not a precise curve number. Axis tick labels alone also do not identify a data value without reading the curve/bar/point.

Record image paths in `visual_inspection.paths`, `sources`, and/or `change_records`, together with method and notes. If the runtime creates a cropped preview or PDF diagnostic, keep it under `/app/work`, not in the text-only submitted bundle.

## 4. Represent uncertainty and unreadability

Exact table/prose values may use:

```json
{"status":"reported", "value":82, "units":"%"}
```

A figure read-off must use a different shape:

```json
{
  "status":"read_off_figure",
  "value":null,
  "estimate":48,
  "range":[45,52],
  "units":"%",
  "uncertainty":{"note":"Approximate visual read-off between coarse ticks; not a reported CI."},
  "visual_inspection":{"method":"agent_vision","paths":["/app/work/page-images/page-0007.png"],"notes":"Panel b, final series point."}
}
```

A range is an honest uncertainty interval unless the source defines it otherwise; do not label it a confidence interval. Do not round a visual estimate into a deceptively precise number. If no defensible estimate/range is possible, do not invent one: record `not_reported` or `noncomparable` with the unreadability reason.

## 5. Comparison and derivation gate

Before any quantitative synthesis, test exact semantic agreement of task, metric, units, material, pollutant, and budget. Also test dataset and dye IDs. Different dyes, train/test splits, concentrations, cycles, doses, time points, adsorption/degradation tasks, or unknown unit systems remain separate rows. The matrix intentionally contains one row per extraction/region and performs no aggregation.

Derived arithmetic requires source record IDs and a visible derivation expression. It must not turn figure estimates into exact source values, average unlike datasets/dyes, or hide missing qualifiers. Use `noncomparable` where the scientific question differs despite superficially similar percentages.

## 6. Final provenance review

Read the matrix and source-region ledger as an auditor:

- every document and matrix field appears;
- every matrix row carries exact `source_document_id` and `paragraph_id`;
- every nonprose extraction resolves to `region_id` and physical page;
- table header path, units, sample split, and multirow context survive;
- figure panel labels, estimate/range, uncertainty, and actual visual path survive;
- captions never stand alone behind curve numbers;
- `not_reported` and `noncomparable` are still explicit;
- status, sources, uncertainty, and change records reflect what was actually done.
