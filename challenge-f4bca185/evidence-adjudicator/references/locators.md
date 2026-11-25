# Locator specification

All paths are POSIX-style paths relative to the runtime input directory (`case.json` and `task.md` included). `exact_substring` is copied directly from the observed source cell/text or decoded scalar value; it is not a generated answer.

## Text and Markdown substrings

`kind=text_substring` includes:

- `source`: input-relative path;
- `start` and `end`: zero-based, end-exclusive Unicode code-point offsets into that document's decoded UTF-8 text;
- `line` and `column`: one-based line and column containing `start`;
- `exact_substring`: `text[start:end]`.

Offsets in JSON raw-text searches describe the original JSON document text, not normalized JSON. Labelled-text anchors may span the whole original line; `exact_field_value` separately records the conservatively captured source field text. Enabled normalized matching may anchor a whole line because zero-trim/case-fold mappings do not pretend to provide a smaller exact span.

Alphanumeric token boundaries and decimal boundaries prevent values such as `12` from matching the inside of `512` or `12.5`. Substrings shorter than two characters are not accepted through broad document search; structured same-field evidence can still adjudicate them.

## CSV and TSV rows

`kind=csv_cell` includes `source`, `row_number`, `column`, and `exact_substring`. The header is physical row 1, the first data record physical row 2. `row_number` is the source row, not an output index. Quoting/newline corner cases should be checked against the original text by the reviewer; the cell string itself is exact after standards-compliant CSV decoding.

Extractor records additionally expose `record_locator` as this source row number. Review-output field paths use `/column_name`; `/` and `~` inside nested JSON keys are escaped as described below.

## JSON pointers

`kind=json_pointer` includes `source`, `json_pointer`, `exact_substring` (decoded scalar text), and `serialized_value` (canonical JSON for the scalar, preserving type). Pointers follow RFC 6901 escaping (`~0` for `~`, `~1` for `/`). List indexes are zero-based. `record_locator` identifies the containing list object or record collection. A JSON pointer is an exact structural locator, so no misleading raw-text offset is invented for reformatted JSON.

## PDF pages

`kind=pdf_page_substring` includes all text-substring fields plus one-based `page`. Text comes from `pdftotext -layout FILE -`; form feeds divide pages, and offsets/lines/columns are local to that page's extracted text. The original PDF's printed page label may differ from the physical PDF page index; the locator always means physical extraction order.

No available converter, nonzero converter status, no extracted text, or unreadable/scanned content yields a source error/unresolved claim. There is no OCR fallback, screenshot interpretation, guessed page number, or fabricated PDF quote.

## Anchor use in downstream reviews

Reviewers should open the source at the row/pointer/page/offset and check record identity, field meaning, units, and context. A conflict anchor stores both the alternate `value` and its `anchor`. Missing/unusable anchors identify explicit not-reported or unknown-unit evidence; these never serve as positive corroboration.
