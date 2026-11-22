# Audit playbook

Run order, acceptance criteria and repair loop for the four automated gates plus the mandatory visual gate. `scripts/audit_deck.py` implements gates 1–4; the visual gate is done by the agent with rendered pages.

## Gate 1 — Number gate

- Extract every numeric token (including percentages, decimals, ranges, exponents) from all slide text and notes of the delivered PPTX.
- Normalize (strip commas, unify minus signs) and search the source index text; also accept tokens whitelisted as `anchor` values in `claims.json`.
- **Finding classes**: `not_in_source` (number appears nowhere), `unit_dropped` (digits match but unit/context absent on slide where required), `rounding_suspect` (slide value is a rounded form of a source value not flagged as approximate).
- Accept when zero `not_in_source` findings, or each is explained in the report (e.g. slide number, year, page count) and whitelisted.

## Gate 2 — Citation gate

- Extract exhibit references (`Figure 2`, `Fig. 3a`, `Table 1`, `Section 4`, `[12]`) from slide text and notes.
- Each must resolve to the source registry (or the case's other materials). `unresolved` findings block delivery.
- Also flag registry exhibits cited on slides whose caption topic does not match the slide's claim — a textual hint only; the visual gate decides.

## Gate 3 — Strength gate

- For each slide, collect verbs/modals in headline and bullets; compare against the max strength of bound claim cards.
- Upgrades (`demonstrates` over `preliminary`, `proves` anywhere, unhedged superlatives without a comparator) are findings; fix wording, not the grade.

## Gate 4 — Coverage gate

- `coverage.json` must account for 100% of registry exhibits and listed sections, each exactly once, each omission with a reason. Any contract full-source rule is checked here verbatim.

## Gate 5 — Visual gate (manual, mandatory when rendering works)

For every cropped figure on the delivered deck:

1. Open the rendered source page and the rendered slide (PNG previews) side by side.
2. Confirm: the crop is the claimed panel/curve; legend, axes, units and panel letters survive; no caption text is misattributed; aspect ratio preserved.
3. Confirm tables cell-by-cell against the source region when transcribed.

Record per-figure verdicts in `audit_report.json` (`visual_gate: pass/fail/unverified` + note). If rendering is unavailable, mark `unverified` and state the impact in `result.json`.

## Repair loop

1. Fix the ledger first if the plan was wrong (claim, locator or strength), then the slide; never patch the slide to hide a ledger error.
2. Rebuild the deck, re-run gates 1–4, re-render once more at most; the budget does not allow infinite polish.
3. Whatever remains open after the second pass is recorded verbatim in `audit_report.json` under `open_findings` and echoed in `result.json.exceptions`.

## Acceptance summary

Deliverable-quality requires: gate 1 clean or fully whitelisted; gates 2 and 4 clean; gate 3 clean; gate 5 pass or explicitly unverified; content map and coverage ledger consistent with the delivered deck (spot-check three slides end to end before finishing).
