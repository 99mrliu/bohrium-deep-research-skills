# Audit format — result schema, join-checks, report anatomy

## result.json schema (what verify.py and render_audit.py expect)

Top level: `case_id` (echoed verbatim), `status`
(`answered|partial|insufficient_evidence|input_error`), `result`,
`claims`, `uncertainties`.

`result.field_results[]` — one record per requested `field_id`:

| key | rule |
|-|-|
| `field_id` | verbatim from target-fields.json |
| `status` | `reported` / `not_reported` / `source_conflict` / `extraction_failed` |
| `scalar` | value as printed (ranges `92–95`, inequalities `> 90` kept) |
| `units` | as printed, never converted |
| `statistic` | printed error / significance, else null |
| `condition` | sample + setting + time point; mandatory for numeric values |
| `comparator` | object of comparison for comparative claims |
| `quote` | verbatim sentence/table line containing the scalar |
| `page` | 1-based page of the quote |
| `bank_id` | bank entry the quote was copied from (enables J4) |
| `notes` | adjudication trail / searched terms / takeover hints |

`claims[]`: `kind` (`conclusion|limitation|speculation`), `text`,
`evidence` = `{quote, page, paragraph_id}`, `source_id`, `location`.
Hedged statements stay `speculation` and keep their hedge words.

## Join-checks (verify.py)

| id | statement | typical failure cause |
|-|-|-|
| J1 | scalar ⊆ quote (verbatim substring) | value retyped or rounded |
| J2 | quote ⊆ text layer (whitespace-normalized) | quote paraphrased from memory |
| J3 | quote found on the stated page | page drift after edits |
| J4 | bank_id resolves and stored quote equals field quote | quote and id attached from different sentences |
| J5 | non-reported fields carry notes/location; conflicts list readings; uncertainties mirror | silent gaps |

Any FAIL means a second person cannot find the evidence: fix the record
(re-copy from `bank.jsonl`) or downgrade the status honestly
(`extraction_failed` with location), never delete the check.

## Audit report anatomy (audit_report.html)

1. **Header**: case_id, overall status, verification verdict, check count.
2. **Coverage matrix**: one row per requested field — a reviewer sees
   completeness in one glance.
3. **Evidence cards**: per field, the quote with the scalar highlighted,
   plus value/condition/comparator/location/notes. This is the
   re-checking unit: read the card, glance at the page preview, agree or
   object.
4. **Claims**: grouped by kind; hedge discipline visible.
5. **Uncertainties**: every not_reported / conflict / failed item with its
   reason — nothing disappears silently.
6. **Verification join-checks**: the raw J1–J5 table.
7. **Page previews**: rendered page PNGs (when pdftoppm is available) for
   visual confirmation against the original layout.

The report is self-contained HTML (no external assets) so it can be
attached to a review or archived with the result.
