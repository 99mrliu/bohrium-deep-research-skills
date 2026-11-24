# examples/minimal — SYNTHETIC example (合成示例)

**Everything here is synthetic**: the Chinese "grant paragraph" and the
English draft were invented for this demo (nano-catalysis / low-temperature
SCR denitration). No real proposal, data, or literature is involved. All
outputs under `out/` carry the same synthetic status.

## What it demonstrates

- `detox.py lint` catches the Chinglish planted in the English draft
  ("With the increasingly...", "has important scientific significance",
  "is easy to be deactivated", nominalizations, connector abuse, ...).
- The Agent (LLM) rewrites the draft into idiomatic grant English — in this
  self-contained example the rewrite and the back-translation fillings are
  pre-scripted inside `run.sh` so the example runs without a model; in real
  use the Agent produces them.
- `align.py align/coverage` aligns zh/en sentences and proves surface
  conservation (numbers, units, years, names, `[n]` citations).
- `align.py backtrans-template/-check` gates the back-translation QA:
  unfilled or `mismatch` pairs force `uncertainty` and forbid `success`.
- `result.py result-skeleton/validate-result` mirrors and checks
  `output_contract`.

## Run

```sh
sh run.sh          # exit code 0 on success; artifacts land in out/
```

Deterministic: two consecutive runs produce byte-identical `out/`.

## What to inspect

- `out/detox-report.json` / `out/detox-report.md` — hits on the planted
  Chinglish, with category and fix suggestion per hit.
- `out/alignment-table.md` — zh/en sentence pairs with per-pair
  conservation status.
- `out/coverage.json` — `summary.all_conserved` should be `true`.
- `out/backtrans.json` — filled worksheet (6 pairs; one honest
  `minor-difference`).
- `out/result.json` — passes `validate-result`.
