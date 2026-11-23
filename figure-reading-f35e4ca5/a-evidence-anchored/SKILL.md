---
name: evidence-anchored-figure-reading
description: Read a scientific figure with upstream-data authenticity as the governing principle — the case's original tables, caption and text are the source of truth and figure pixels are a hypothesis to be verified against them. Mine tables into a queryable profile, gate the axis card (type/unit-prefix/calibration), anchor every series to candidate table columns, run the bidirectional figure↔table crosscheck, and deliver every number with a provenance record (source_type + locator + verbatim). Use when a task asks to extract, verify, or answer questions about values in a scientific figure (图表数值提取, 图表核验, figure verification, provenance-tagged reading) and fabricated or unverifiable numbers are unacceptable.
---

# Evidence-anchored figure reading

Core idea: **the figure is not the data.** In these cases the platform
ships the original figure *and all original tables*; the tables, caption
and text are the authentic numbers, and pixel readings are hypotheses.
This skill makes the agent build a provenance chain for every reported
number: mined tables → gated axis card → series anchors → bidirectional
crosscheck → provenance-tagged claims → result.json.

## Runtime contract

Read `/input/case.json` and `/input/task.md` first; the case's
`output_contract` defines the exact result fields (any shape — dict,
list, or mixed). Work in `/app/work`; final artifacts belong in
`/app/output`, including `result.json` carrying the original `case_id`
and every output_contract field. Budget is tight (~900 s, 64 model
calls): step 1 writes a valid **partial** result.json immediately; improve
it in place and keep `status` honest (`success` only when every contract
field is filled and every claim is locatable). If paths differ outside
the harness, pass the real paths with the CLI flags.

## Dependencies

Python 3, standard library only. Optional: `pdftotext` (poppler) for PDF
blocks — its absence is recorded in `inventory.degraded`, never fatal.
No network, no pip install.

## Workflow

1. **Mine the authentic sources (once).**
   `python /skills/weekly-skill/scripts/mine_case.py --case /input/case.json --task /input/task.md --input-dir /input --work /app/work --out /app/output`
   Produces `inventory.json` (file list, per-column table profiles with
   unit guesses, text blocks, number index with verbatim contexts) and the
   skeleton `result.json`.

2. **Answer from tables/text first.** Many questions (exact values,
   conditions, n, units, error-bar semantics) are answered *by quote* from
   layer 1–2 material (`references/source_priority.md`). Search
   `inventory.number_index` for the asked quantities; capture
   table_cell / caption_verbatim / text_sentence evidence immediately
   into `claims.json` (schema: `references/provenance_schema.md`).

3. **Build the axis card from the zoomed figure.** Crop/zoom the image
   (PIL, or `pdftoppm -png -r 300` if the figure ships inside a PDF).
   Write `/app/work/axis_spec.json`: per axis — verbatim label, verbatim
   unit, declared type, ≥3 ticks `{value, px}` (image coordinates), plot
   area box. Then extract readings into `figure_readings.json`
   (`{"series":[{"name":..., "points":[[x,y], ...]}]}`) by any sound
   method (manual zoom reading is legitimate; the gates check it).

4. **Gate the axis card.**
   `python /skills/weekly-skill/scripts/anchor_figure.py --axis /app/work/axis_spec.json --readings /app/work/figure_readings.json --inventory /app/work/inventory.json --work /app/work`
   Hard-fails the three classic misreads: axis-type vs tick geometry,
   unparseable/copied-wrong units, and ranges irreconcilable with every
   table column (the mV-as-V fingerprint). **Never extract values from a
   failing axis card — fix the card first.**

5. **Run the bidirectional crosscheck.**
   `python /skills/weekly-skill/scripts/crosscheck.py --readings /app/work/figure_readings.json --anchor /app/work/anchor_map.json --inventory /app/work/inventory.json --input-dir /input --work /app/work`
   `all_matched: false` means: a reading matches no table row, or an
   in-range table row has no reading (missed curve / swapped legend).
   Resolve each entry or carry it explicitly into `uncertainty`.

6. **Write claims with provenance.** For each reported number append a
   claim to `/app/work/claims.json` per `references/provenance_schema.md`
   (evidence source_type + locator + verbatim, crosscheck status).

7. **Deliver.**
   `python /skills/weekly-skill/scripts/make_result.py --case /input/case.json --fragment /app/work/result_fragment.json --claims /app/work/claims.json --out /app/output/result.json --status success`
   Also copy `inventory.json`, `anchor_map.json`,
   `crosscheck_matrix.json` into `/app/output` as the auditable evidence
   trail. `make_result.py` auto-downgrades `success` to `partial` if
   contract fields are null or claims lack locators.

## Failure catalogue

| Symptom | Diagnosis | Fix |
|-|-|-|
| anchor_figure hard-fail axis_type_gate | ticks copied from log axis declared linear (or reverse) | re-read tick labels digit by digit; geometry wins |
| candidate_columns empty for an axis | unit misread (prefix) or tables don't cover this panel | re-check unit characters; if genuinely unanchored, justify `no_anchor` in uncertainty |
| unexplained_table_rows non-empty | missed curve segment or legend swap | map each table column to a legend entry; re-read the legend colors/markers |
| unmatched reading cluster at one end | plot-area box off by a few px, or axis doesn't start at first tick | re-measure plot area; check calibration residuals |
| pdftotext absent | degraded layer-2 access | read PDF with the platform pdf tool; record in uncertainty |

## Limits

- Raster figures are read manually (zoomed); this skill verifies and
  documents readings, it does not trace curves pixel-wise.
- 3-D charts and images without numeric axes (micrographs) yield
  `no_anchor` claims only; state precision limits.
- Multi-panel figures: build one axis card **per panel**; never share a
  calibration across panels.

See `examples/minimal_example.md` for a complete runnable synthetic
miniature (illustrative, not an official case result).
