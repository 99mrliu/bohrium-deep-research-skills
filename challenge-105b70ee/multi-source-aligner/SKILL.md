---
name: multi-source-aligner
description: >-
  Multi-source alignment skill for paper field extraction. Main text,
  tables, figure captions and supplementary information are treated as
  different channels of ONE field table: a source scanner segments every
  input PDF into per-source, region-tagged records (body / table /
  caption), then an aligner gathers, per requested field_id, the readings
  from all sources, groups them by value, and classifies each field as
  corroborated (>=2 sources agree), single_source, conflict (same
  quantity+condition, divergent values) or none — with explicit source
  priority and merge rules, so cross-source agreement strengthens a field
  and main-vs-SI divergence surfaces as source_conflict instead of being
  silently averaged. Use when /input provides case.json,
  target-fields.json and one or more PDFs (main + SI) and
  /app/output/result.json must carry per-source evidence
  (concrete-reading-v2). 多来源对齐：正文/表格/图注/SI 同源合并，分歧显形。
---

# Multi-Source Aligner — 正文、表格、图注、补充材料是同一张字段表的不同来源

**Core bet.** Field errors hide between sources: the text says 93%, the
table says 92–95, the SI says 90.8 — and a single-pass reader averages,
picks randomly, or never sees the disagreement. This skill makes
**alignment** the product: every field collects its readings from all
sources, agreement across sources strengthens it, divergence becomes an
explicit `source_conflict` with every reading quoted — never silently
merged.

## When to use

- `/input/case.json` + `/input/target-fields.json` + one or more PDFs
  (main paper; supplementary identified by name: supp/si/mmc/extdata);
  `/app/output/result.json` echoes `case_id` with `status`,
  `result.field_results` (one per `field_id`, each with a `readings`
  list), `claims`, `uncertainties`.

## Workflow (paths relative to this SKILL.md)

**0. Orient (1 request).** Read `/input/case.json` (`case_id`,
`output_contract`), `target-fields.json`, list the PDFs.

**1. Scan sources (0 requests).**

```bash
python3 scripts/source_scan.py --input-dir /input --work-dir /app/work \
    [--text-file-main F] [--text-file-si F]
```

Classifies each PDF as `MAIN` or `SI<n>`, extracts text, and segments it
into region-tagged records: `body` sentences, `table` lines (with their
caption), `caption` lines. Output: `work/sources.jsonl` + per-source stats.
Exit 3/4 (no text layer / no extractor) → OCR via the environment tool in
`environment/resources.yaml`, then `--text-file-main/--text-file-si`.

**2. Align fields across sources (0 requests).**

```bash
python3 scripts/align.py propose --work-dir /app/work \
    --input-dir /input --output /app/output/result.json
```

For each `field_id`: keyword+unit matching gathers candidate readings from
**all** sources and regions; readings are grouped by normalized value;
the field is classified `corroborated | single_source | conflict | none`
and a draft result.json is written with the full `readings` list per
field (source, region, page, verbatim quote, parsed value) and a
**proposed** status. The draft is a valid honest partial from this moment.

**3. Adjudicate each field (your budget).** For every field, read its
`readings` list (not the whole paper) and apply the merge rules in
`references/alignment-rules.md`:

- **corroborated** → `reported`; keep all readings in `readings` (the
  cross-source agreement is itself evidence), cite the
  highest-priority source's quote in `quote` (priority: main-table >
  main-body > caption > SI).
- **single_source** → `reported` only after the normal accept test
  (subject/condition/unit/statistic); note `single source` in `notes`.
- **conflict** → check conditions first: readings from different
  conditions are NOT a conflict — pick the condition-matching one,
  `reported`, list the others in `notes`. Same quantity+condition,
  irreconcilable values → `source_conflict`, all readings kept.
- **none** → targeted synonym/单位/中文 grep across `sources.jsonl`;
  still nothing → `not_reported` with searched terms; `n.d.` cell →
  `not_reported` quoting the cell; location known but unreadable →
  `extraction_failed` with location.

Edit result.json directly (schema in references), keeping every field's
`readings` intact — deleting readings is falsifying the alignment.

**4. Claims.** Conclusions/limitations/speculations with `kind`, verbatim
`evidence.quote`, `source_id` (MAIN/SI1/…), `location`. When a claim and a
field cite different sources, say so.

**5. Check + finalize (0 requests).**

```bash
python3 scripts/align.py check --output /app/output/result.json \
    --work-dir /app/work
```

Verifies: `case_id` echoed, all contract keys, every field decided once,
scalar verbatim inside its quote, quote verbatim in the cited source's
scan records, reported fields keep ≥1 reading, conflicts keep ≥2 readings
with divergent values, uncertainties mirror non-reported fields. Fix all
ERRORs. Set overall `status` (`answered` only if all fields `reported`).

## Budget discipline

Steps 1–2 are free; the readings lists make step 3 a per-field review
instead of a paper-wide search. Hardest first: conflicts and
table-region readings. Reserve ≥3 requests for steps 4–5.
