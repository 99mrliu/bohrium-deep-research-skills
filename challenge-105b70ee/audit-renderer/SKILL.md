---
name: audit-renderer
description: >-
  Downstream verification-and-rendering skill for paper field extraction.
  After fields are bound, a provenance join-check proves every reported
  value is a verbatim substring of its own quote, every quote is verbatim
  in the paper's text layer on the stated page, and every bank_id resolves;
  then an audit pack is rendered (HTML report with highlighted evidence
  cards, coverage matrix, claims by kind, uncertainty table, optional page
  PNG previews) so a second person can independently re-check every field
  without re-reading the paper. Use when /input provides case.json,
  target-fields.json and a paper PDF and /app/output/result.json must be
  provably traceable (concrete-reading-v2). 下游核验渲染：溯源连接机检 +
  审计报告渲染，每个字段可被第三人独立复核。
---

# Audit Renderer — 先证明每条字段可溯源，再把证据渲染成审计包

**Core bet.** A result.json nobody can re-check is worth little. This
skill's product is the **verification and its rendered proof**: a machine
join-check that fails loudly on fabricated or mis-attached evidence, and
an HTML audit pack in which every field shows its quote with the value
highlighted, its page, and its status — checkable by a second person in
minutes, without opening the paper.

## When to use

- `/input/case.json` + `/input/target-fields.json` + paper PDF(s);
  `/app/output/result.json` must echo `case_id` and carry `status`,
  `result.field_results` (one per `field_id`), `claims`, `uncertainties`.
- The rendering step needs the same PDFs; page previews use `pdftoppm`
  when present and are skipped otherwise (the HTML still renders).

## Workflow (paths relative to this SKILL.md)

**0. Orient (1 request).** Read `/input/case.json` (`case_id`,
`output_contract`), `/input/target-fields.json`, `task.md`; identify main
and supplementary PDFs.

**1. Build the text layer + evidence bank (0 requests).**

```bash
python3 scripts/build_bank.py --pdf /input/<paper>.pdf --work-dir /app/work \
    [--si /input/<si>.pdf] [--text-file /app/work/ocr.txt]
```

Writes `layer.jsonl` (page-tagged verbatim sentences), `bank.jsonl`
(quantified/cued sentences with stable `bank_id`), `layer_stats.json`.
Exit 3/4 → scanned PDF or no extractor: use the environment OCR/pdf-text
tool (`environment/resources.yaml`), save text, rerun with `--text-file`.

**2. Bind fields (your semantic work).** Search `bank.jsonl` / grep
`layer.jsonl`; for each `field_id` write its record into
`/app/output/result.json` (schema below): status
`reported|not_reported|source_conflict|extraction_failed`, and for
reported values `scalar`, `units`, `statistic`, `condition`, `comparator`,
verbatim `quote`, `page`, `bank_id` of the bank entry the quote came from.
Start from a skeleton with all fields `not_reported` so the file is always
a valid honest partial. Rules: scalar verbatim inside quote; quote copied
from the bank/layer, never retyped; absent fields are `not_reported` with
searched terms, never zero.

**3. Prove provenance (0 requests).**

```bash
python3 scripts/verify.py --result /app/output/result.json --work-dir /app/work
```

Join-checks, each printed as PASS/ERROR: scalar ⊆ quote (verbatim); quote ⊆
text layer **on the stated page** (whitespace-normalized); `bank_id`
exists and its stored quote equals the field's quote; claims evidence
verbatim + located; every requested field decided; non-reported fields
mirrored in `uncertainties`. **Fix every ERROR before finishing** — an
ERROR means evidence a second person could not find. Writes
`/app/work/verify_report.json`.

**4. Render the audit pack (0 requests).**

```bash
python3 scripts/render_audit.py --result /app/output/result.json \
    --work-dir /app/work --out /app/output/audit_report.html \
    [--pdf /input/<paper>.pdf --pages-dir /app/output/pages]
```

Renders `audit_report.html`: header (case_id, status, verifier verdict),
coverage matrix (field × status), one evidence card per field (quote with
the scalar highlighted, page, bank_id, condition/comparator), claims
grouped by kind, uncertainty table. With `--pdf` and `pdftoppm` available,
referenced pages are rendered to `pages/page-N.png` for visual spot-check
(runtime artifacts; absence never blocks the HTML).

**5. Finalize (1 request).** Overall `status`: `answered` only when every
field is `reported` and verify is clean; otherwise `partial` /
`insufficient_evidence` / `input_error` with reasons in `uncertainties`.
Re-run `verify.py` after any edit. Deliverables in `/app/output/`:
`result.json`, `audit_report.html`, `pages/` previews (if rendered).

## Failure handling

| Symptom | Action |
|-|-|
| verify ERROR: quote not in layer | re-copy the quote from `bank.jsonl` (never retype); if the sentence only exists garbled → `extraction_failed` |
| verify ERROR: bank_id mismatch | the quote moved; update both from the same bank entry |
| Scanned PDF | OCR fallback (step 1); mark OCR-sourced fields in `uncertainties` |
| Long paper, many tables | the layer is page-tagged; grep by unit strings and table captions first |

See `references/audit-format.md` for the result schema, the join-check
definitions, and the audit-report anatomy.
