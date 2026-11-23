---
name: ga-spec-compiler
description: >-
  Compile a source-anchored JSON figure spec into a deterministic, editable
  graphical abstract (SVG + PNG + PDF). Trigger when the task asks for a
  graphical abstract / 图形摘要 / mechanism schematic / summary figure from a
  paper, case.json, or data files, especially when every entity, relation and
  number must trace back to source material and identical inputs must
  reproduce the identical figure: the model authors one structured spec file,
  a blocking gate verifies every quote and number against the extracted
  sources, and a deterministic renderer does all drawing.
---

# ga-spec-compiler

The model never draws. It reads the actual materials, fills **one** JSON
spec (`figure_spec.json`) where every factual element carries a verbatim
source quote, and two programs do the rest: `check_spec.py` (blocking gate)
and `render_spec.py` (deterministic matplotlib compiler). This kills the
three classic graphical-abstract failures: entities/numbers that cannot be
traced to the source, irreproducible layouts, and undeliverable bitmaps
without an editable source.

## Runtime contract (DeepSeek Harness)

- Skill installed at `/skills/weekly-skill`. Inputs: `/input/case.json`,
  `/input/task.md`, plus the case's materials (PDF via pdf-text-tool
  `pdftotext`, data files as-is). **Read the actual files; never assume
  content from labels.** The PDF arrives without a pre-extracted answer layer.
- Work under `/app/work`; deliver under `/app/output`:
  `graphical_abstract.svg` (editable, layered, real `<text>`),
  `graphical_abstract.png` (canvas dpi, default 300), `graphical_abstract.pdf`,
  `figure_spec.json` (the true source file), `check_report.json`,
  `render_report.json`, and `result.json` (original `case_id` + every field
  named by the case's `output_contract`, honest `status`, `sources`,
  `uncertainty`, `change_record`).
- Budgets: 64 model requests, 900 s, 16384 tokens per response. **Run
  `make_result.py` immediately after reading case.json** so a valid partial
  result exists, then update it at each milestone.
- Never fabricate numbers, entities, or quotes. If a value cannot be found
  verbatim in the sources, it does not go in the figure — or it goes in as an
  explicitly dispositioned exception (see gate S3).

## Protocol (5 steps, 2 are machine gates)

```
0  result scaffold .... make_result.py          (30 s, protects the run)
1  extract sources .... extract_materials.py    (machine)
2  author spec ........ figure_spec.json        (you — the only creative file)
3  GATE ............... check_spec.py           (machine, must PASS)
4  compile + export ... render_spec.py          (machine, deterministic)
```

### Step 0 — scaffold the result (first thing)

```bash
python3 /skills/weekly-skill/scripts/make_result.py \
    --case /input/case.json --outdir /app/output --status partial \
    --note "run started"
```

### Step 1 — extract the source pool (always first, one command)

```bash
python3 /skills/weekly-skill/scripts/extract_materials.py \
    --input /input --outdir /app/work
```

Produces `source_pool.txt` (your **only** quotable source of truth),
`sources_index.json` (per-file sha256 + extraction tool — cite these in
`result.json.sources`), `data_files.json` (structural preview of CSV/JSON).
If a PDF is marked `unextracted`, run the ocr-tool, append its transcript to
`source_pool.txt` in the same `===== SOURCE: ... =====` block format, and
record this in `uncertainty`. For figure03-style biological sources, open the
rendered PDF pages (pdf-render-tool, 150 dpi) to confirm which figure is a
schematic vs. measured data before you encode either.

### Step 2 — author `/app/work/figure_spec.json`

Full grammar: `references/spec_format.md`. Anchoring rules:
`references/source_anchoring.md`. The essentials:

- `canvas`: `width_in`/`height_in` (7.2 × 4.0 is a safe single-column GA),
  `dpi` 300.
- `panels[]`: `kind: "schematic"` (nodes/edges in panel-fraction coordinates
  `xywh_frac`, top-left origin) or `kind: "bar"|"line"|"scatter"` (data from
  the actual source data file via `source.data_ref.file`).
- Every node / labelled edge / series / annotation that states a fact MUST
  carry `source: {locator, quote}` where `quote` is a **verbatim copy** from
  `source_pool.txt` (fix line wraps only; never retype, never "round"
  numbers). Edge labels stating a mechanism ("activates", "inhibits") need a
  quote containing that relation.
- Numbers in any label/title/series must appear in that element's own quote
  or its `data_ref` file. The gate checks this mechanically.
- Entity roles drive the visual encoding (`entity`, `process`, `outcome`,
  `condition`, `intervention`, `note`) — do not invent per-node colours
  unless the source encodes them.
- Reading order = panel order in `reading_order` (problem → method → result
  → conclusion across the canvas).

### Step 3 — blocking gate

```bash
python3 /skills/weekly-skill/scripts/check_spec.py \
    --spec /app/work/figure_spec.json --pool /app/work/source_pool.txt \
    --datadir /input | tee /app/work/check_report.json
```

Exit 0 required. Findings: fix the spec and re-run. A finding may be
dispositioned only by adding `{"id", "finding", "reason"}` to the spec's
`exceptions` list with the exact issue text — e.g. a qualitative arrow whose
relation is obvious from a diagram you inspected on a rendered page; say so.
Silent omission is not a disposition.

### Step 4 — compile and export

```bash
python3 /skills/weekly-skill/scripts/render_spec.py \
    --spec /app/work/figure_spec.json --outdir /app/output
python3 /skills/weekly-skill/scripts/make_result.py \
    --case /input/case.json --outdir /app/output --status complete --gate pass \
    --note "spec compiled, exports written"
```

The SVG keeps text as text (`svg.fonttype: none`) with one named group per
spec element (`node_<id>`, `edge_<a>_<b>`, `panel_<id>`) — it is the editable
source together with the spec. Open the PNG and check it once as a human
would: labels legible, no overflow, arrow directions match the causal story.

## Failure handling

| Situation | Action |
|---|---|
| PDF yields no text | ocr-tool → append transcript to pool → note in `uncertainty` |
| A required number is not in the sources | remove it or add a dispositioned exception; never invent |
| Gate keeps failing on overflow | shorten label, enlarge box, or raise `font_pt` ≤ 1 pt; do not shrink below 7 pt |
| Material has images only (figure03 case) | describe only what you verified on the rendered page; mark the panel `note` role and exception it |
| 600 s elapsed, spec not passing | render nothing; finalize `result.json` with `status: partial`, gate findings attached |
| Two valid layouts possible | pick the one matching `reading_order`; record the alternative in `change_record` |

## Self-check before finalizing

1. `check_spec.py` exit 0 on the exact spec that was rendered.
2. `graphical_abstract.svg/.png/.pdf` all present; PNG opens at 300 dpi.
3. Every `sources[]` entry in `result.json` has file + sha256 from
   `sources_index.json`.
4. `exceptions` non-empty ⇒ each has a human-readable reason.
5. Re-running `render_spec.py` on the same spec reproduces the same layout
   (deterministic by construction; PDF metadata date varies, see
   `render_report.json`).

## Scope and limits

Chart panels support bar/line/scatter with optional symmetric `yerr`;
schematics support rounded boxes and four edge styles. It is not a
molecule/structure drawer — represent molecules as labelled entities unless
the case ships an image asset, which you may reference (not embed as text).
See `examples/minimal_example.md` for one complete, runnable input/output
pair (marked as an example, not a formal case result).
