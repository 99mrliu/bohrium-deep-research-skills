# Strength ladder & guardrails (限定强度阶梯与四维护栏)

Machine-checkable model of claim strength used by `scripts/strength.py`.
Every polished sentence must land on the **same rung** as its source sentence
unless the change is explicitly authorized.

## 1. Five-level strength ladder (五级阶梯)

A sentence's level = the highest level among its cue hits; no cue → level 2
(plain declarative). Editing that moves the level up = `strengthened`, down =
`weakened`.

| Level | Name | English cues | 中文线索 | Typical use |
|---|---|---|---|---|
| 0 | speculative 推测 | may, might, could, suggest(s/ed), possibly, perhaps, potentially | 可能, 或许, 也许, 推测, 疑似 | hypothesis-generating results, underpowered findings |
| 1 | tentative 倾向 | appear(s/ed), seem(s/ed), tend(s/ed) to, (un)likely, plausibly | 似乎, 看来, 倾向于 | trends without full statistical support |
| 2 | reporting 陈述 | show(s/ed), indicate(s/d), demonstrate(s/d), found, observed, report(ed), support(s), implicate(s) | 表明, 显示, 发现, 提示, 观察到 | standard results reporting (also the no-cue default) |
| 3 | strong 强断言 | establish(es/ed), confirm(s/ed), conclusively, robustly | 证实, 确证, 确认 | replicated / confirmatory evidence |
| 4 | absolute 绝对 | prove(s/n/d), always, never, must, certainly, definitely, undoubtedly, impossible, inevitably | 证明, 必然, 总是, 绝对, 毫无疑问 | almost never justified in empirical prose |

**Classic silent upgrades the gate must catch:** `may improve` → `improves`
(0→2), `suggest` → `demonstrate` (0→2), `is associated with` → `causes`
(see guardrail 3), `could` → `will` (0→2, `will` is uncued = default 2).

## 2. Four guardrails (四维护栏)

Drift on any guardrail is a drift even when the ladder level is unchanged.

### 2.1 Quantifier scope (量词范围)
Ranked narrow→broad: none/no(0) < few/little(1) < several/some/certain(2) <
many/numerous(3) < most/majority(4) < all/every/each(5);
中文: 无/没有(0) < 少数(1) < 一些/部分/某些/若干(2) < 许多(3) < 多数/大多数(4) <
所有/全部/每个(5).
Higher rank or dropped quantifier (`some patients` → `patients`) =
`scope-broadened`; lower or added = `scope-narrowed`. Same-rank synonym swap
(`some`→`several`) is **not** drift.

### 2.2 Negation scope (否定范围)
Cues: not, n't, no, never, rarely, seldom, hardly, scarcely, without,
fail(s/ed), none; 不, 没(有), 未, 无, 很少, 罕见. Any change to the negation
set = `negation-changed`. Watch covert removals: `did not reach statistical
significance` → `was not quite significant` → `was significant`.

### 2.3 Causality vs correlation (因果 vs 相关)
Causal: cause(s/d), leads/led to, results/ed in, drives, induces, triggers,
produces, generates; 导致, 引起, 造成, 促使.
Correlational: is associated with, correlates/ed with, is linked to,
relates/ed to, tied to, co-occurs; 相关, 关联, 有关, 伴随.
Any class change = `causality-changed` (direction recorded, e.g.
`correlational-to-causal`).

### 2.4 Conditionals & scope adverbials (条件句与范围状语)
Cues: in vitro, in vivo, ex vivo, in silico, in situ, in this cohort/study/
subset/population/sample, under these conditions/circumstances, in mice/rats/
humans/patients/animals, preliminary, pilot; 体外, 体内, 离体, 本研究, 本队列,
在该条件下, 初步. Removed = `scope-broadened` (an `in vitro` finding becomes a
generic claim); added = `scope-narrowed`.

## 3. Authorization of an intentional strength change (授权写法)

A strength change is sometimes legitimate (the task or the user asks for it).
It must ride on the edit as explicit metadata — there is **no** implicit path:

```json
{
  "unit": "u0010",
  "revised": "Our findings demonstrate that NLRP3 contributes ...",
  "type": "word-choice",
  "reason": "align claim strength with the confirmatory knockout data",
  "review": {"decision": "accept", "reason": "requested by user"},
  "strength_change": {
    "authorized_by": "user",
    "explanation": "User instructed: align claim strength with the confirmatory knockout data (suggest -> demonstrate)."
  }
}
```

- `authorized_by`: `"task"` (the written task brief demands it) or `"user"`
  (explicit user instruction). Nothing else is accepted.
- `explanation`: non-empty, states the source of authority and the change.
- Authorized drifts are **applied but recorded** as `authorized_drift: true`
  in `changes.json` and `strength-audit.json` — never silently.
- Missing/invalid authorization + any drift ⇒ **strength-gate revert**. The
  gate cannot be skipped, disabled, or bulk-waived.

## 4. Verdict vocabulary

`none` | `strengthened` | `weakened` | `scope-broadened` | `scope-narrowed` |
`negation-changed` | `causality-changed`. When several fire, the primary
verdict follows this priority: negation > causality > strengthened > weakened
> broadened > narrowed; all fired kinds are listed under `drifts` with
hit-word evidence.

## 5. Honesty boundary (诚实边界)

Cue lexicons are **heuristics**: they cannot prove semantic equivalence and
they have both false positives (e.g. `no` inside a benign phrase) and false
negatives (hedges outside the lexicon, e.g. `to some extent`). Treat every
verdict as a **review trigger**, not a proof. Novel hedge phrasings you meet
in the wild should be checked by hand — and may be added to the lexicon for
the next run.
