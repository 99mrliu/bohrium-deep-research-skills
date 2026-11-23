---
name: semantic-adjudicator
description: >-
  Mid-stream semantic adjudication skill for paper field extraction under
  the concrete-reading-v2 contract. A light text index is built once; the
  core is the per-field decision procedure: candidate sentences are ranked,
  then accepted or rejected by semantic rules (subject, condition,
  comparator, statistic, unit must match the requested field), and every
  field receives one of reported / not_reported / source_conflict /
  extraction_failed by an explicit decision tree — a guessed value is
  rejected by the tooling itself (scalar must be verbatim inside its quote,
  condition is mandatory for measured values, comparator is mandatory for
  comparative claims). Use when /input provides case.json,
  target-fields.json and a paper PDF and /app/output/result.json must carry
  one auditable record per field_id. 中游语义裁决：每个字段按决策树定状态，
  条件与数值同源绑定，机器拦截裸数值与凭空猜测。
---

# Semantic Adjudicator — 逐字段语义裁决，条件与数值同源绑定

**Core bet.** Extraction fails in the middle: a number is copied from the
wrong subject, from the wrong condition, without its comparator, or a
missing field is silently filled with a plausible value. This skill makes
the **decision procedure** the product: the tooling refuses a reported
value that is not verbatim inside its own quote, refuses a measured value
without its condition, and refuses a comparative claim without its
comparator. `not_reported` is a first-class, auditable outcome.

## When to use

- `/input/case.json` + `/input/target-fields.json` (or fields in task.md) +
  paper PDF(s) under `/input/`; deliver `/app/output/result.json` echoing
  `case_id` with `status`, `result`, `claims`, `uncertainties` and one
  record per requested `field_id`.

## Workflow (paths relative to this SKILL.md)

**0. Orient (1 request).** `ls /input/`; read `case.json` (note `case_id`
and `output_contract` keys), `target-fields.json` (list every `field_id`),
`task.md`. Identify main vs supplementary PDFs.

**1. Index the text (0 requests).**

```bash
python3 scripts/extract.py --pdf /input/<paper>.pdf --work-dir /app/work \
    [--si /input/<si>.pdf] [--text-file /app/work/ocr.txt]
```

Writes `pages.txt` (`[PAGE n]` markers), `sentences.tsv` (line-numbered
sentences with page numbers) for grep-based candidate search. Exit 3 →
scanned PDF: use the environment OCR/pdf-text tool in
`environment/resources.yaml`, save text, rerun with `--text-file`. Exit 4 →
no extractor: same fallback.

**2. Draft the skeleton (0 requests).**

```bash
python3 scripts/adjudicate.py draft --input-dir /input \
    --output /app/output/result.json
```

Every field starts `not_reported`; overall `status` starts `partial`. This
file is a **valid honest partial** from now on — save early, improve in
place. Evidence can only upgrade a field.

**3. Adjudicate every field (your budget goes here).** Per `field_id`:

1. Find candidates: `grep -in "keyword\|synonym\|unit" /app/work/sentences.tsv`
   (search synonyms and unit strings, English and Chinese).
2. Read the candidate's sentence **and its neighbors** in `pages.txt`.
3. Apply the accept test (full rules in `references/decision-rules.md`):
   the sentence is about the requested subject; the value's condition
   (sample, setting, time point) matches the field; unit and statistic are
   as printed; comparative claims name their comparator.
4. Record the decision — the tool enforces the schema
   (`references/field-schema.md`):

```bash
python3 scripts/adjudicate.py set --output /app/output/result.json \
    --field capacity_composite_100cyc --status reported \
    --scalar "152" --units "mAh g⁻¹" \
    --condition "100 cycles, 0.5 C, 25 °C" --comparator "" \
    --quote "After 100 cycles ... 152 mAh g⁻¹." --page 1 --paragraph-id p001.002 \
    --notes "confirmed against abstract; table row agrees"

python3 scripts/adjudicate.py set --output /app/output/result.json \
    --field retention_composite_500cyc --status not_reported \
    --notes "table cell states 'n.d.'; searched: retention, 500 cycles, 保持率"
```

`set` **rejects** (exit 1, file untouched): scalar not verbatim inside
`--quote`; `reported` without condition for a numeric scalar; comparative
quote without `--comparator`; `not_reported` without searched-terms notes;
`extraction_failed` without a location. Ranges and inequalities
(`92–95 %`, `> 90 %`, `p < 0.05`) go into `scalar` verbatim — never
averaged, never stripped.

**4. Claims.** Add the paper's central conclusions via
`adjudicate.py claim --kind conclusion|limitation|speculation --text ...
--quote ... --page N`. Hedge language (`may`, `suggests`, `可能`, `提示`)
is `speculation` and must keep its hedge words in `text` — never promoted
to fact.

**5. Final check (0 requests).**

```bash
python3 scripts/adjudicate.py check --output /app/output/result.json
```

Verifies: `case_id` echoed, all `output_contract` keys present, every
requested `field_id` decided exactly once, every non-reported field
mirrored in `uncertainties`, claim kinds valid, overall `status` consistent
(`answered` only when all fields reported; `input_error` only for unusable
input). Fix every ERROR; WARNs need a reason in `notes`.

## Decision tree (summary; full version in references/decision-rules.md)

```
candidate sentence found?
├─ no, after synonym+unit+中文 grep → not_reported (notes: searched terms)
├─ yes, but location unreadable (garbled cell / scanned) → extraction_failed (notes: location + manual check)
└─ yes, readable:
   ├─ subject/condition/unit/statistic all match → reported
   ├─ two readings, same quantity+condition, irreconcilable → source_conflict (quote both)
   └─ readings differ by condition → reported with the matching one; others in notes
```

## Budget discipline

Steps 1–2 cost nothing. Allocate ~70% of the 64-request budget to step 3
(hardest fields first: cross-page tables, ranges, `n.d.`, conflicts),
reserve ≥3 requests for claims and the final check. The skeleton from step
2 means any interruption still leaves a complete, honest result.json.
