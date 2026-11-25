# Layout engine reference (textfit.py + deck_forge.py)

## 1. Width model

Text width is predicted, not measured with a real font — the pipeline must run
with pure stdlib and no font files. `string_width_pt(s, size_pt)` sums a
per-character advance factor (in **em**) and multiplies by the font size and a
safety factor:

| Character class | Advance factor |
|---|---|
| CJK ideographs, fullwidth punctuation (`unicodedata.east_asian_width` ∈ W/F) | 1.00 em |
| ASCII UPPERCASE (except narrow/wide below) | 0.68 em |
| ASCII lowercase (except narrow/wide below) | 0.52 em |
| Digits | 0.55 em |
| Space | 0.28 em |
| Narrow glyphs `i l j t . , : ; ' ! \|` | 0.28 em |
| Wide glyphs `m w M W @ %` | 0.85 em |
| All other ASCII / non-wide non-ASCII | 0.55 em |

`s = Σ factor(ch) × size_pt × 1.08`.

**Justification (honest):** these are heuristics calibrated against common
sans fonts (Calibri, Helvetica/Arial, DejaVu Sans): the average latin letter
in those faces advances ≈0.50–0.53em, digits are tabular ≈0.55–0.56em, spaces
≈0.25–0.28em. A flat **+8% safety margin** is then applied so real renderer
metrics (PowerPoint, LibreOffice) almost always come out *narrower* than the
prediction. The model is deliberately conservative: it trades a little
whitespace for a hard guarantee that text never spills its box. For CJK it is
exact for fullwidth glyphs (1.00em by construction of CJK fonts) plus margin.

## 2. Wrapping

`wrap_text(text, box_w_pt, size_pt)` is greedy and deterministic:

- break opportunities: after spaces (latin), between any two CJK/fullwidth
  characters;
- a single token wider than the box is hard-split character by character
  (never dropped, never overflows);
- identical `(text, box_w, size)` always yields identical lines.

## 3. Slide geometry (16:9 default, scales with probed sldSz)

All boxes are computed in points (1pt = 12700 EMU) and emitted in EMU:

- margins: 48pt left/right; content-slide titles start at 28pt (deck title 30pt)
  and step down a ladder (28/24/20, deck title 30/26/22/18) until they fit their
  line budget (2 lines content, 3 deck title); the title box height is computed
  from the RESOLVED lines and the body (and the title-slide subtitle) shifts down
  accordingly — boxes never overlap by construction;
- body box: from below the title to the **footer zone** (bottom 6% of slide
  height) minus padding; bullet indent 16pt, line height 1.25×size, inter-
  bullet gap 0.35×size;
- `source_line`: reserved strip directly under the body, 10.5pt;
- `image`: right column = 40% of content width; body narrows accordingly;
- footer text + slide number live inside the reserved bottom zone, so the
  export audit can whitelist them.

## 4. Overflow policy ladder (per slide, in order; every step logged)

1. **(a) shrink font** 18 → 16 → 14pt. **14pt is a hard floor** — the code
   contains no path that emits smaller body text.
2. **(b) split continuation**: at 14pt, bullets are greedily packed into
   pages; extra pages become `"<title> (cont.)"` slides inserted immediately
   after the source slide (max `MAX_CONTINUATIONS = 2`).
3. **(c) move to backup**: bullets beyond the continuation budget move to
   `role:"backup"` slides appended at the very end of the deck.

Every fired step appends to `layout.json.actions[]`
(`shrink_font` / `split_continuation` / `move_to_backup` /
`backup_slides_emitted`). Anomalies (e.g. wrapping titles, a single bullet
taller than a whole page) go to `layout.json.warnings[]`.

## 5. Theme cloning (deck_forge.py)

When `--template` is given, `ppt/theme/theme1.xml` is copied **verbatim
(byte-for-byte)** from the template package into the output. All runs
reference theme entries symbolically:

- fonts: `<a:latin typeface="+mj-lt"/>` (titles) / `"+mn-lt"` (body), with
  `+mj-ea`/`+mn-ea` for East Asian text → PowerPoint/LibreOffice resolve the
  template's real major/minor fonts;
- colors: `<a:schemeClr val="accent1"/>` for titles, `tx1` for body text,
  `accent3` for source lines/footers.

**Not cloned (declared exception):** slide-master *artwork* — bitmaps,
background images, decorative shapes, custom layouts. The output uses a
minimal blank master/layout; only the theme part (fonts + color scheme +
format scheme) is carried over byte-identically.

## 6. Determinism

`layout.json` is a pure function of `(plan.json, theme.json)`: no timestamps,
no randomness, fixed iteration order. `deck_forge.forge()` writes zip members
in fixed order with a fixed docProps timestamp, so identical inputs give a
byte-identical pptx.

## 7. Post-export audit (export_audit.py)

soffice converts the deck to PDF with an isolated profile
(`-env:UserInstallation=file:///tmp/lo_audit` — never collides with a running
LibreOffice). `pdftotext -bbox` then yields every word's bounding box:

- any word outside the page rect minus a 4pt margin → `off_page` violation;
- any word whose bottom edge enters the bottom 6% footer zone → `footer_zone`
  violation, **unless** the word belongs to the intentional footer text or
  slide number (whitelist from `layout.json`);
- `pdffonts` output is attached as evidence of embedded/used fonts.

Verdict `PASS|FAIL|RENDERER_MISSING`; exit 1 on FAIL. `RENDERER_MISSING` is an
honest statement, not a pass: inspect the preview SVG/PNGs and rerun the audit
where LibreOffice exists.
