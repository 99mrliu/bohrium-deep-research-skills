---
name: faithful-textlayer
description: >-
  Upstream data-authenticity skill for paper field extraction. Before any
  field is answered, build and audit a faithful, page/paragraph-anchored text
  layer from the paper PDF: ligature and spacing repair, hyphenation joins,
  column/table scrambling detection, scanned-page detection, per-page
  integrity metrics. Fields are then bound only to verified text-layer
  sentences; unreadable locations become extraction_failed with a stated
  manual-check point, never a guess. Use when the task provides a paper PDF
  under /input plus /input/case.json and /input/target-fields.json and
  expects /app/output/result.json with verbatim, located evidence
  (concrete-reading-v2). 上游数据真实性：先建可信文本层再答字段，坏位置如实标记。
---

# Faithful Text Layer — 先建可信文本层，再谈字段抽取

**Core bet.** Most field-extraction errors are born upstream: interleaved
two-column lines, scrambled table cells, dropped ligatures ("fi" lost),
broken units ("mAh g −1" split), scanned pages read as empty. This skill
makes the **text layer itself an auditable artifact**. You answer fields
only from sentences that survived the integrity audit; positions that did
not survive are reported as `extraction_failed` with the exact location —
never guessed.

## When to use

- `/input/case.json` + `/input/target-fields.json` (or fields in task.md) +
  one or more paper PDFs under `/input/`; output `/app/output/result.json`
  must echo `case_id`, carry `status`, `result` (one record per requested
  `field_id`), `claims`, `uncertainties`.
- Not for: no PDF present, or no requested fields.

## Workflow (all paths relative to this SKILL.md)

**0. Orient (1 model request).**

```bash
ls -la /input/
cat /input/case.json; cat /input/target-fields.json 2>/dev/null; cat /input/task.md 2>/dev/null
```

Note `case_id`, the `output_contract` keys, and every requested `field_id`.
Identify the main PDF and supplementary PDFs (name contains
supp/si/mmc/extdata → SI).

**1. Inspect the PDF (0 requests).**

```bash
python3 scripts/pdfinspect.py --pdf /input/<paper>.pdf --out /app/work/inspect.json
```

Reads per-page text yield, flags low-text (probably scanned) pages and
column/table risk. If it exits 3 (no text layer at all) → use the
environment OCR/pdf-text tool listed in `environment/resources.yaml`, save
the text, and rerun step 2 with `--text-file`. If it exits 4 (no extractor
available) → same fallback.

**2. Build the anchored text layer (0 requests).**

```bash
python3 scripts/textlayer.py --pdf /input/<paper>.pdf --work-dir /app/work \
    [--text-file /app/work/ocr.txt] [--si /input/<si>.pdf]
```

Produces `/app/work/textlayer.jsonl` (one entry per paragraph: `pid` like
`p002.003`, `page`, verbatim `text`), `/app/work/fulltext.txt`, and
`/app/work/integrity.json` (per-page yield, normalization counts,
low-text pages, table-line count). **Read `integrity.json` first**: any
page flagged `low_text` or `table_risk` is evidence-fragile; fields whose
only candidate lives there must carry that fragility in `notes`, or become
`extraction_failed` when the location is unreadable.

**3. Harvest the evidence bank (0 requests).**

```bash
python3 scripts/harvest.py --work-dir /app/work
```

Writes `/app/work/evidence_bank.jsonl`: every quantified sentence
(number + unit/range/inequality/statistic) and every cued statement
(conclusion / limitation / hedge, EN+中文) with `bank_id`, `page`, `pid`,
verbatim `quote`, parsed numbers. `harvest_report.json` records what was
swept — zero-candidate pages are visible, so a later `not_reported` is an
auditable claim, not an omission.

**4. Bind fields to bank entries (your semantic work).** For each
`field_id`: search the bank (or `grep -n` `fulltext.txt`) for candidates;
accept only when subject, condition, comparator, unit and statistic all
match the request; copy the quote **verbatim** from the bank entry. Status
rules (details in `references/textlayer-rules.md`):

- `reported` — value confirmed against a bank quote; fill `condition`,
  `comparator`, `statistic` from the sentence context.
- `source_conflict` — two bank entries give irreconcilable readings for the
  same quantity+condition (different conditions are **not** a conflict:
  pick the matching one, note the other).
- `not_reported` — harvest + a targeted synonym grep both empty; record
  searched terms. Absent ≠ zero; `n.d.`/`not reported` cells →
  `not_reported` with that note.
- `extraction_failed` — the location exists but is unreadable
  (scanned page, garbled cell, flagged low-text/table-risk page): give the
  location and what a human should check.

**5. Write + self-check (1 request).** Assemble
`/app/output/result.json` with keys: `case_id` (verbatim), `status`
(`answered` only if every field is `reported`; else `partial`,
`insufficient_evidence`, or `input_error`), `result.field_results` (list,
one per `field_id`, each with `scalar`, `units`, `statistic`, `condition`,
`comparator`, `quote`, `page`, `paragraph_id`, `bank_id`, `status`,
`notes`), `claims` (paper's central conclusions; `kind` ∈
conclusion|limitation|speculation; hedge words never promoted to facts;
each with `evidence` quote + `source_id` + `location`), `uncertainties`
(every not_reported / conflict / failed item + text-layer fragility notes).
Attach `integrity.json` findings under `uncertainties` when they bear on a
field. Sanity: every `scalar` must appear verbatim inside its own `quote`;
every `bank_id` must exist in the bank.

## Budget discipline (64 requests / 900 s)

Steps 1–3 are free. Spend requests on step 4 adjudication (worst fields
first: conflicts, ranges, n.d., cross-page tables), keep ≥3 requests for
steps 5 and writing. Save a valid honest-partial result.json early (all
fields present, conservative statuses) and improve in place.

## Failure handling

| Symptom | Action |
|-|-|
| No text layer (exit 3) | OCR via environment tool, `--text-file`, mark affected pages fragile |
| No extractor at all (exit 4) | Same fallback; if impossible, status `input_error` with reason |
| Two-column interleave suspected | textlayer.py already splits columns by gutter; verify in `integrity.json` |
| Field only on a low-text page | `extraction_failed` + page + what to check manually |
| Scrambled table row | read raw page text in `fulltext.txt`; if cell unreadable → `extraction_failed` |

See `references/textlayer-rules.md` for the normalization table, integrity
metrics, unit-preservation rules and status mapping.
