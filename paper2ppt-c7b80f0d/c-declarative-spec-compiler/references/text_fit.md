# Text-fit and demotion policy (compile-time constraint enforcement)

All policies below are implemented in `scripts/compile_deck.py` and every
action is recorded in `compile_report.json`. The goal is deterministic,
auditable layout: given the same spec, the same deck comes out, and no text is
ever silently clipped or shrunk to unreadability.

## 1. The estimator (documented constants)

- Width units: **CJK / wide char (U+2E80 and above) = 2 units; any other
  char = 1 unit.** One unit ≈ 0.5 × font_size (pt) of advance width
  (proportional latin fonts average ~0.5 em; CJK glyphs ≈ 1 em).
- Chars-per-line: `floor(box_width_emu / (0.5 × font_pt × 12700))`.
- Lines per bullet: `ceil(units / chars_per_line)`, min 1; plus 0.4 line per
  bullet for inter-paragraph spacing.
- Line height = **1.3 × font_pt**; capacity = `floor(box_height_emu / (1.3 ×
  font_pt × 12700))`.
- The estimator is deliberately conservative (overestimates line counts). A
  false positive costs one harmless shrink step; a false negative would mean
  visible overflow, which is worse.

## 2. Per-kind body box budgets (builtin backend, 16:9, 12192000 × 6858000 EMU)

| Slide kind | Body box width | Body box height |
|---|---|---|
| content / conclusion / backup | slide width − 2 × 0.55 in margin | title (0.75 in) + claim (0.42 in) + gaps down to footer |
| figure | 44% of content width (image takes the right ~50%) | same vertical budget |
| two-column | (content width − 0.3 in gutter) / 2, bullets split in half | same vertical budget |
| table | full content width, but bullets get the top 42% only (table below) | 42% of vertical budget |

The template backend uses the same ladder/demotion decisions computed with
these budgets, then fills real placeholders; when a shrink step was taken it
sets the run font size explicitly (otherwise theme sizes are inherited).

## 3. Shrink ladder and floor

- Body font ladder: **20 → 18 → 16 → 14 → 12 pt**, walked one step at a time
  until the estimated lines fit the box.
- **Readability floor = 12 pt. Never below.** If the box still overflows at
  12 pt, trailing bullets are demoted into the speaker notes with a
  `[DEMOTED:text-fit]` marker until the remainder fits, and a warning is
  recorded.
- Title: 28 pt (template: theme size), wraps to at most 2 lines; longer
  titles are elided with "..." and the full title is preserved in notes
  (`[FULL TITLE]`).
- Claim banner 14 pt, footer 10 pt, table text 12 pt (fixed; these have
  bounded content by construction).

## 4. Demotion rules (content is moved, never deleted)

| Trigger | Action | Marker in notes |
|---|---|---|
| bullets > `meta.max_bullets` (default 6) | surplus bullets (from the end) to notes | `[DEMOTED:bullet-cap]` |
| estimated overflow at 12 pt floor | trailing bullets to notes until fit | `[DEMOTED:text-fit]` |
| table rows > 8 | rows 9+ to notes as JSON list | `[DEMOTED:table-rows]` |
| non-backup slides > `meta.slide_limit` | slides moved after a compiler-inserted "Backup / Appendix" divider | report `backup_overflow` |
| title > ~2 lines | elide + full title to notes | `[FULL TITLE]` |

Authoring consequence: order bullets by importance; the compiler always
demotes from the end.

## 5. Table compaction

- Max 8 data rows on the slide (plus header). Surplus rows go to notes as a
  JSON list (machine-checkable, nothing paraphrased) and the decision is
  recorded.
- Wide tables: the estimator does not model column width; keep ≤ ~5 columns
  on the slide. Move full-width tables to a `backup` slide or notes.
- Template backend: real table shape via python-pptx. Builtin backend: aligned
  text lines ("col | col"), header bold — limitation disclosed in README.

## 6. Multi-figure grid policy

The spec supports one image per `figure` slide by design. For multi-panel
comparisons: either (a) crop the paper's own multi-panel figure as ONE image
(preferred — preserves the paper's panel labels and numbering), or (b) compose
a grid PNG offline (e.g. matplotlib) and reference it. Two `figure` slides in
a row is preferable to an overstuffed single slide; the slide-limit overflow
mechanism protects the talk length.

## 7. Images

- PNG sized from its own header (IHDR + pHYs dpi, default 96 dpi) — no image
  library needed.
- Placement: aspect ratio preserved, centered inside the bounding box
  (`fit_image_in_box`), `noChangeAspect` lock set.
- Missing or unreadable image: labelled placeholder box + warning; the slide
  still builds so the pipeline never stalls on one bad crop.
