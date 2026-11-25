# Method notes: heading heuristics, reference grammar, raw-preserving

## 1. Heading detection heuristics and thresholds

Priority order (first match wins), per non-empty line ≤ 100 chars:

1. **Numbered** `^(\d+(\.\d+){0,4})\.?\s+<title>$` — title must start with a
   letter and contain no `.` (kills numbered list items and decimals).
   Level = number of dot-separated components.
2. **Appendix subsection** `A.1 Title` → level 2, number `A.1`;
   **Appendix** `Appendix A[:.-] Title` → level 1, number `A`.
3. **Known unnumbered words** (exact, case-insensitive, trailing colon ok):
   abstract, keywords, references, bibliography, acknowledg(e)ments,
   appendix/appendices, supplementary material(s) → level 1.
4. **ALL-CAPS**: ≥4 letters, uppercase ratio ≥ 0.85, length ≤ 80 → level 1
   (level 2 if size hints exist and size < 1.3 × body size).
5. **Size-hint short line** (only with `--sizes` TSV): size ≥ 1.2 × median
   body size, length ≤ 80, not ending in `.` → level 1 if ≥ 1.35 × else 2.

Tree building: stack of open headings; numbered headings additionally
**prefix-attach** to the node whose number is the longest existing prefix
(so `2.2.1` nests under `2`, not under the previous sibling `2.1`).

Inconsistencies (reported, never auto-fixed):

| type | trigger |
|---|---|
| `numbering_gap` | same parent & level: child numbers not consecutive (1.1 → 1.3) |
| `missing_parent` | `X.Y.Z` present but direct parent `X.Y` absent |
| `level_jump` | heading nested >1 level below its attached parent, or consecutive heading deepens by >1 |
| `duplicate_number` | same section number seen twice |

## 2. Reference grammar notes (two styles)

**Numbered-bracket**: `[n] <authors>. <title>. <venue> <vol>, <pp–pp> (<year>).`
Variant without volume: `<venue> (<year>).` Authors are initials-first
(`A. Turing, B. Lovelace`).

**Author-year**: `<authors> (<year>). <title>. <venue>, <vol>(<issue>), <pp-pp>. [doi-url]`
Authors are surname-first (`Hopper, G. & Kleene, S.` / `Von Neumann, J.`).

Extraction order per entry: strip `[n]` label → find DOI anywhere → match
author list at string head → consume a leading `(year).` (author-year) else
search `(year)` anywhere → split title at first `. ` → parse the tail with
three venue regexes (bracket-with-volume, author-year, bracket-plain).

**Known failure examples** (all land in partial/raw, never guessed):
- `Smith, John, and Jones, Mary. 2001. Title...` — full given names break the
  initial-based author regex.
- `... Journal 12 (2020) 34-56` — year before pages breaks both tail regexes.
- Titles containing `. ` (e.g. `U.S. widgets`) shift the title/venue boundary.
- CJK or accented author lists outside `[A-Za-z\-']` fail the author match.

## 3. Why raw-preserving beats field invention

A downstream consumer that trusts a fabricated `venue` or `year` silently
propagates a citation error that no validator can catch. A `parse_status:
raw` entry with the verbatim string, by contrast: (a) is auditable — the
original text is right there; (b) is reparable — a later pass (or a human)
can re-parse exactly the failed entries; (c) keeps statistics honest —
`summary.raw` measures real extraction quality. Confidence is a weighted
sum of present fields (authors .20, year .15, title .25, venue .15,
volume .10, pages .10, doi .05), and `reasons` lists what was missing, so
consumers can filter without re-parsing.
