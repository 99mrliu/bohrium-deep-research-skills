# Alignment rules — sources, regions, merge, conflict

## Source taxonomy

| source_id | what | how detected |
|-|-|-|
| `MAIN` | the paper itself | PDF in /input whose name lacks SI markers |
| `SI1`, `SI2`, … | supplementary information | filename contains supp / _si / mmc / extdata / supporting |

Regions inside a source: `body` (narrative sentences), `table` (table
lines, kept whole with their caption attached), `caption` (figure/table
caption lines). A value read from `table` must be checked against its row
label and column header; the caption is stored with the record for that.

## Source priority (for choosing the cited quote)

1. `MAIN` + `table` (the tabulated reading)
2. `MAIN` + `body`
3. `MAIN` + `caption`
4. `SI*`

Priority decides which quote represents the field in `quote`/`page`/
`source_id`. It never deletes other readings: the `readings` list keeps
every source's version, and `check` fails a reported field whose readings
were emptied.

## Merge classes → status

| alignment | meaning | adjudicated status |
|-|-|-|
| `corroborated` | same value in ≥2 sources | `reported`; note the corroboration (`"MAIN text + SI1 agree"`) |
| `single_source` | value in exactly one source | `reported` only after the accept test (subject/condition/unit/statistic); note `single source` |
| `conflict` | ≥2 distinct values across readings | see conflict handling below |
| `none` | no candidate anywhere | `not_reported` after targeted grep; or `extraction_failed` if a location exists but is unreadable |

## Conflict handling

1. **Conditions first.** Read both quotes' conditions (sample, cycle
   count, temperature, batch). Different conditions → NOT a conflict:
   pick the reading whose condition matches the field, `reported`, list
   the other readings in `notes` with their conditions.
2. **Same quantity + same condition, divergent values** (e.g. main text
   91.2% vs SI 90.8% for the same ICE) → `source_conflict`: keep all
   readings, put one verbatim quote in `quote`, enumerate the readings in
   `notes`, and mirror the field in `uncertainties`. Never average, never
   silently prefer one.
3. **Region nuance.** A text value `93%` vs a table range `92–95` for the
   same quantity is consistent (point inside range) → `reported` with the
   point value; note the table range as the tabulated reading. A text
   value outside its own table's range is a real conflict.

## Cross-source consistency rules

- Corroboration strengthens but does not replace the accept test: both
  sources could quote the same wrong-subject number (e.g. both cite a
  literature value).
- SI-only values are valid evidence; mark `source_id: SI1` and note
  `supplementary only` — a reviewer must know the main text lacks it.
- Caption readings are lowest priority: they describe axes and trends,
  not necessarily reported values; accept only when the caption states
  the value explicitly.
- When the SI corrects the main text (erratum-like phrasing: "the value
  in Table 1 should read …"), prefer the SI reading and explain in
  `notes`.

## Field record schema (result.field_results[])

As in the task contract, plus `readings`: a list of
`{source, region, page, rid, quote, scalar, units, match_score}` — every
candidate reading found across sources. `readings` is append-only: the
alignment evidence must survive your adjudication.
