# Minimal example (SYNTHETIC EXAMPLE / 合成示例)

All text here is **synthetic**: `case.json` embeds an invented methods paragraph
(`source_text`) with 8 planted defects. Nothing is real data.

Planted defects (one per sentence, s0001–s0008):

| sid | defect | edit type |
|---|---|---|
| s0001 | subject–verb agreement ("cultures was") | agreement, grammar |
| s0002 | tense slip ("is replaced" in Methods) | tense-voice |
| s0003 | missing article ("at wavelength of") | article-preposition |
| s0004 | dangling modifier ("Using ImageJ software, the images were…") | syntax |
| s0005 | colloquial register ("a bunch of tests … worked") | register |
| s0006 | overclaim ("prove … perfect for all cell types") | hedging |
| s0007 | wordy phrase ("Due to the fact that … at this point in time") | conciseness |
| s0008 | missing comma before "then" | punctuation |

Two deliberate gate demonstrations live in `edits/02-fixes-b.json`:

- an s0009 edit with the vacuous reason *"improve fluency"* → **rejected at intake** (gate C07);
- a valid s0009 semicolon edit that `run.sh` deliberately **leaves unreviewed** →
  **rolled back** by the mandatory review gate (C04). Rollback cannot be skipped.

s0009 carries protected tokens (`p < 0.05`, `Fig. 2`); the source also contains
`37 °C`, `5%`, `[12]`, `48 h`, `80%`, `450 nm`, `30 s`, `95 °C`, `10 min` — all
verified by gate C03 end-to-end.

Run it:

```sh
cd examples/minimal && sh run.sh   # expected exit code 0
```

Deliverables appear in `out/`: `polished.md`, `changes.json`, `change-log.md`,
`review.html` (open in a browser: left original / right revised, type badges,
collapsible reason+basis, gate bar), `intake-report.json`, `result.json`.
Intermediate state (`job/`, second-run dirs) is cleaned up after the
determinism check; re-running `run.sh` regenerates everything byte-identically.
