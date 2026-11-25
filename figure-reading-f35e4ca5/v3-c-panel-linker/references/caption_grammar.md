# Caption micro-grammar of scientific figures

How multi-panel captions are actually written, and how `caption_parse.py` cuts them into
per-panel clauses. The goal is **alignment**, not summarization: every clause stays
verbatim so it can be cited as evidence.

## 1. Skeleton

A typical caption has three layers, in order:

1. **Title / overview sentence** — `Figure 1. Overview of the synthetic experiment.`
   Applies to *all* panels. Rule: every leading sentence that names no panel reference is
   an overview clause, up to the first sentence that names one.
2. **Per-panel clauses** — sentences that name one or more panel references:
   `(a) Kinetic trace of signal vs time.` A sentence belongs to every panel it names.
3. **Trailing global material** — statistics, scale bars, cross-references
   (`See also Figure 2 ...`) appearing *after* the per-panel block and naming no panel.
   These are `unassigned_clauses`: kept verbatim, never silently dropped, and the agent
   must attach them explicitly if used.

## 2. Panel reference forms

| Form | Example | Notes |
|---|---|---|
| Parenthesized letter | `(a)`, `(b)` | Most common. Lower or upper case. |
| Bold / plain letter at clause start | `a Kinetic trace...`, **A** | Often lost when caption arrives as plain text; the parser then sees an unassigned clause — re-attach by position if the order is unambiguous, else flag uncertainty. |
| `panel A` | `as in panel A` | Case-insensitive. |
| In-figure reference | `Fig. 1c`, `Figure 2B` | Letter glued to the figure number. |
| Multi-letter clause | `(a),(b) show...` | One clause, two owners: assign verbatim to both. |
| Ranges | `(a)–(c)`, `(a)-(c)` | Expand to every letter in the range (en-dash, em-dash or hyphen). |
| In-clause sub-references | `(d) Spectrum, inset of (c)` | The clause belongs to (d); the mention of (c) is a *cross-panel dependency*: record it, do not move the clause. |

## 3. Parsing rules (implemented)

1. Protect abbreviation periods (`Fig.`, `et al.`, `vs.`, `e.g.`, `i.e.`, `cf.`, `No.`)
   before sentence splitting on `. ! ?` followed by whitespace.
2. Find panel references per sentence with the forms above; expand ranges first.
3. Leading no-reference sentences → `overview_clauses`; later no-reference sentences →
   `unassigned_clauses`; the rest → `clauses[letter]` (verbatim).
4. `panel_refs` = letters in order of first mention — this is the expected pixel order and
   is compared against `panel_map.json`.

## 4. Ambiguity handling

- **Caption letter without a pixel panel** (caption runs to (e), pixels stop at (d)):
  `caption_pixel_mismatch` in the check; add an `uncertainty` entry; never guess-merge.
- **Pixel panel without a caption clause**: the panel still exists; the matrix must either
  reference it or mark it `not_needed` with a reason.
- **Two-letter parentheticals** like `(n = 3)` or `(SD)`: not panel references unless they
  appear in a range expansion; single/double-letter whitelisting is deliberately strict.
- **Nested figures** (`Figure 1—figure supplement 2`): the supplement is a *different
  figure*; if its pixels were not shipped it goes to the gap ledger.
- **Multiple figures in one caption block**: split at each `Figure N.` header; only align
  the figure whose pixels were shipped; the others seed the gap ledger.
