# Minimal example (SYNTHETIC / 合成示例)

**All content here is synthetic.** `source.md` is a fabricated English
biomedical abstract (NLRP3 / steatohepatitis) written only to demonstrate the
pipeline; it is not real research.

## What is in it

- `source.md` — synthetic abstract with **8 grammar defects** (agreement,
  tense, countability, modal+infinitive) planted across 12 sentences, plus
  several sentences whose hedging is *already correct* and must not be
  "improved" (`may improve`, `some animals`, `is associated with`,
  `in vitro`, `in this cohort`, ...).
- `edits-good.json` — batch `grammar-fixes`: 8 legal edits that repair grammar
  without touching any hedge.
- `edits-adversarial.json` — batch `adversarial`: 6 edits designed to test the
  gates:
  1. `may improve ... some ... did not reach` → `improves ... all ... was`
     (**strength-gate** revert: negation-changed + strengthened + scope-broadened)
  2. `is associated with` → `causes`, `in this cohort` dropped
     (**strength-gate** revert: causality-changed + scope-broadened)
  3. `in vitro` dropped (**strength-gate** revert: scope-broadened)
  4. edit with **no review record** (**review-gate** revert)
  5. heavy but legal rewrite keeping a level-0 hedge (applied, **heavy_rewrite
     warning**)
  6. `suggest` → `demonstrate` with valid `strength_change` authorization
     (applied, recorded as **authorized_drift**)

## Run

```sh
cd examples/minimal
sh run.sh        # exit code 0
```

## Expected outcome (verify by reading `out/`)

- `out/polished.md` — grammar fixed; hedges intact; the heavy rewrite and the
  authorized `suggest → demonstrate` change visible.
- `out/changes.json` — 10 applied, 4 reverted (3 × strength-gate,
  1 × review-gate), 0 rejected.
- `out/strength-audit.json` — per-edit drift verdicts with hit-word evidence;
  the three adversarial strength attacks carry their drift records and
  `gate: "strength-gate"`.
- `out/conservation-report.md` — what changed / what was refused / which
  hedges were conserved.
- `out/result.json` — mirrors `case.json` `output_contract`; passes
  `validate-result`.

Determinism: running `sh run.sh` twice produces byte-identical `out/`.
