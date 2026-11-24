# Output contract — filling `/app/output/result.json`

## Golden rule

**Read the case's real `output_contract` before writing anything.**
Open `/input/case.json`, find its `output_contract` (or equivalent field),
and fill EVERY field it actually defines. Never assume a schema from
memory or from this document — cases differ. This file only describes the
invariants that must hold regardless of the case-specific schema.

## Steps

1. Read `/input/case.json` and `/input/task.md` (and
   `environment/resources.yaml` if present). Record:
   - the real `case_id` — copy it verbatim into `result.json`;
   - requested deliverables and language direction (EN→ZH, ZH→EN, or
     bilingual aligned);
   - EVERY field of the real `output_contract`, with its required type.
2. Create `/app/work` and `/app/output`.
3. **Early partial result.** Before any long work, write a valid
   `/app/output/result.json` containing the real `case_id`, all required
   fields with honest partial/empty values, and `status: "partial"`.
4. **Atomic updates.** After each stage (extraction, ledger, each
   translated section, audit), rewrite `result.json` atomically: write to
   `result.json.tmp`, then `mv` over `result.json`. A crash must never
   leave a truncated JSON.
5. Final `result.json` must contain:
   - `case_id` — the real one;
   - every field of the case's actual `output_contract`;
   - `status` — honest: `success` (all deliverables complete, audit exit
     0), `partial` (say EXACTLY what is missing and why), or `failed`;
   - `sources` — list of the actual material files used, each with the
     extraction method (`pdftotext -layout` / `text-passthrough` /
     `degraded: <reason>`);
   - `uncertainty` — list of all `[待确认]` items and any degraded
     extraction notes;
   - change records — summary of `change_log.md`: manual ledger
     additions, `normalized` rewrites accepted, fixes made after audit.

## Final `/app/output` contents

- the case-requested deliverable(s) (clean target-language version and/or
  bilingual aligned version, per the case);
- `facts.jsonl` — the fact ledger;
- `audit_report.json` — the deterministic audit result;
- `extraction_manifest.json` — provenance of the extraction;
- `change_log.md` — change log + human-confirmation items + gaps;
- `result.json` — as above;
- the fact & source mapping (table or JSON traceability of every number,
  term, citation, figure to the source), if the case requests it as a
  separate artifact (otherwise embed it in the deliverable);
- if the case requests an editable Office/slide/diagram artifact, also
  render a real PDF/PNG preview of it.

## Honesty rules

- A partial result states exactly what is missing and why (e.g.
  "Sections 4–5 untranslated: request budget exhausted at section 3").
- Never fabricate missing software state (pretend pdftotext ran when it
  did not) or scientific data (invent a number to fill a gap).
- If extraction was degraded, `status` cannot be `success` unless every
  ledger fact was still verifiable by another stated means.
