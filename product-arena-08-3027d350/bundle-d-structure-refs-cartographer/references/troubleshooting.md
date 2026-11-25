# Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `heading_tree` exits 3, `no_headings_detected` | text has no page markers or headings use an unknown style | check `=== page N ===` markers; add `--sizes` TSV; extend `KNOWN_LEVEL1` |
| Body lines detected as headings | lines start with digits + letter (e.g. "3 Results show...") | numbered regex requires the title to contain no `.` and line ≤ 100 chars; trim overlong wrapped lines upstream |
| Whole paper nested under "Abstract" | unnumbered headings default to level 1 — check `kind` field | if a known-word heading should be level 1 this is correct; else it is a detection error, report it |
| `refs_parse` exits 3 | no References heading and no trailing `[n]` list | check the heading list (`headings.json` flat); add the section title to `REFS_TITLES`; fallback needs ≥2 bracket lines |
| References glued into one entry | entries separated only by blank lines or unusual starters | current splitters: `[n]` start / surname-first+year / odd starter after complete entry; reformat input or extend `split_entries` |
| Author-year entry: `title` = "(1952)" | leading `(year).` not consumed — fixed in current version; if seen, the authors regex did not match, so year stayed mid-string | inspect `reasons`; treat as partial |
| Surname-first author loses trailing period (`Kleene, S`) | regex backtracking; `split_authors` re-adds it | if a case still slips through, normalize on read |
| `Table 1` caption missed | caption not at line start (wrapped or prefixed) | captions are line-start anchored by design; mentions still counted, so it appears as mention-without-caption — check `structure_report.gaps` |
| Fig. n mention misread as caption | wrapped line happened to start with `Fig. n` | known limitation, declared in `uncertainty` |
| DOI captured with trailing punctuation | sentence-final period | DOI is rstripped of `.,;)`; exotic trailing chars may remain — verify against the raw string |
| `result.json` status = partial | some contract field empty or `--case` omitted | read `outputs.<field>.explanation` |
| Non-ASCII garbled | input not UTF-8 | re-encode upstream; scripts read UTF-8 only |
