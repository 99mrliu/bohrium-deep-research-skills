# Rebind policy (normative)

The center of gravity of this skill is **figure/table data rebinding**: every
quantitative element on a slide is *rebound* to a printed source in the paper,
with provenance, or it is removed.

## 1. Verbatim rules

1. CSV cells are exactly as printed: keep `%`, `±` / `+/-` tails, thousands
   separators, and scientific notation untouched. Reformatting is a
   presentation-layer decision and never alters the CSV.
2. Charts parse floats from CSV cells **only for plotting geometry**. The
   source strings are stored untouched in
   `charts/<chart_id>.provenance.json` (`rows_used`). Any number rendered as
   *text* (slide bullets, footers) must come from the CSV string or the paper
   text, never from the parsed float (avoids `92.30` vs `92.3` drift).
3. A trailing `%` in slide prose may fall back to the bare digits for the
   verbatim check (a percent sign is typography; the digits are data). The
   digits themselves must always match verbatim.
4. Manual transcription (worksheet path) must be verbatim; the audit will
   re-check every transcribed number against the paper text, so transcription
   errors are caught before the deck is built.
5. **Never estimate data from bitmap pixels.** If a value exists only inside
   a raster chart, it does not appear on a slide as a number; the figure is
   embedded as a crop instead.

## 2. Figure classification rule (deterministic)

`figure_harvest.py` classifies each harvested figure as:

- **replot-candidate** iff at least one *quantity word* of the figure caption
  (alphabetic token, length ≥ 4, not in the stopword list in the script —
  e.g. "accuracy", "latency", "validation") also appears in a mined table's
  caption or header row;
- **bitmap-embed** otherwise.

A `replot-candidate` is an instruction to look for its data in the CSVs and
replot from them (linking the chart to the original figure via `figure_ref`).
It is **not** a license to read values off the pixels. If no mined table
covers the figure's quantities, it stays a verified crop.

## 3. Crop verification rule

A bitmap figure enters the deck only as a crop whose zone was verified against
an actually rendered PNG (the agent must look at it). The auto zone is the
band above the caption up to the first body-text line (≥ 6 words); shorter
lines are treated as in-figure labels. Wrong zone → re-crop with
`--override fig-N=x0,y0,x1,y1` (PDF pts, top-left origin as in
`pdftotext -bbox-layout`). Caption missing → locate via the in-text reference
("see Figure N") and set the zone manually; note it in exceptions.

## 4. Number audit rules (fail-closed)

For every slide in `plan.json`:

1. **Numbers** — every numeric token in title/bullets must occur verbatim
   (whitespace-normalized, word-bounded) in the paper text or a mined CSV.
   `Figure N` / `Table N` / `p. N` mentions are excluded from the numeric
   scan and checked as references.
2. **References** — every `Figure N`/`Table N` mention must exist in
   `figures.json`/`tables.json`; `table_ref` must resolve to a *mined* table
   with an existing CSV; `chart_ref` to an existing chart provenance file;
   `figure_ref` to an existing crop. `kind: table|chart|figure` requires the
   matching ref.
3. **Units** — a whitelisted unit glued to a number (`%`, `ms`, `s`, `min`,
   `MB`, `KB`, `GB`, `Hz`, `kHz`, `MHz`, `dB`, `mM`, `mol`, `kg`, `mg`, `g`,
   `km`, `cm`, `mm`, `V`, `mA`, `A`, `J`, `K`, `W`) must appear verbatim in
   the paper text; this catches unit conflicts such as reporting `92.3 ms`
   where the paper prints seconds.

Overall FAIL ⇒ exit 1 ⇒ `build_deck.py` refuses to build. **Fix the plan,
not the checker.**

## 5. Native-editability rules

- Tables are emitted as real `<a:tbl>` graphic frames (header row bold,
  theme-colored header fill, banded rows) filled from the CSV — editable in
  PowerPoint/WPS. A screenshot of a table is a defect.
- Charts are PNGs (an accepted raster), but each carries an in-chart source
  note and a provenance JSON, so the chart can be regenerated from data.
- Figure crops carry the original caption text plus `Source: Figure N, p.X`.
- Every slide has a real speaker-notes part recording its source bindings.

## 6. Provenance chain

```
paper.pdf ──pdftotext──► paper.txt ────────────────┐
         └─captions──► tables/table-N.csv ──► replot ──► charts/*.png
         └─bbox──────► figures/fig-N.png                 + *.provenance.json
plan.json + sources ──► number_audit.json (PASS) ──► build_deck ──► pptx
```
Every hop keeps its identifiers (`table-N`, `fig-N`, `chart_id`, page), so
any slide element can be traced back to a page of the paper.
