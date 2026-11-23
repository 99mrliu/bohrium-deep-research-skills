# Text-layer rules — normalization, integrity metrics, status mapping

## Documented normalizations (textlayer.py counts every one)

| Change | Example | Recorded as |
|-|-|-|
| Ligature repair | `ﬁrst` → `first` | `ligatures` |
| Hyphen-newline join | `perfor-\nmance` → `performance` | `hyphen_joins` |
| Layout space collapse | `152    mAh` → `152 mAh` | `space_collapses` |
| Unit rejoin across line break | `152\nmAh` → `152 mAh` | `unit_joins` |

Quotes copied from `evidence_bank.jsonl` are taken **after** these
normalizations, so a scalar copied from the same entry is always a verbatim
substring of its quote. Never re-normalize by hand; if you edit a quote,
recopy it from the bank.

## Unit preservation

- Copy the unit exactly as printed (`mAh g⁻¹`, `mg cm⁻²`, `°C`, `%`).
  Never convert (no mAh→Ah, no °C→K), never "clean up" superscripts into a
  different form. If the text layer shows `mAh g-1` (ASCII fallback), keep
  that form in `units` and note `unit form: ASCII fallback` in `notes`.
- Keep error/statistic with the value: `93 ± 2 %`, `p < 0.05`, `n = 5`,
  CI bounds. A value without its printed statistic is incomplete, not wrong.
- Ranges (`92–95 %`) and inequalities (`> 90 %`, `< 0.05`) go into `scalar`
  verbatim; do not average ranges or drop the comparator sign.

## Integrity metrics (integrity.json)

- `low_text_pages`: page yielded < 120 chars → probably scanned or figure
  page. Evidence quoted from there needs a manual look; unreadable →
  `extraction_failed`.
- `normalizations`: high `hyphen_joins`/`unit_joins` counts mean heavy
  layout damage was repaired — spot-check one repaired sentence before
  trusting the page.
- `page_stats[].paragraphs == 0`: empty page in the layer.

## Column and table symptoms

- Two-column interleave: sentences from left and right columns merge into
  one line. `textlayer.py` splits at wide gutters; verify by checking that
  harvested sentences read as single-column prose.
- Table scrambling: in `-layout` mode rows survive, but merged cells and
  multi-line headers break alignment. Treat any value read from a table
  line as suspect until the row label and column header are both visible in
  the same quote; record `table:<caption>` in `notes` when a value comes
  from a table line.

## Status mapping from layer state

| Layer state at the evidence location | Status |
|-|-|
| Quote verified in bank, scalar verbatim inside quote | `reported` |
| Two bank entries, same quantity+condition, irreconcilable | `source_conflict` |
| Harvest + targeted synonym grep both empty | `not_reported` |
| Cell/location exists but unreadable (low-text, garbled) | `extraction_failed` |

`n.d.`, `not determined`, `not reported`, `–` as a cell value: the paper
explicitly declines to give the value → `not_reported`, with the cell text
quoted in `notes`. This is different from "we could not find the field":
still `not_reported`, but `notes` lists the searched terms instead.

## OCR fallback

`pdfinspect.py` exit 3 or `textlayer.py` exit 3/4: use the OCR/pdf-text
tool named in `environment/resources.yaml`, save plain text (form-feed
between pages if the tool supports it), rerun
`textlayer.py --text-file FILE`. Mark every page processed this way in
`uncertainties` (`"source": "ocr"`), because OCR digit confusions
(`0/O`, `1/l`, `5/S`) must be double-checked for any numeric field.
