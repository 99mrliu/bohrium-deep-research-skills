# Wiring rules (linking_rules)

The link matrix is the contract between *what the task asks* and *where the answer is
allowed to come from*. These rules are what `link_matrix.py --check` enforces.

## Rule 1 — one claim ← named panels only

A claim may use **only** the panels, tables and text spans named in its matrix row.
Evidence cells must be locatable:

- panel: `panel id + bbox` (bbox from `panel_map.json`, e.g. `p_b bbox=[x0,y0,x1,y1]`)
- table: `file + row/col` (e.g. `table1.csv row=2 col=group_B`)
- text: `source + char offsets` (e.g. `caption_map.json clauses.b[0] chars 0–48`)

If the right panel is not in the row, fix the row first — never cite from memory.

## Rule 2 — comparative claims need ≥ 2 panels

Any question phrased as a comparison (`compare`, `vs`, `between`, `differ`, `relative`,
`correlat`, 比较, 相比, 对比) is flagged `comparative: true` at init. A filled comparative
row citing fewer than two *existing* panels is a `comparative_claim_single_panel`
violation. Comparing "panel (a) with the table" is allowed: cite the panel **and** the
table row/col — the rule demands two *supports*, at least two of which are panels when the
claim is panel-vs-panel.

## Rule 3 — a panel may support many claims; every claim must name its panels

Reuse is fine; anonymity is not. Conversely, at check time **every pixel panel must be
referenced by ≥ 1 row or marked `not_needed`** — this is what catches silently dropped
panels. Same for caption clauses: referenced or explicitly excused.

## Rule 4 — how to mark not_needed

In the fill fragment:

```json
{
  "not_needed_panels": [{"panel": "p_c", "reason": "task asks only about kinetics"}],
  "not_needed_clauses": [{"letter": "c", "reason": "no question touches panel (c)"}],
  "rows": [{"id": "q3", "status": "not_needed", "reason": "requires Figure 2, a declared gap"}]
}
```

A `not_needed` row/clause/panel without a reason is itself a violation
(`not_needed_without_reason`). Excusing is a decision; decisions need reasons.

## Rule 5 — the gap ledger (organization v2)

Figures mentioned in text or captions but shipped **without pixels** are declared gaps:

- seeded by `caption_parse.py` (`figures_without_pixels`) and extended from `task.md`
  mentions in `--check`;
- each entry: `{reference, evidence: where mentioned, status: "no_pixels_provided"}`;
- report them in `result.json` under `gaps` and mention in `uncertainty`;
- **never reconstruct** their content from the caption text, from memory, or by drawing;
- questions answerable only from a gap figure → row `status: "not_needed"`, reason naming
  the gap, and the corresponding `output_contract` field filled with an explicit
  "not answerable: Figure N pixels not provided" — the field is filled, honestly.

## Rule 6 — status honesty

`result.json status: "success"` only when every contract field is filled and every claim
is locatable through the matrix. Any violation left at final check → `partial` with the
violations summarized in `uncertainty`. The matrix is machine-checkable precisely so that
honesty is cheap.
