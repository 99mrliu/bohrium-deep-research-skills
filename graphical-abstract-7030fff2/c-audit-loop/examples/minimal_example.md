# Minimal example (EXAMPLE — not a formal case result)

Bundle C loop: mine → ledger → gate → inspect → patch → diff, on synthetic
inputs.

## Inputs

`/input/material.txt` (3 sentences about HeLa + staurosporine),
`/input/viability.csv`, and a starting SVG `compare.svg` that needs one
label corrected (`"Viability drops to 42%"` → `"Viability drops to 42% (CCK-8)"`).

## Calls and observed outputs (verified during authoring)

```bash
python3 scripts/mine_sources.py --materials /input --work /app/work
# -> files 3, blocks 3, numbers_indexed 7, unminable 0

python3 scripts/ledger_verify.py --ledger /app/work/source_ledger.json \
    --pool /app/work/evidence_pool.jsonl --svg /app/output/figure.svg
# GOOD ledger: gate PASS. A ledger whose entry shows "37%" while the source
# says 42% fails with: orphan-number "number '37' shown but absent from its
# evidence quotes" (verified).

python3 scripts/svg_inspect.py --svg /app/output/figure.svg \
    --out /app/work/inspection.json
# -> verdict CLEAN on well-formed SVGs; on an early multi-line-tspan build it
#    caught a real overflow false-positive source (lines must be compared per
#    tspan, not joined) — fixed in the shipped inspector.

# edit mode: source-preserving patch
python3 scripts/apply_patch.py --svg /input/compare.svg \
    --patch /app/work/patch.json --out /app/output/graphical_abstract.svg \
    --record /app/work/change_record.json
# -> status applied, operations_applied 1, diff_hunks 1, changed_lines 2,
#    bytes_before 3294, bytes_after 3302 — everything outside the one label
#    is byte-identical, proven by the recorded unified diff.

python3 scripts/render_diff.py --before before.png --after after.png
# -> changed_fraction 0.0, within_tolerance true (identity case); on a real
#    edit it reports the changed bbox so collateral damage is caught.
```

## patch.json used above

```json
{"operations": [{"op": "replace_text",
                 "old": "Viability drops to 42%",
                 "new": "Viability drops to 42% (CCK-8)"}]}
```

`apply_patch.py` aborts if `old` occurs zero or two-plus times — ambiguity is
an error to fix in the patch, not something to brute-force.

## Ledger entry that PASSES

```json
[{"element": "node-drug", "kind": "entity",
  "shows": "Staurosporine 5 uM treatment node",
  "evidence": [{"key": "material.txt#para-1",
                "quote": "We treated HeLa cells with 5 uM staurosporine for 6 h"}],
  "numbers_shown": ["5", "6"]}]
```
