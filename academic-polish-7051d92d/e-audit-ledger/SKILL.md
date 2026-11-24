---
name: audit-trail-polish
description: >
  Academic English polishing with a machine-checkable audit trail: freeze the
  source into sentence units, log every edit with type / reason / basis,
  enforce MANDATORY review with non-skippable rollback, and deliver a
  self-contained review.html side-by-side report plus change log and
  contract-mirrored result.json. Trigger when the user needs 修改记录 /
  审校痕迹 / a third-party-reviewable polish deliverable (每处修改可查、可复核);
  do NOT trigger for pure Q&A, translation-only tasks, or when no change
  record or reviewable deliverable is needed.
---

# audit-trail-polish

Polish academic English **and** deliver the proof. The failure this skill fixes:
a polish job that hands back one rewritten paragraph and says "improved fluency"
gives a third party no way to judge whether each change should have been made.
Here every change is a ledger entry — frozen sentence id, original, revised,
type, concrete reason, cited basis — and the deliverables (`review.html`,
`change-log.md`, `changes.json`) are re-checkable by machine.

核心判据:改得对、说得像、没改坏、**讲得清**(this skill's重心)。

## When to use / not use

- USE: polishing with an audit trail; journal/language-editor handoff; cases
  where an advisor, co-author or editor must approve each change; any run whose
  output must survive re-execution and diffing.
- DO NOT USE: pure question answering, summarization, translation-only, or a
  quick informal rephrase where no change ledger is wanted.

## Harbor runtime contract

- Inputs: `/input/case.json` + `/input/task.md` (case materials per manifest —
  read the real files; never guess content from labels). Work in `/app/work`,
  deliver to `/app/output/result.json` plus the artifact files.
- `result.json` must contain `case_id` and **every field** of the case's
  `output_contract` (names/types differ per case — mirror them). Mappable →
  real content; unmappable → `null` + a `notes` entry. Never fabricate.
- Honest `status` (`success` / `partial` / `blocked`), `sources`,
  `uncertainty`. `partial` states concrete limits; `blocked` ships no fake text.
- Budget: 64 model requests / 900 s / 16384 tokens per response. Therefore:
  - write edit batches of **≤15 sentences each** (`edits/NN-name.json`), many
    files merged by filename order — one corrupt batch never sinks the others;
  - **save an honest partial deliverable early**, then iterate;
  - reserve the last part of the budget for a full human-style read-through —
    machine gates cannot prove "改得漂亮".
- Scripts: Python 3 standard library only, no network, no installs.

## Pipeline (scripts are deterministic: same input → same bytes)

```sh
python3 scripts/ledger.py prepare --source src.txt --job job          # freeze s0001…
python3 scripts/ledger.py intake  --job job --edits edits/ \
        --out job/intake-report.json                                  # C02/C03/C07
python3 scripts/ledger.py review  --job job --edits edits/ \
        --review review.json                                          # C04, mandatory
python3 scripts/render.py export  --job job --out out --case-id ID    # C01 + deliverables
python3 scripts/render.py idempotence --job job --polished out/polished.md
python3 scripts/result.py result-skeleton --case case.json --out skeleton.json
python3 scripts/result.py fill-result --case case.json --artifacts out \
        --out out/result.json
python3 scripts/result.py validate-result --case case.json --result out/result.json
```

### Ledger and gate semantics

- **Freeze (C01)**: the source is split into stable units `s0001…` with offsets
  and separators preserved. No merging, dropping or reordering of sentences;
  export re-fills sentence-by-sentence and verifies byte-exactly.
- **Edit entry**: `{sid, original, revised, types, reason, basis}`.
  `original` must equal the frozen sentence (anchor, C02). `types` from the
  14-type vocabulary (see `references/edit-taxonomy.md`). `reason` ≥12 chars,
  concrete, and screened against a vacuous-reason blacklist ("improve fluency",
  "提升流畅性", …) (C07). `basis` cites a style rule, termbase entry or grammar
  rule. Failing entries are **rejected with per-entry explanations**.
- **Protected tokens (C03)**: number+unit, percentages, p-values/CIs, `[12]`,
  `(Author, Year)`, `Fig. 2b`, `Eq. (3)`, URLs/DOIs/emails are extracted per
  sentence and compared; any loss or invention rejects/rolls back the edit.
- **Review (C04) — mandatory, rollback not skippable**: every accepted edit
  needs a review record `{edit_id, decision: accept|reject|query, reason}`.
  Unreviewed edits and stale edits (hash mismatch) are **rolled back
  automatically**; a `query` holds the edit back pending clarification. Never
  patch around this gate — a past submission lost points exactly for making
  review optional.

### review.html positioning

`review.html` is a **self-check and handoff tool** (self-contained, inline CSS,
zero external dependencies; open it in any browser): left original / right
revised per sentence, type badges, collapsible reason+basis, top statistics bar
and gate status. It makes human review cheap; it **does not replace peer
review** or subject-matter judgement.

## Honesty boundaries (机器门的边界)

- The gates prove **"没改坏"** — nothing lost, anchored, conserved, reviewed.
  They cannot prove **"改得漂亮"**: elegance, discipline fit and nuance still
  need the final read-through. Budget for it.
- The protected-token list is pattern-based; unusual notations may escape it —
  say so in `uncertainty` when the text is notation-heavy.
- On failure, degrade to an honest `partial` (applied subset + rollback list),
  never to silent omission.

## Files

- `scripts/ledger.py` — prepare / intake / review (gates C01–C04, C07)
- `scripts/render.py` — export (polished.md, changes.json, change-log.md,
  review.html) + idempotence check
- `scripts/result.py` — result-skeleton / fill-result / validate-result
- `references/` — edit-taxonomy.md, review-protocol.md, output-contract.md,
  failure-modes.md
- `examples/minimal/` — synthetic end-to-end demo (`sh run.sh`), including a
  deliberately vacuous edit (rejected) and a deliberately unreviewed edit
  (rolled back)
