# Minimal example — synthetic demo case (合成示例 / synthetic 示意输出)

All data below are **synthetic** (合成示例), produced by `make_synthetic_case.py` with a
fixed seed. Outputs shown are 示意输出 — illustrative excerpts, not real science.

## 0. Generate the demo case

```bash
python3 examples/make_synthetic_case.py --out /tmp/f35e-c-demo
# prints: /tmp/f35e-c-demo   (figure1.png, caption.txt, case.json, task.md, table1.csv)
```

The caption ends with `See also Figure 2 for the microscopy.` — Figure 2 is **not**
shipped in `materials`, so it must land in the gap ledger.

## 1. split → caption_parse → link_matrix init

```bash
python3 scripts/split_panels.py \
  --image /tmp/f35e-c-demo/figure1.png \
  --work /tmp/f35e-c-work --out /tmp/f35e-c-work/panels
# -> wrote panel_map.json with 4 panel(s)                     [exit 0]
#    p_a [27,49,544,421]  p_b [652,38,1169,389]  p_c [30,514,544,887]  p_d [652,514,1169,887]

python3 scripts/caption_parse.py \
  --case /tmp/f35e-c-demo/case.json --task /tmp/f35e-c-demo/task.md \
  --caption /tmp/f35e-c-demo/caption.txt --input-dir /tmp/f35e-c-demo \
  --work /tmp/f35e-c-work
# -> wrote caption_map.json: 4 panel ref(s), 1 figure(s) without pixels   [exit 2]
#    clauses a-d verbatim; overview: "Figure 1. / Overview of the synthetic experiment."
#    unassigned: "See also Figure 2 for the microscopy."
#    WARNING: figures_without_pixels: Figure 2

python3 scripts/link_matrix.py \
  --panels /tmp/f35e-c-work/panel_map.json \
  --captions /tmp/f35e-c-work/caption_map.json \
  --task /tmp/f35e-c-demo/task.md --work /tmp/f35e-c-work
# -> wrote link_matrix.json with 3 unfilled row(s)            [exit 0]
#    q1 (suggests p_b), q2 comparative (suggests p_a, p_d), q3 open
```

## 2. fill — example agent-written fragment (`/tmp/f35e-c-fill.json`)

q1 (the panel-(b) question) is answered from panel `p_b` + the CSV table; q2 (the
comparison) cites two panels; q3 is intentionally left unfilled for this demo.

```json
{
  "rows": [
    {
      "id": "q1",
      "panels": ["p_b"],
      "tables": ["/tmp/f35e-c-demo/table1.csv"],
      "evidence": [
        "p_b bbox=[652,38,1169,389] bar heights ctrl=1.00 trtA=1.85 trtB=1.02, *** over trtA",
        "table1.csv row=treatment_A col=significant_vs_control -> yes; row=treatment_B -> no",
        "caption_map.json clauses.b[0] '(b) Grouped quantification with significance.'"
      ],
      "status": "filled"
    },
    {
      "id": "q2",
      "panels": ["p_a", "p_d"],
      "evidence": [
        "p_a bbox=[27,49,544,421] x-axis: time (s) 0-10",
        "p_d bbox=[652,514,1169,887] x-axis: frequency (Hz) 0-500"
      ],
      "status": "filled"
    }
  ]
}
```

```bash
python3 scripts/link_matrix.py --panels /tmp/f35e-c-work/panel_map.json \
  --captions /tmp/f35e-c-work/caption_map.json --task /tmp/f35e-c-demo/task.md \
  --work /tmp/f35e-c-work --fill /tmp/f35e-c-fill.json
# -> merged 2 fragment row(s) into link_matrix.json           [exit 0]
```

## 3. check — excerpt of `link_check.json` (示意输出)

```bash
python3 scripts/link_matrix.py --panels /tmp/f35e-c-work/panel_map.json \
  --captions /tmp/f35e-c-work/caption_map.json --task /tmp/f35e-c-demo/task.md \
  --work /tmp/f35e-c-work --check
# -> wrote link_check.json (3 violation(s)) and gap_ledger.json (1 gap(s))   [exit 2]
```

```json
{
  "schema": "link_check/1",
  "ok": false,
  "violations": [
    {"type": "unfilled_row", "row_id": "q3",
     "detail": "row has no evidence yet: What overall conclusion does the figure support ..."},
    {"type": "unused_caption_clause",
     "detail": "caption clause for panel (c) not referenced by any row and not marked not_needed"},
    {"type": "unreferenced_panel",
     "detail": "pixel panel p_c not referenced by any row and not marked not_needed"}
  ],
  "warnings": ["gap_ledger: 1 figure(s) without pixels: Figure 2"],
  "summary": {"rows": 3, "panels": 4, "caption_clauses": 4, "gaps": 1}
}
```

The only violations are the intentionally unfilled row `q3` and the consequently
unreferenced panel `p_c` / its caption clause — exactly the wiring holes a reviewer
would otherwise have to find by eye.

## 4. `gap_ledger.json` — the Figure 2 gap (示意输出)

```json
{
  "schema": "gap_ledger/1",
  "gaps": [
    {
      "reference": "Figure 2",
      "evidence": "caption: referenced in caption but no image pixels shipped in materials",
      "status": "no_pixels_provided"
    }
  ]
}
```

Merge this ledger into `result.json` `gaps`/`uncertainty`. The microscopy content of
Figure 2 is **never reconstructed** — it is a declared gap (organization revision v2).
