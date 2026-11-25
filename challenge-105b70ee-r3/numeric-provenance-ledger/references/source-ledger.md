# Canonical sources and the append-only numeric ledger

## Canonical source JSON

The lexer consumes only UTF-8 JSON that explicitly preserves readable source text. This avoids pretending that a PDF with no usable text layer has been read.

```json
{
  "sources": [
    {
      "source_id": "main-paper",
      "title": "Source title",
      "doi": null,
      "paragraphs": [
        {"paragraph_id": "p-0001", "page": 3, "text": "Exact extracted text …"}
      ]
    }
  ]
}
```

Rules:

- `source_id` is unique. `paragraph_id` is unique within its source and stable in order. `page` may be an integer, a source-specific string, or `null`; do not invent a page number after unreliable extraction.
- `text` is an exact string used for every offset and quote. Preserve superscript minus `⁻`, multiplication sign `×`, en dash `–`, em dash `—`, uncertainty symbol `±`, middle dot `·`, micro sign `µ`, Greek mu `μ`, percent `%`, and whitespace that distinguishes statistic/unit typography.
- Do not Unicode-normalize, convert units, turn `–` into `-`, replace `−` with `-`, or repair an apparent numeric typo. Keep source-reading notes in `selection.json`, not by editing the quotation.
- Tables should be transcribed into row-aware paragraph records (for example, `table2-row4`) with their headers and condition cells in `text`. A bare number stripped from its row/column headers is not a semantically usable reading.
- Figure captions and supplement paragraphs receive their own source/paragraph IDs. References such as `Fig. 2` and `Table 1` stay in the same text as the quantities they accompany.
- `case.json`, `target-fields.json`, and `task.md` define scope but are not substitutes for evidence. Inspect the actual supplied materials and record only readable text. If the Agent uses a runtime PDF/text/OCR utility, that utility is an environment reader, not a Python dependency of this Skill. Its output must be inspected before becoming canonical text.

A scanned page with no trustworthy text can be named in `extraction_failed.failure_kind` as `no_text_layer`, `ocr_unreadable`, or `unreadable_source`. Never turn that situation into `not_reported`.

## Harvest command

From the Skill root:

```sh
python3 -B scripts/numeric_ledger.py \
  --sources examples/minimal/input/sources.json \
  --ledger examples/minimal/output/numeric_ledger.jsonl \
  --audit examples/minimal/output/ledger_inventory.md
```

The harvester is Python 3.9+ standard library only. It scans each statement in source/paragraph order and emits one JSON object per line. Compound expressions are a single ledger row with exact numeric component spans:

| Kind | Typical exact raw | Scalar / units / statistic treatment |
|---|---|---|
| `scalar` | `25 °C`, `5 × 10⁻³ mol·L⁻¹` | Scalar and unit spans kept separately; typography unchanged |
| `uncertainty` | `4.8 ± 0.3 mV` | Scalar is `4.8 ± 0.3`; central/uncertainty components have individual spans |
| `range` | `2–4 ms` | En dash remains in scalar and range endpoints are components |
| `inequality` | `<0.2 °C` | Comparator is `<`; scalar remains `0.2` |
| `percent` | `8%` | Units are exactly `%` |
| `percentage_point` | `0.6 percentage points` | Units are exactly `percentage points`, never converted to `%` |
| `p_statistic` | `p<0.01` | Full raw is statistic; scalar `0.01`; comparator `<` |
| `n_statistic` | `n=18` | Full raw is statistic; scalar `18`; comparator `=` |
| `confidence_interval` | `(95% CI 0.4–1.1)` | Full raw is statistic; confidence, lower, and upper components are ledgered |
| `table_reference`, `figure_reference` | `Table 1`, `Fig. 2` | Reference numbers are components, not scalar answers |
| `numeric_residual` | `6`, `12` inside `C6H12O6` | Safety-net numeric fragments in identifiers; Agent must not mistake them for measurements |

Every row includes `token_id`, `source_id`, `page`, `paragraph_id`, `statement_id`, `start`, `end`, `raw`, `scalar`, `units`, `statistic`, `comparator`, component offsets, statement quote, context offsets/text, and a SHA-256 hash of paragraph text. Spans are **half-open Unicode-codepoint offsets within that paragraph's exact `text`**, not UTF-8 byte positions. JSON escaping does not change the decoded string.

## Append-only invariant

- A first run creates the file. A repeat with identical source order/content appends zero lines and preserves existing bytes.
- New source/paragraph records may be added **at the end**, producing new IDs. Inserting or changing earlier text can renumber later IDs, so the script treats an ID/content collision as fatal instead of rewriting history.
- After a collision, investigate the source adapter. If a corrected source genuinely requires renumbering, use a new ledger path and explicitly redo semantic selections; do not hand-edit old rows.
- A final JSONL line without a newline is treated as a torn ledger and rejected. Duplicate IDs and malformed lines are rejected.
- The result builder recomputes the harvest and compares each current expected row to the stored row before using any ID.

## Lexer boundary and required inspection

The recognizer handles common SI-style units and scientific typography, but it does not understand arbitrary domain notation, OCR spacing errors, every language, mixed table layouts, or all equation syntax. Residual ASCII/superscript digits are ledgered to reduce silent loss, but semantic completeness still requires comparing the readable text and ledger inventory. Unsupported notation can be represented faithfully by adding an explicit source-reading limitation or by improving the lexer and rerunning with a fresh ledger; never fill gaps with inferred numbers.
