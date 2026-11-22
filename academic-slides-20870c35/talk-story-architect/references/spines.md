# Narrative spine library

A spine is an ordered list of beats; each beat maps to one or more slides. Choose one spine per talk, state the choice and any hybridization in `/app/work/audience.json`, then map the paper's material onto beats. Beats may be merged (two beats, one slide) but a slide still carries exactly one message. The work order's mandated sections or slide list override any spine.

## 1. Progress spine (group meeting, 组会/中期)

Use when the audience knows the project and needs state, not persuasion.

1. **Recap** — the agreed goal and last milestone, one slide, no new content.
2. **Plan vs actual** — what was promised for this period, what exists now.
3. **Key evidence** — the one or two results that carry the period, each with its qualified strength.
4. **Blockers** — what is stuck, why, what was tried; be specific, this is why the meeting exists.
5. **Ask / next step** — the decision or help needed, and the plan to the next checkpoint.

Adaptation levers: background nearly zero; method detail only where it caused a blocker; conclusion sits at "plan vs actual".

## 2. Defense spine (开题/毕业答辩, committee judges validity)

1. **Problem** — the question and why it is worth a thesis/project.
2. **Gap** — what prior work cannot do, stated fairly with citations.
3. **Insight** — the one idea everything else hangs on.
4. **Method** — enough to judge soundness, not to reproduce.
5. **Validation** — evidence the method works, controls and baselines first.
6. **Contribution boundary** — what is claimed, at what strength, and what is explicitly not claimed (limitations that change interpretation).
7. **Takeaway** — the opening question answered at its qualified strength.

Adaptation levers: every claim beat needs its strongest available evidence on-slide; expect objections at gap, validation and boundary — plan backups there.

## 3. Conference spine (会议报告, mixed specialist audience, short)

1. **Hook** — the surprising fact or the practical pain, one slide.
2. **Idea** — the approach in one picture or one sentence.
3. **How it works** — the minimum mechanism to make the result interpretable.
4. **Result** — the single strongest result, full evidence on slide.
5. **Meaning** — what changes for the audience; limitations in one honest line.
6. **Takeaway** — the one sentence to remember.

Adaptation levers: one result done well beats three done thinly; terminology beyond the assumed common core must be defined where used.

## 4. Review spine (项目/基金评审, conclusion-first for decision-makers)

1. **Conclusion up front** — the claim and its strength in the first content slide.
2. **Evidence chain** — the few results that carry the conclusion, ordered by strength.
3. **Method credibility** — why the evidence can be trusted.
4. **Risk and mitigation** — the limitations and open risks, already owned by the presenter.
5. **Ask** — the decision requested and what it enables.

Adaptation levers: no long background; numbers with conditions, not adjectives; anticipate "what if it fails" with a backup slide.

## 5. Pitch/teaching spine (cross-disciplinary or outreach)

Problem story → intuition → one concrete example worked end to end → result → where it fails → takeaway. Use only when the work order names a lay or cross-field audience.

## Ordering and cut rules (all spines)

- Order slides so each slide needs only what earlier slides established; if slide *n* needs a term defined on slide *n+2*, move the definition.
- Cut in this order when over budget: redundant confirmations, secondary robustness checks, method minutiae (to backup), then extra examples — never cut the limitation that changes interpretation or the control that makes the key result believable.
- Backup slides live after the takeaway and are labeled backup; they do not count against the mandated slide count only if the work order permits extras — otherwise deliver them as a separate section and record the choice.
