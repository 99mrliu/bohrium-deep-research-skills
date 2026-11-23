# Minimal example (SYNTHETIC — 合成示例, not a formal test case)

Synthetic input only: a 3-page artificial paper PDF (`A Synthetic Study of
Electrode Retention`, no real data) and a synthetic `target-fields.json`
with 6 fields. All outputs below are 示例 from that synthetic run.

## Commands and observed behaviour (示例)

```bash
python3 scripts/extract.py --pdf synth_paper.pdf --work-dir /app/work
# -> index -> 31 sentences, 3 page blocks

python3 scripts/adjudicate.py draft --input-dir /input --output /app/output/result.json
# -> draft -> 6 fields, all not_reported   (valid honest partial from this moment)

python3 scripts/adjudicate.py set --output /app/output/result.json \
    --field capacity_composite_100cyc --status reported --scalar "152" \
    --units "mAh g-1" --condition "100 cycles, 0.5 C, 25 deg C" \
    --quote "After 100 cycles at 0.5 C and 25 deg C the cell delivered a specific capacity of 152 mAh g-1." \
    --page 1 --paragraph-id p001.001 --notes "abstract; table row agrees"
# -> set capacity_composite_100cyc -> reported
```

## Rejections observed in the synthetic run (the point of the skill, 示例)

```text
REJECTED: scalar '99.9' is not verbatim inside --quote
REJECTED: numeric reported value requires --condition (sample/setting/time point)
REJECTED: comparative quote requires --comparator
REJECTED: not_reported requires --notes with searched terms
```

## Final check (示例)

```bash
python3 scripts/adjudicate.py check --output /app/output/result.json
# -> check: PASS (6 fields, 0 errors, 0 warnings)
```

The synthetic `retention_composite_500cyc` field resolves to
`not_reported` because the table cell literally says `n.d.`; the synthetic
`high_temp_retention_60c` field resolves to `not_reported` because the
paper's conclusion states high-temperature behaviour is unreported. Both
are auditable outcomes, not extraction failures.
