---
name: ga-audit-loop
description: >-
  Evidence-ledger and repair-loop QA for graphical abstracts and figure
  edits. Trigger when a graphical-abstract / 图形摘要 / figure task demands
  that every element be checkable against the source materials, when an
  existing provided figure must be EDITED (source-preserving patch, not a
  redraw), or when a draft figure needs an independent defect inspection
  before delivery: mines a citable evidence pool with stable block keys,
  verifies a per-element source ledger (verbatim quotes + number tracing),
  scans any SVG for a defect taxonomy, applies minimal byte-preserving
  patches with a diff record, and rasterises/diffs exports to prove an edit
  touched only what it should.
---

# ga-audit-loop

An audit-first approach. This skill does not tell you how to draw — it makes
any drawing **accountable**. Three blocking instruments:

1. **Source ledger** — every figure element has an entry whose evidence is a
   verbatim quote from a stable pool block (`file#page-N` / `file#para-N`);
   every displayed number must occur in its own evidence. `ledger_verify.py`
   blocks delivery otherwise.
2. **Defect scan** — `svg_inspect.py` checks ANY SVG (yours, a provided
   starting figure, a converted trace) against a named defect taxonomy
   (overflow, font floor, layering, viewBox, raster embeds, clipped text).
3. **Source-preserving edit** — when the workorder is "edit this figure",
   `apply_patch.py` performs exact, minimal operations on the original SVG
   text (fail unless the target occurs exactly once) and emits a unified
   diff as the change record; `render_diff.py` pixel-diffs before/after to
   bound the edit's blast radius.

## Runtime contract (DeepSeek Harness)

- Skill at `/skills/weekly-skill`. Inputs: `/input/case.json`,
  `/input/task.md`, materials per case. **Read the actual files; the PDF has
  no pre-extracted answer layer.** Tools per `environment/resources.yaml`
  (pdftotext, pdftoppm, ocr, soffice, scientific-python).
- Deliver under `/app/output`: the editable SVG, rendered PNG/PDF previews
  when an exporter exists, `result.json` with original `case_id` and all
  `output_contract` fields, plus `source_ledger.json`,
  `inspection.json`, `change_record.json` as applicable.
- Budgets: 64 model requests, 900 s, 16384 tokens per response. **Write a
  partial `result.json` with `finalize_result.py` right after mining.**
- Honest status: a figure whose ledger has blockers is `partial` with the
  findings attached, not `complete`.

## Protocol

```
0  mine pool ........ mine_sources.py        (machine; keys + number index)
1  result scaffold .. finalize_result.py --phase mined
2  draw / receive ... (your choice) or the provided starting figure
3  LEDGER GATE ...... ledger_verify.py       (machine; must PASS)
4  DEFECT SCAN ...... svg_inspect.py         (machine; repair loop)
5a export ........... render_diff.py --svg --png
5b edit mode ........ apply_patch.py + render_diff.py --before --after
6  finalize ......... finalize_result.py --phase complete
```

### Step 0 — mine the evidence pool

```bash
python3 /skills/weekly-skill/scripts/mine_sources.py \
    --materials /input --work /app/work
```

`evidence_pool.jsonl` gives every block a stable key (`paper.pdf#page-3`);
`number_index.json` answers "where does 42% live?" instantly. Files that
cannot be mined are listed in `pool_report.json.unminable` — OCR them or
declare the limit, never pretend.

### Step 3 — write and verify the ledger

Format: `references/ledger_format.md`. One entry per figure element
(entity, relation, value, label). Verify:

```bash
python3 /skills/weekly-skill/scripts/ledger_verify.py \
    --ledger /app/work/source_ledger.json \
    --pool /app/work/evidence_pool.jsonl --svg /app/output/graphical_abstract.svg
```

With `--svg` it also checks both directions of coverage: ledger ids exist in
the figure, and figure text is covered by ledger entries. Fix blockers; a
warning (e.g. id mismatch) must be explained in `exceptions` if left open.

### Step 4 — defect scan and repair loop

```bash
python3 /skills/weekly-skill/scripts/svg_inspect.py \
    --svg /app/output/graphical_abstract.svg --out /app/work/inspection.json
```

Defect codes and repair moves: `references/defect_taxonomy.md`. Loop until
CLEAN or every remaining defect is dispositioned in `result.json.exceptions`
with a reason.

### Step 5b — edit mode (when the case provides a starting figure)

Do not redraw. Write `/app/work/patch.json` with minimal operations
(`replace_text` must match exactly once; `replace_attr` targets one element
id; see `apply_patch.py --help`), then:

```bash
python3 /skills/weekly-skill/scripts/apply_patch.py \
    --svg /input/<starting-figure>.svg --patch /app/work/patch.json \
    --out /app/output/graphical_abstract.svg \
    --record /app/work/change_record.json
# rasterise both versions (any exporter) then bound the edit:
python3 /skills/weekly-skill/scripts/render_diff.py \
    --before /app/work/before.png --after /app/work/after.png --tolerance 0.05
```

`apply_patch.py` aborts (exit 1) if any operation's target is ambiguous —
rewrite the operation more specifically; never force it. The diff record and
the pixel-diff bbox are your proof that the edit is source-preserving.

## Failure handling

| Situation | Action |
|---|---|
| Number visible in figure absent from pool | find it in `number_index.json` → fix quote, or remove the number |
| Quote close but not verbatim (unicode minus, µ) | copy the exact characters from the pool block; do not "fix" the source |
| PDF unminable (scanned) | ocr-tool → append as new pool blocks → note tool in ledger locators |
| Starting figure has no ids / no layers | inspect it first; if patch ops cannot be made unambiguous, deliver an annotated redline PNG + exception instead of a destructive rewrite |
| Pixel-diff shows collateral change | revert, re-patch with a tighter operation; the change record must show only intended hunks |
| Time nearly up, ledger failing | finalize as `partial` with open findings — a failed gate is information, not something to hide |

## Self-check before finalizing

1. `ledger_verify.py` PASS (or every blocker written into `exceptions` with
   a reason and `status: partial`).
2. `svg_inspect.py` CLEAN on the delivered SVG.
3. Edit mode: `change_record.json` shows only intended hunks; pixel-diff
   `within_tolerance: true`.
4. PNG/PDF preview exists or its absence is recorded with the tool report.
5. `result.json`: case_id, gates, exceptions, uncertainty, change_record all
   honest.

## Scope and limits

The ledger verifies textual/numeric anchoring, not scientific taste (that
judgement stays with you and the reviewer). The pixel diff needs same-size
renders. OCR-dependent pools inherit OCR error rates — say so in
`uncertainty`. See `examples/minimal_example.md` for a runnable demo
(marked as example).
