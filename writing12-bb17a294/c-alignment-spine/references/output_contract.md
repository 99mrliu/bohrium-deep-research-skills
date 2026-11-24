# Output Contract — Filling `/app/output/result.json`

The case's `output_contract` is read from `/input/case.json` at intake and
obeyed **literally**. Never assume its schema: different cases name fields
differently, require different artifacts, or demand extra metadata. Record
**every** field it lists, then fill each one honestly.

## Rules

1. **Read first, write second.** Before any translation work, copy the
   real `case_id`, the requested deliverables, the language direction
   (EN→ZH / ZH→EN / both), and the full `output_contract` object from
   `/input/case.json` into your working notes. Quote the contract; do not
   paraphrase it from memory.
2. **Early partial, atomic updates.** Write a valid partial
   `/app/output/result.json` before any long stage (valid JSON, real
   `case_id`, `status: "partial"`, what is done so far). Update it after
   each stage by writing a temp file and renaming it into place
   (`result.json.tmp` → `mv`), so a reader never sees a torn file.
3. **Every contract field present.** If the contract asks for a field you
   cannot fill (e.g., a page count for an unreadable PDF), include the
   field with a `null`/empty value **and** explain why in the uncertainty
   or notes field. Missing keys look like a broken submission; explained
   nulls look like honest work.
4. **Honest status.** Use the status vocabulary the contract defines. If
   it doesn't, use `complete` / `partial` / `failed`. A partial result
   states exactly which segments/deliverables are missing and why
   (budget, unreadable source, ambiguous instruction).
5. **Sources.** List the actual material files you read (paths under
   `/input/`, e.g. `paper.pdf` extracted with `pdftotext`), plus any
   external sources you genuinely consulted. Do not list sources you did
   not use.
6. **Uncertainty.** Record unresolved translation choices: ambiguous
   terms, illegible figure text, numbers you could not cross-check,
   segments whose classification you overrode by hand.
7. **Change record.** Mirror `change_log.md`: intake observations,
   segmentation overrides, every manual edit to segment text, every
   post-edit to a `> TGT` block, every re-run of the checker/deriver,
   any deliberate deviation from the contract (with justification).

## Recommended skeleton (adapt to the real contract — it wins)

```json
{
  "case_id": "<exact value from /input/case.json>",
  "status": "complete | partial | failed",
  "deliverables": {
    "bilingual_master": "/app/output/bilingual.md",
    "translation_target": "/app/output/translation_target.md"
  },
  "artifacts": {
    "source_segments": "/app/output/source_segments.txt",
    "structure_inventory": "/app/output/structure_inventory.json",
    "alignment_report": "/app/output/alignment_report.json",
    "change_log": "/app/output/change_log.md"
  },
  "alignment": {
    "segments_total": 0,
    "verdict_ok": 0,
    "coverage": "see alignment_report.json"
  },
  "sources": ["<actual input files used>"],
  "uncertainty": ["<unresolved items, or empty list>"],
  "change_record": ["<summary of change_log.md entries>"],
  "partial_notes": "<if partial: exactly what is missing and why; else empty>"
}
```

## Never

- Never invent a `case_id`, a contract field, a coverage number, or a
  verification result. Numbers in `result.json` must match
  `alignment_report.json` and the deriver's coverage output.
- Never claim `complete` while `check_alignment.py` exits non-zero.
- Never fabricate source content to fill a gap; mark the gap instead.
