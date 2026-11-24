# Vancouver numbering rules (as enforced by `numbering_check.py`)

Vancouver style numbers citations in the order they first appear in the
text, and the reference list is ordered by that citation order — not
alphabetically, not by year. The examples below are synthetic.

## 1. Numbering by first appearance

The first work cited in the text is `[1]`, the next *new* work cited is
`[2]`, and so on. Re-citing an earlier work reuses its number.

```
Template transfer reaches high precision with good templates [1], while
sequence-only predictors need no template at all [2]. Pooling several
templates raises recall [3], but the low-identity weakness of [1] remains.
```

First appearances: `[1]`, then `[2]`, then `[3]` — legal. Had the second
sentence introduced `[3]` before `[2]` ever appeared, that is a
first-appearance violation:

```
... predictors need no template at all [3].   <-- VIOLATION: [2] never seen yet
```

`numbering_check.py` walks the draft in reading order, tracks the set of
numbers seen, and requires each newly appearing number to be exactly
`len(seen) + 1`.

## 2. Marker syntax

- Single: `[1]`
- List: `[1,2]` (two works supporting one statement)
- Range: `[1-3]` (three or more consecutive numbers; equivalent to `[1,2,3]`)
- Mixed: `[1,4-6]`

The checker accepts optional inner whitespace (`[1, 4-6]`) and expands
ranges before analysis. Descending ranges (`[3-1]`) are malformed and are
rejected as a usage error. Markers are placed **before** the punctuation of
the clause they support in this skill's convention:

```
... carries a partially mismatched pocket [1].
```

Whatever house style applies, placement must be consistent; the checker
analyzes markers regardless of which side of the period they sit on.

## 3. Bibliography order = citation order

The reference list is numbered in first-appearance order, so the manuscript
bibliography is a permutation of the provided bibliography whenever the
provided one is not already in citation order. In this skill, `bib.json`
list order *is* the manuscript's reference-list order: marker `[n]` denotes
`bib.json` entry `n`. If you reorder citations in the text, you must also
reorder the bibliography (the `--fix` mode emits the reordered list).

## 4. Renumbering procedure on revision

Numbering breaks silently whenever sentences move, are inserted, or are
deleted. On every revision that touches sentence order:

1. Run `numbering_check.py` (no `--fix`). If it exits 0, nothing to do.
2. If it reports first-appearance violations, run it with `--fix`:
   - the draft's **markers** are rewritten with the old→new mapping
     (prose is never touched);
   - the bibliography is rewritten in citation order (`--out-bib`);
   - a change record JSON (`<out-draft stem>.changes.json`) records the
     old→new mapping and how many markers were edited.
3. Adopt the renumbered bibliography order in `bib.json` (re-run
   `bib_parse.py` on the corrected source, or reorder entries to match).
4. Re-run the full audit (numbering, coverage ledger, claim-citation)
   once to confirm green.

Example (synthetic). Before — second work cited is numbered 3:

```
... no template at all [3]. ... pooling templates [2].
```

`--fix` produces the mapping `{1->1, 3->2, 2->3}`, rewrites the markers:

```
... no template at all [2]. ... pooling templates [3].
```

and reorders the bibliography so that the work formerly listed third is now
second. The change record shows `"markers_edited": 2`.

## 5. What the checker does *not* do

- It never rewrites prose; `--fix` touches markers only.
- It cannot repair markers with no bibliography entry (`[7]` with six
  entries): those must be resolved by the writer, from the sentence content
  and the claim records.
- It does not judge whether a sentence *should* cite a work; that is the
  coverage ledger's and the writer's job.
- Uncited bibliography entries and duplicate-definition risks are reported
  as warnings: they do not fail the numbering check on their own, but the
  coverage ledger and claim-citation check may fail on the same facts.
