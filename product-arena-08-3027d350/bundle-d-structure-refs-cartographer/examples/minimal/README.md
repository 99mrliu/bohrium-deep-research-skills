# Minimal example (SYNTHETIC — smoke test only)

**Everything in `inputs/` is synthetic**: the mini-paper, its authors, venues
and the DOI `10.1234/synth.1952.54` are invented. It describes no real
research and exists only to exercise the skill end to end with Python 3
standard library only.

## Layout

- `inputs/pages.txt` — 4-page synthetic paper, `=== page N ===` markers.
  Planted anomalies: section `2.2` absent while `2.2.1` exists; `Table 1`
  captioned but never cited; `Fig. 2` cited but has no caption; 6 references
  (3 numbered-bracket, 2 author-year, 1 deliberately corrupted).
- `inputs/case.json` — synthetic `case_id` + `output_contract`
  (toc / references / captions / structure_issues / uncertainty).
- `inputs/task.md` — the task statement for the case.
- `outputs/` — **real outputs** of actually running the pipeline below,
  read and verified by eye before committing.

## Commands

```bash
sh run.sh        # runs all three scripts, outputs land in outputs/
```

or step by step (paths relative to this directory):

```bash
python3 ../../scripts/heading_tree.py  --pages inputs/pages.txt --out outputs
python3 ../../scripts/refs_parse.py    --pages inputs/pages.txt \
       --headings outputs/headings.json --out outputs
python3 ../../scripts/structure_report.py --pages inputs/pages.txt \
       --headings outputs/headings.json --toc outputs/toc.json \
       --refs outputs/references.json --case inputs/case.json --out outputs
```

All three exit 0.

## What to look for in outputs/

- `headings.json` — 9 headings; tree nests 1.1/1.2 under `1`, and
  2.1 + **2.2.1 under `2`** (prefix attach). `inconsistencies` has exactly
  2 entries, both about the planted anomaly: `missing_parent` (section 2.2
  absent) and `level_jump` (level-3 heading under level-1 parent).
- `toc.json` — 9 entries with anchors `sec-1`, `sec-1-1`, …, `sec-2-2-1`,
  plus unnumbered `sec-abstract` / `sec-acknowledgments` / `sec-references`.
- `references.json` — `summary: {parsed: 5, partial: 0, raw: 1}`,
  `style_hint: mixed`. Entry 4 (Hopper & Kleene) has full fields incl.
  `issue: "3"` and the DOI; the corrupted `%%% BROKEN ENTRY …` entry has
  `parse_status: raw`, all fields null/empty, original string in `raw`.
- `structure_report.json` — 2 captions (Fig. 1 p.2, Table 1 p.3), 2
  mentions (Fig. 1 p.1, Fig. 2 p.2); gaps: `Table 1` caption-without-mention
  and `Fig. 2` mention-without-caption (1 each).
- `result.json` — `case_id: synthetic-mini-001`, `status: success`, all 5
  contract fields `ok`, `findings` echoing 2 heading inconsistencies,
  1+1 caption gaps, 1 raw reference.
