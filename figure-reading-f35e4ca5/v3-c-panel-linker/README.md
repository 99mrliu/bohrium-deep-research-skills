# panel-linked-figure-reading — bundle C (多子图结构关联 / cross-panel evidence linking)

## Purpose

In multi-panel scientific figures the dominant failure is **mis-wiring**, not misreading:
answering with panel (c)'s data for a question about panel (b), attaching a caption clause
to the wrong panel, or silently dropping a panel. This skill builds the wiring diagram
before any value is read:

1. `scripts/split_panels.py` — segment the figure into panels (deterministic ink-projection
   gutter splitting + pure-numpy connected-component label detection) → `panel_map.json`.
2. `scripts/caption_parse.py` — parse the caption into per-panel verbatim clauses and find
   figures referenced but shipped without pixels → `caption_map.json`.
3. `scripts/link_matrix.py` — init / fill / check a machine-checked link matrix from every
   task question to the exact panels, tables and text spans that support it →
   `link_matrix.json`, `link_check.json`, `gap_ledger.json`.

The agent still reads the values; the skill guarantees nothing is cross-wired or dropped.

## Dependencies

- python3 stdlib + numpy 2.x + PIL 12.x (pipeline), matplotlib 3.x (example generator only).
- Optional: poppler `pdftotext` (caption extraction from a shipped PDF; absence only sets a
  `degraded` flag).
- No network, no pip.

## Inputs

- `--image`: the ONE original figure image shipped with the case.
- `--case`: `/input/case.json` (`case_id`, `output_contract` of any shape, `materials` list).
- `--task`: `/input/task.md` (the questions).
- `--caption`: optional explicit caption text file (wins over case.json / pdftotext).
- `--work`: scratch dir for all JSON artifacts (`/app/work` in the harness).
- `--out`: directory for panel crops (`split_panels.py`).

## Artifact field definitions

### panel_map.json (split_panels.py)
- `image` (str): source image path. `image_size` ([w, h]).
- `panels` (list, reading order): `id` (`p1..pn` or label-derived `p_a..`),
  `label_guess` (str|null, e.g. `"a"`), `label_detected` (bool),
  `bbox` ([x0, y0, x1, y1] pixels in the original image), `crop` (path to PNG crop).
- `labels_detected` (bool): any label cluster found.
- `single_panel` (bool): true when no split was possible.
- `warnings` (list[str]).

### caption_map.json (caption_parse.py)
- `caption_source` (str): `explicit_file` | `case_json` | `pdftotext` | `none`
  (`+ degraded` when pdftotext missing but a PDF was present).
- `caption_text` (str): full verbatim caption.
- `panel_refs` (list[str]): panel letters in order of first mention, e.g. `["a","b","c","d"]`.
- `clauses` (dict letter → list[str]): verbatim sentences assigned to that panel.
- `overview_clauses` (list[str]): leading sentence(s) applying to all panels.
- `unassigned_clauses` (list[str]): sentences that mention no panel and are not leading
  overview (kept for the agent; never silently dropped).
- `figures_without_pixels` (list): `{reference, mentioned_in}` — seeds of the gap ledger.
- `warnings` (list[str]).

### link_matrix.json (link_matrix.py)
- `rows` (list): one per task question/claim:
  - `id` (str, `q1..qn`), `question` (str, verbatim from task.md),
  - `panels` (list[str] of panel ids), `tables` (list[str] of table file paths),
  - `text_spans` (list of `{source, start, end}` char-offset spans),
  - `evidence` (list of locator strings, e.g. `"p_b bbox=[...]"`, `"table1.csv row=2 col=C"`),
  - `comparative` (bool, detected from wording), `status` (`unfilled` | `filled` | `not_needed`),
  - `reason` (str, required when `not_needed`).
- `not_needed_panels` (list of `{panel, reason}`): pixel panels deliberately unused.
- `not_needed_clauses` (list of `{clause, reason}`): caption clauses deliberately unused.

### link_check.json (link_matrix.py --check)
- `ok` (bool). `violations` (list): `{type, row_id?, detail}` — types:
  `unfilled_row`, `row_without_support`, `unknown_panel`, `unused_caption_clause`,
  `unreferenced_panel`, `content_type_mismatch`, `comparative_claim_single_panel`.
- `warnings` (list[str]).

### gap_ledger.json (link_matrix.py --check)
- `gaps` (list): `{reference, evidence (where mentioned: caption clause / task line),
  status: "no_pixels_provided"}`. Merged from `caption_map.json` `figures_without_pixels`
  and the materials list. Reported into `result.json` `gaps`/`uncertainty`; never
  reconstructed.

## Exit codes (all three scripts)

- `0` — success, no warnings.
- `2` — success with warnings/violations (inspect the JSON artifacts).
- `1` — fatal error (missing input, unreadable file, invalid override).

## Limitations

- No value digitization: numbers are read by the agent, never by these scripts.
- Alignment is structural: the check proves coverage and wiring, not answer correctness.
- Gutter splitting assumes roughly grid-like layouts with whitespace gutters; irregular
  collages need the `panel_override.json` escape hatch (see SKILL.md failure catalogue).
- Label detection guesses letters from position order, not OCR.

## Maintenance

- Pure stdlib+numpy+PIL; keep it that way (runtime has no pip/network).
- When changing artifact schemas, bump the `schema` field in each JSON and update this
  README plus `examples/minimal_example.md`.
- Deterministic by design: no randomness, no timestamps in outputs.
