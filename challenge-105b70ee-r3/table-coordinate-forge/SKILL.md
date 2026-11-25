---
name: table-coordinate-forge
description: >-
  Reconstruct PDF table rows, columns, spanning cells, and continued headers from
  pdftotext -bbox-layout XHTML coordinates, then bind requested scientific fields
  to reviewed cells with verbatim values, units, conditions, and cell-level evidence.
  Use when table values are lost, shifted, or detached from row/column conditions;
  not for generic keyword extraction or text-layer cleaning.
---

# Table Coordinate Forge

## Purpose and invariant

Build **upstream layout truth first**. Turn each real PDF into coordinate-bearing
XHTML, reconstruct candidate table geometry, inspect that geometry, and only then
make semantic field decisions. The pipeline never searches a target name and
automatically promotes the nearest number. Geometry candidates are not answers.

The final authority is the original case PDF plus the requested field definitions.
The generated XHTML and tables are navigable evidence, not a substitute for visual
review when coordinates are ambiguous.

## Runtime workflow (required two-pass pattern)

At execution time, read the actual `/input/case.json`,
`/input/target-fields.json`, and `/input/task.md`. Read all real PDFs supplied
under `/input`; do not infer contents from filenames or domain labels. Work in
`/app/work` and retain deliverables in `/app/output`.

Set `SKILL_HOME` to this installed skill directory. No installation, network
access, or third-party Python package is needed. Python 3.9+ and the standard
library are sufficient; `pdftotext` is optional only when bbox XHTML is already
available.

### Pass 1 — write a safe partial immediately and reconstruct geometry

```bash
python3 "$SKILL_HOME/scripts/runtime.py"
```

Defaults are exactly:

```text
--input-dir /input --work-dir /app/work --output-dir /app/output
```

The script writes `/app/output/result.json` before PDF parsing. It then finds PDFs,
runs the equivalent of `pdftotext -bbox-layout DOCUMENT.pdf DOCUMENT.bbox.xhtml`,
and produces:

- `/app/work/layout.json`: pages, physical lines, words, and coordinates;
- `/app/work/tables.json`: candidate tables, segments, grid cells, and header paths;
- `/app/work/reviewed-bindings.template.json`: one unfinished record per target;
- `/app/output/table-preview.md`: human-reviewable cells with stable IDs;
- `/app/output/table-preview.svg`: searchable text/vector layout preview;
- `/app/output/result.json`: still partial, with no auto-promoted scalar.

Check `/app/work/tables.json` and both previews. For each table, verify its first
row really is a header, inspect continuation links, and compare any suspicious
row/span against the original PDF. Candidate detection can be wrong; do not repair
it by inventing text or silently changing a coordinate-derived quote.

### Pass 2 — author reviewed bindings and validate atomically

Copy the template to `/app/work/reviewed-bindings.json`. For every requested
`field_id`, explicitly choose one of `reported`, `not_reported`,
`source_conflict`, or `extraction_failed`. For a reported field, supply the value
cell, its row and effective column headers, exact expected header text, and every
condition-bearing cell. See `references/reviewed-bindings.md` for the full schema.

```bash
python3 "$SKILL_HOME/scripts/runtime.py" \
  --bindings /app/work/reviewed-bindings.json
```

The second pass reconstructs the same geometry, verifies exact cell IDs and
expected text, validates the result contract, and only then atomically replaces
`result.json`. A rejected binding leaves a contract-valid partial output and an
actionable `binding_rejected` uncertainty. Do not bypass this by manually editing
reported scalars into the result.

## Semantic binding decisions

1. **Read the target definition, not an expected answer.** Match the requested
   experimental meaning to a complete cell path. A lexical match alone is not
   semantic correctness.
2. **Bind a value cell only with its coordinate context.** Include same-row keys,
   inherited and repeated continued headers, units, timing, dose, sample,
   baseline/comparator, and footnote or spanning-note cells needed to interpret it.
   Preserve every condition that changes the requested reading.
3. **Keep source text verbatim.** `scalar` must be a literal substring of the value
   cell; `quote` is the complete cell text. Do not round, normalize significant
   figures, convert units, split ranges, replace Unicode symbols, expand error
   notation, or turn absence into zero. `units` must occur verbatim in a reviewed
   value/header cell.
4. **Set `experimental_condition` and its `condition` alias to exactly the same
   reviewed string.** Put statistical meaning in `statistic`; keep comparator or
   baseline in `comparator`. Use null when genuinely inapplicable, not when merely
   unreviewed.
5. **Use `not_reported` only after a stated complete review scope.** Its notes must
   name reviewed pages/segments/headers. If the table was too damaged to review,
   use `extraction_failed` instead. Conflicting supported readings remain
   `source_conflict` with all exact value evidence and a null scalar.
6. **Leave unbound fields failed rather than guessing.** Missing bindings become
   `extraction_failed`; there is exactly one output record per requested field in
   target order, and no `result.field_results` mirror is emitted.

Read `references/geometry-rules.md` for gutter thresholds, spanning geometry,
continued-table joining, and review triggers. Read `references/failure-and-output.md`
for status logic and the exact output contract.

## Dependency and failure handling

`pdftotext` from Poppler is used only as an external coordinate extractor. If it
is missing or fails, the output states the failure and gives this actionable
fallback:

```bash
pdftotext -bbox-layout DOCUMENT.pdf DOCUMENT.bbox.xhtml
```

Supply the resulting `.xhtml` as input (or a filename containing `bbox` for XML),
then rerun. Do not use plain `pdftotext -layout` output: flattened spaces cannot
reconstruct trustworthy coordinates. Scanned PDFs without a text layer require a
separate OCR-plus-coordinates stage; this skill does not pretend that OCR text is
PDF text-layer truth.

For ambiguous merged cells, multiple header rows, rotated pages, or candidates
that omit needed rows, keep affected fields `extraction_failed`, identify the
segment/page, and request visual review. If no requested value is supported after
a complete effort, final status is `insufficient_evidence`; if only some fields
are resolved, use `partial`; well-supported `not_reported` and `source_conflict`
records are resolved field decisions, so an all-resolved case can be `answered`.

## Synthetic verification example

Everything under `examples/minimal/` is a **synthetic example, never official
results**. From the skill root, run:

```bash
python3 examples/minimal/run_example.py
```

The runner performs both runtime passes, verifies two reported values and one
scoped not-reported field, checks continued page-2 condition evidence, parses the
SVG as XML, and runs a deliberate failure test. The failure changes expected
`Yield (%) at 24 h` to `Yield (%)`; exit code 2 is required and all scalars must
remain null in the failure-output result. Actual commands and inspected artifacts
are recorded in `examples/minimal/INSPECTION.md`.

## Scope limits

This is not generic keyword extraction, prose cleaning, OCR, unit conversion, or
an answer dictionary. The geometry engine is deliberately conservative and tuned
for unrotated, coordinate-driven tables with repeated vertical gutters. Wrapped
multiline logical rows, border-only tables without repeated gutters, complex
rowspans/colspans, and header hierarchies beyond the candidate first row require
agent review or a geometry extension. A clean preview does not itself validate a
scientific interpretation.
