---
name: panel-linked-figure-reading
description: 多子图结构关联与图注对齐，先建“连线图”再读数：子图切分、caption 逐面板解析、question→panel/table/text 链接矩阵与缺口台账。Triggers: 多子图, 子图关联, 图注解析, multi-panel figure, caption alignment, subfigure linking, gap ledger.
---

# Panel-linked figure reading (多子图结构关联)

**Core idea.** In multi-panel figures the dominant error is not misreading a value but
**mis-wiring** — answering with panel (c)'s data for a question about panel (b), pairing a
caption clause with the wrong panel, or silently dropping a panel. This skill builds the
wiring diagram **before** any value is read: it segments the figure into panels, parses the
caption into per-panel clauses, aligns the two, and maintains a machine-checked **link
matrix** from every question/claim to the exact panels, tables and text spans that support
it — plus a **gap ledger** for figures whose pixels were never shipped. Value reading
itself is the agent's job; this skill guarantees nothing is cross-wired or dropped.

## Runtime contract

Read `/input/case.json` and `/input/task.md` first; the case's `output_contract` defines the exact result fields (any shape — dict, list, or mixed). Work in `/app/work`; final artifacts belong in `/app/output`, including `result.json` carrying the original `case_id` and every output_contract field. Budget is tight (~900 s, 64 model calls): write a valid **partial** result.json early; improve it in place and keep `status` honest (`success` only when every contract field is filled and every claim is locatable; otherwise `partial` with explicit limits). The case ships ONE original figure image plus all original tables; any figure mentioned in text or captions whose pixels are not provided is a declared gap — list it, never reconstruct it. If paths differ outside the harness, pass the real paths with the CLI flags.

## Dependencies

- python3 stdlib + numpy 2.x + PIL 12.x (required; matplotlib only used by the synthetic
  example generator, not by the pipeline).
- Optional: poppler `pdftotext` for pulling caption text blocks out of a shipped PDF.
  If `pdftotext` is absent, caption extraction from PDFs is skipped and the
  `caption_source` is flagged `degraded` (caption can still come from `--caption` or
  `case.json`).
- No network, no pip.

## Workflow

Run from anywhere; scripts write small JSON artifacts into `--work` (use `/app/work`).

0. **Early partial result.** Read `/input/case.json` + `/input/task.md`; immediately write
   a valid partial `/app/output/result.json` with the original `case_id`, every
   `output_contract` field stubbed, `status: "partial"`, empty `sources`/`gaps`. Improve
   it in place afterwards.
1. **Segment panels.**
   `python3 /skills/weekly-skill/scripts/split_panels.py --image /input/<figure>.png --work /app/work --out /app/work/panels`
   → `panel_map.json` (panel ids in reading order, label guesses, bboxes, crops).
2. **Parse caption.**
   `python3 /skills/weekly-skill/scripts/caption_parse.py --case /input/case.json --task /input/task.md --input-dir /input --work /app/work`
   → `caption_map.json` (ordered panel refs, per-panel verbatim clauses, unassigned
   clauses, figures referenced but shipped without pixels).
3. **Init link matrix.**
   `python3 /skills/weekly-skill/scripts/link_matrix.py --panels /app/work/panel_map.json --captions /app/work/caption_map.json --task /input/task.md --work /app/work`
   → `link_matrix.json` with one unfilled row per task question/claim.
4. **Answer — wired only.** Answer each task question **only** from the panels, tables and
   text spans its matrix row names; record evidence cells with locators: panel id + bbox,
   table file + row/col, text span (char offsets). Merge assignments with
   `python3 /skills/weekly-skill/scripts/link_matrix.py --panels ... --captions ... --task ... --work /app/work --fill /app/work/fill_fragment.json`
5. **Check the wiring.**
   `python3 /skills/weekly-skill/scripts/link_matrix.py --panels ... --captions ... --task ... --work /app/work --check`
   → `link_check.json` coverage warnings: unused caption clause, unreferenced pixel panel,
   claim citing a panel whose content type mismatches, cross-panel comparative claim
   citing <2 panels, unfilled rows. Exit 2 = warnings, 0 = clean, 1 = fatal.
6. **Report gaps.** Merge `gap_ledger.json` (figures mentioned but never shipped) into
   `result.json` `gaps`/`uncertainty`; never reconstruct their content. Set final
   `status` honestly.

## Failure catalogue

| Failure | Handling |
|---|---|
| Caption missing | Link against `task.md` only; `caption_map.json` has empty clauses and a warning; matrix rows must cite panels/tables/text spans from the task text. |
| Panel labels absent in pixels | Positional ids `p1..pn` assigned row-major, `labels_detected: false`, warning in `panel_map.json`; use positional ids everywhere. |
| Irregular collage layouts | Auto-gutter splitting under/over-segments; write a manual override file `panel_override.json` (`{"panels":[{"id":"p1","bbox":[x0,y0,x1,y1]},...]}`) in `--work` and rerun `split_panels.py` — it is honored first. |
| Caption letters don't match pixels (e.g. caption has (e), pixels have 4 panels) | Conflict is recorded as a `caption_pixel_mismatch` warning and an `uncertainty` entry; do not guess-merge clauses onto panels. |
| Figures mentioned but pixels not shipped (v2 rule) | Declared gap: entry in `gap_ledger.json` with the mention evidence; surface in `result.json` gaps; **never reconstruct**. |

## Limits

- **No value digitization.** The skill never reads numbers off axes, bars, or spectra; the
  agent does that, from the panels the matrix names.
- **Alignment is structural, not semantic.** The matrix proves coverage and wiring, not
  that an answer is correct.
- Honesty rules: `status: "success"` only when every contract field is filled and every
  claim is locatable; otherwise `partial` with explicit limits. Gaps are listed, never
  reconstructed. If a link cannot be established, say so in `uncertainty` instead of
  silently citing a likely-looking panel.
