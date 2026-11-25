# Evidence adjudication audit

SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE

- case_id: `SYNTHETIC-EVIDENCE-001`
- status: `partial`
- deterministic: no network, clock, random values, unit conversion, or inferred scientific answers
- comparison: exact typed scalar matching plus only the case-enabled equivalences listed below

## Decision states

- `corroborated`: 4
- `source_conflict`: 1
- `extractor_only`: 1
- `unverifiable`: 1

## Source manifest

- `case.json`; readable=`true`; sha256=`529acf5e3c3c854b943b30766aa2381f36f5e7100db7b0cf3c94f655f9f72d72`
- `materials/extracted.csv`; readable=`true`; sha256=`c0735c27b99f6ba5420b24fa1d1e39f281c21f4df117c30b9be50f11bac71280`
- `materials/method.md`; readable=`true`; sha256=`54330ddf729dc9c08e4a854024204a8bf8adb2ae9de526efd17dc154fa53d0af`
- `materials/reference.csv`; readable=`true`; sha256=`21cf4befdb829f60a1d15f1de3d8bc318022db6a36de39f92949c77f990776dc`
- `task.md`; readable=`true`; sha256=`17b85bad35a88cdd357850acc039c723c0885b5d4972ff0f2f856857e35c8066`

## Enabled normalization

```json
{
  "apply": true,
  "casefold": false,
  "collapse_whitespace": true,
  "trim_whitespace": true,
  "unicode_nfkc": false
}
```

Output normalization is restricted to corroborated strings. Conflict and missing values are never silently replaced.

## Review and limitations

- `E000003` / `R000001` / `/melting_point_K`: **source_conflict** — Independent evidence contains a different value for the identified field.
- `E000006` / `R000001` / `/unknown_unit`: **unverifiable** — The extracted value is missing or null.
- `E000007` / `R000001` / `/unsupported_label`: **extractor_only** — No independent evidence supports this non-empty extractor value.
- No evidence-backed value is defined for contract field: official_score
- E000003 /melting_point_K: source_conflict
- E000006 /unknown_unit: unverifiable
- E000007 /unsupported_label: extractor_only

An `extractor_only` value is retained as extractor content and is not source truth. `source_conflict` values are not adjudicated by plausibility. `unverifiable` covers nulls, unreadable/missing evidence, and explicitly unavailable or unit-deficient source values. PDFs without usable `pdftotext` text remain unresolved; page locations are never invented.
