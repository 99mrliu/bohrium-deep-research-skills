# Failure modes: how polishing silently strengthens claims (限定词消失失败案例集)

Realistic failure patterns this skill exists to catch. Each entry: the silent
drift, why it is wrong, and how the gate classifies it. Use these as a
checklist when reviewing your own edits.

## 1. Modal upgrade (情态升级)

- `The treatment **may improve** survival.` → `The treatment **improves**
  survival.`
  Verdict: `strengthened` (level 0→2). The author's honest uncertainty about a
  non-significant result becomes a factual claim.
- `These findings **suggest** a role for X.` → `These findings **demonstrate**
  a role for X.`
  Verdict: `strengthened` (0→2). Hypothesis-generating becomes confirmatory.
- `X **could** explain Y.` → `X **explains** Y.` / `X **will** explain Y.`
  Verdict: `strengthened`. `will` carries no cue word, so the sentence falls
  to the default level 2 — the drift is still caught by the level jump.

## 2. Quantifier generalization (量词泛化)

- `**Some patients** responded.` → `**Patients** responded.`
  Verdict: `scope-broadened` (quantifier dropped → generic claim).
- `in **some** animals` → `in **all** animals`
  Verdict: `scope-broadened` (rank 2→5).
- `**Most** samples were positive.` → `**The** samples were positive.`
  Verdict: `scope-broadened`. Dropping `most` reads as *all*.

## 3. Negation erosion (否定侵蚀)

- `the effect **did not reach** statistical significance` → `the effect was
  significant`
  Verdict: `negation-changed`. This is the single most dangerous polish in
  biomedical writing: it inverts the result.
- `**rarely** observed` → `seldom observed` is fine (both negation cues);
  `rarely observed` → `occasionally observed` is **not** —
  `negation-changed`.
- Watch multi-step erosion across editing rounds: `not significant` →
  `not quite significant` → `borderline significant` → `significant`.

## 4. Correlation → causation (相关变因果)

- `Biomarker Y **is associated with** disease severity.` → `Biomarker Y
  **causes** disease severity.`
  Verdict: `causality-changed` (`correlational-to-causal`). Observational
  data almost never licenses `causes`; reviewers and editors treat this as an
  overclaim.
- Sneakier variants that the gate also catches: `associated with` →
  `drives`, `linked to` → `leads to`, `correlates with` → `results in`,
  `相关` → `导致`.

## 5. Scope-condition loss (范围状语丢失)

- `X amplifies Y **in vitro**.` → `X amplifies Y.`
  Verdict: `scope-broadened`. A dish-level finding becomes a general
  biological claim.
- `**In this cohort**, Z predicted relapse.` → `Z predicts relapse.`
  Verdict: `scope-broadened` (+ tense upgrade). Single-cohort result becomes
  a universal predictor.
- `**Under these conditions**, W was sufficient.` → `W is sufficient.`
  Verdict: `scope-broadened`. The condition *was* the finding.
- `**preliminary** data indicate` → `data indicate`: the hedge is the word
  `preliminary`; dropping it = `scope-broadened`.

## 6. Compound attacks (组合漂移)

The most realistic bad edit changes several dimensions at once:

- `The treatment **may improve** insulin sensitivity in **some** animals,
  although the effect **did not reach** statistical significance.`
  → `The treatment **improves** insulin sensitivity in **all** animals,
  although the effect **was** significant.`

  One "fluency pass" produces `negation-changed` + `strengthened` +
  `scope-broadened`. The audit lists every fired kind with hit-word evidence;
  the primary verdict follows the priority order (negation first).

## 7. Near-misses that are NOT drift (勿过度回退)

- `shows` → `showed` (tense fix, same level-2 cue family) → `none`.
- `some` → `several` (same quantifier rank 2) → `none`.
- `may has` → `may have` (grammar fix, hedge intact) → `none`.
- `is associated with` → `was associated with` (tense only) → `none`.

Over-reverting these teaches the agent to fear editing; the gates exist to
permit good edits, not to freeze the text.

## 8. What the gate CANNOT see (诚实边界)

- Hedges outside the lexicon (`to some extent`, `arguably`, `据推测` variants).
- Meaning changes with no cue-word change (`tumor growth` → `tumor
  metastasis` — same level, different claim).
- Reordering that moves a negation's scope when both sentences contain `not`.
- Numbers, units, and reference labels (handled by other means; never edit
  them here).

Every `none` verdict therefore means "no *cue-level* drift detected", and the
final human/agent read-through is still mandatory.
