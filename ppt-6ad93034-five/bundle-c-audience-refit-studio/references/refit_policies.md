# Refit policies — audience-refit-studio

The full editorial + mechanical policy behind SKILL.md. The scripts
enforce (a)–(d); the agent owns everything else.

## 1. Roles and slide typing

Every paragraph in the deck model carries a role:

| role | meaning |
|---|---|
| `title` | paragraph in a title/ctrTitle placeholder |
| `body` | any other shape paragraph |
| `notes` | speaker-notes paragraph (notes slide part) |

Slide *roles* (background / gap / method / evidence / backup) are an
editorial classification the agent assigns when planning the refit; they
drive the compression order below.

## 2. Op vocabulary (`refit_ops.json`)

The file is a JSON list of ops (or `{"ops": [...], "target_slides": n}`).
**Every op requires a non-empty `reason`.** Indices are 0-based positions
in the current deck state at the moment the op is applied; ops apply in
list order.

```jsonc
[
  {"op": "rewrite_paras", "slide": 1,
   "paras": [{"pid": "s1p0", "text": "New title"}],
   "reason": "merge background+gap per brief §5",
   "introduced_numbers": [], "dropped_numbers": [], "dropped_terms": []},
  {"op": "set_notes", "slide": 2, "text": "...", "reason": "..."},
  {"op": "delete_slide", "slide": 3, "reason": "...", "dropped_numbers": ["90.0%"]},
  {"op": "move_slide", "from": 0, "to": 2, "reason": "..."},
  {"op": "add_slide", "after": 2, "donor": 0,
   "paras": [{"pid": "s0p0", "text": "Next Steps"}],
   "reason": "advisor needs a next-steps slide; donor cloned"}
]
```

`rewrite_paras` pids reference the model produced by `deck_io.py read`
(`s<slide>p<n>`). `add_slide` pids reference the donor slide's pids;
unlisted paragraphs keep the donor's text. `set_notes` replaces the notes
text (first para gets the text, extras blanked); the slide must already
have a notes part.

### Honesty declarations

- `introduced_numbers`: numbers that appear in the new text and are NOT
  in the before deck or the paper. Each entry is itself a claim that must
  be defensible; the reason field of the op explains it.
- `dropped_numbers`: numbers removed by this op that do not survive
  anywhere else in the deck and are not on a slide this op deletes.
- `dropped_terms`: locked terms intentionally removed by this op.

## 3. Audience profiles (what changes, what never does)

| audience | zh | foreground | allowed to shrink | never touches |
|---|---|---|---|---|
| advisor | 导师 | progress, problems, next steps | tutorial background, related work | measured numbers, term surfaces |
| reviewer | 评审 | novelty, validation, threats to validity | tutorial background | measured numbers, ablation numbers |
| peer | 同行 | method detail, reproducibility | motivation rhetoric | measured numbers, hyperparameters |

## 4. Language switch (zh ↔ en)

- All `title`/`body`/`notes` text translates.
- Locked terms (`terms.json → do_not_translate`) keep their ORIGINAL
  surface form; they are never translated, transliterated, or re-cased.
- First use after the switch gets a short target-language gloss in
  parentheses; afterwards the locked surface stands alone.
- Punctuation and spacing localise with the language; numbers and units
  do not localise (92.3% stays 92.3%, never 92,3 %).

## 5. Compression / expansion order

To reach `target_slides` < current:

1. Merge `background` + `gap` into one "Background & Motivation" slide.
2. Fold method minutiae into `backup` slides.
3. Only then consider dropping related-work slides.

Hard rules:

- `evidence` slides never lose their numbers. If the slide goes, its
  numbers are re-homed on a surviving slide or declared in
  `dropped_numbers`.
- `backup` absorbs detail before any evidence slide is touched.
- Expansion uses `add_slide` with an existing donor — never a blank,
  unstyled layout.

If the target is still unreachable, land at the nearest feasible count and
record an exact exception in `result.json`.

## 6. Audit definitions (`conserve_check.py`)

### (a) Numeric tokens

Token regex covers: integers, decimals, thousands separators (`1,000`),
percents (`92.3%`), scientific `×10^n` / `e-notation` (`1e-3`), and glued
unit symbols (`3.5s`, `12mg`, `45°`). Comparison is a **deck-wide
multiset** diff (numbers may move between slides) plus per-slide detail in
the audit JSON.

- NEW token ⇒ must appear verbatim in `paper.txt` or in some op's
  `introduced_numbers`. Otherwise FAIL, naming the token.
- DROPPED token ⇒ must be in some op's `dropped_numbers`, or the token's
  full before-count must occur on slides this op set deleted. Otherwise
  FAIL, naming the token.

### (b) Terminology

- For each locked surface: total occurrences before vs after. Loss is a
  FAIL unless the lost occurrences all sit on deleted slides or the term
  is in some op's `dropped_terms`.
- Misspelling probe: normalised (lowercase, alnum-only) edit-distance-1
  candidates near locked surfaces in the after text are flagged as
  fabrication suspects and FAIL the audit.

### (c) Surgical scope

A slide is *named* by an op if the op targeted its position (rewrites,
notes, deletion) or produced it (add_slide). Every unnamed slide's
`text_hash` (sha256 of its concatenated paragraph texts) must be identical
before and after, and the output part set must equal the part set
predicted by replaying the ops.

### (d) Slide count

After-count must equal `target_slides` from the ops file or the work
order; otherwise FAIL with both numbers in the message.

## 7. Styling preservation rule

Text edits replace run TEXT only. The first run of a rewritten paragraph
receives the full new text; remaining runs are blanked (`<a:t></a:t>`);
all `a:rPr` run properties are left untouched. Paragraphs without runs
receive one synthetic run (`lang="en-US"`). This is the simplest
lossless-styling strategy: font, size, colour, and language of the first
run carry the new text verbatim.
