# Minimal example (SYNTHETIC — 合成示例, not a formal test case)

This example uses a **synthetic 3-page paper PDF** generated for local
self-testing (`A Synthetic Study of Electrode Retention`, artificial
sentences, no real data) plus a synthetic `target-fields.json`. It exists
only to demonstrate the interface and commands end-to-end. All outputs
below are示例 outputs from that synthetic run, not formal case results.

## Synthetic input

- `synth_paper.pdf` — 3 pages: quantified sentences, a table with an
  `n.d.` cell, a cross-page continued table, a hedged sentence, an author
  conclusion, a stated limitation.
- `target-fields.json` — 6 synthetic fields, e.g.
  `capacity_composite_100cyc` (expect `mAh g-1`), `retention_composite_500cyc`
  (the table cell is `n.d.`), `high_temp_retention_60c` (absent from the
  synthetic paper → must be `not_reported`).

## Commands

```bash
python3 scripts/pdfinspect.py --pdf synth_paper.pdf --out /app/work/inspect.json
python3 scripts/textlayer.py  --pdf synth_paper.pdf --work-dir /app/work
python3 scripts/harvest.py    --work-dir /app/work
```

## Observed synthetic output (示例)

```text
inspect -> pages=3 chars=1593 low_text=[]
textlayer -> 7 paragraphs, 3 pages; low_text=[]
harvest -> 17 bank entries ({'quantified': 15, 'cued': 2})
```

Bank entry (示例, verbatim from the synthetic run):

```json
{"bank_id": "E0001", "page": 1, "pid": "p001.001", "source": "MAIN",
 "quote": "After 100 cycles at 0.5 C and 25 deg C the cell delivered a specific capacity of 152 mAh g-1.",
 "numbers": ["100", "0.5", "25", "152"], "cues": ["quantified"]}
```

Field binding for the synthetic fields (示例 of the expected semantics):

| field_id | expected handling |
|-|-|
| `capacity_composite_100cyc` | `reported`, scalar `152`, units `mAh g-1`, quote = E0001, condition `100 cycles, 0.5 C, 25 deg C` |
| `retention_composite_100cyc` | `reported`, scalar `93`, units `%`, quote from E0009/E0016; note the table's `92-95` range as the tabulated reading |
| `ice_first_cycle` | `reported`, scalar `91.2`, units `%`, quote = E0010 |
| `electrode_loading` | `reported`, scalar `12`, units `mg cm-2`, quote = E0006 |
| `retention_composite_500cyc` | `not_reported` — the table cell says `n.d.` (quoted in notes); never invent a value |
| `high_temp_retention_60c` | `not_reported` — absent from the synthetic paper; the conclusion even states high-temperature behaviour is unreported (E0017) |
