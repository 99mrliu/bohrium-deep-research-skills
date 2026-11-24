# Register taxonomy — four violation classes (判定边界)

`register.py lint` reports four classes. Every hit is a **candidate**, not a
verdict: the agent must adjudicate in context and record the decision in the
edit's `reason`. This file defines each class and its legitimate-use boundary
so reasonable usage is not damaged (误伤边界).

## 1. colloquial 口语化

**Definition**: words or constructions from spoken/informal registers that
have a precise written counterpart.

- EN: contractions (`doesn't`, `it's`), `a lot of / lots of`, `get + past
  participle` (`get improved`), `just / really / pretty + adj`, `kind of /
  sort of / a bit`, `stuff`.
- ZH: 搞 / 弄 / 挺 / 特别 / 东西 / 事儿.

**Legitimate-use boundary (do NOT "fix")**:
- Inside verbatim quotations, interview data, or the quoted text of a
  reviewer's comment.
- `just` as an adjective (“a just society”) — the linter cannot tell;
  adjudicate.
- `get + PP` rule excludes `got ten/seven...` and similar false positives, but
  new ones exist (“got red-hot”) — adjudicate.
- 挺 in 挺拔/挺进/挺立, 特别 in 特别是/特别地, 弄 in 弄虚作假, 搞 in 搞笑 are
  already excluded by the patterns; other compounds may still false-fire.
- Possessive `'s` (e.g. “the model's accuracy”) is *not* a contraction; the
  pronoun-restricted pattern avoids it.

## 2. promotional 宣传化

**Definition**: evaluative hype claiming superiority without attached,
verifiable evidence.

- EN: `revolutionary / breakthrough / cutting-edge / game-changing /
  world-leading / unprecedented / first-ever / state-of-the-art`.
- ZH: 国际领先 / 世界一流 / 国内首创 / 填补空白 / 颠覆性 / 重大突破 / 遥遥领先.

**Legitimate-use boundary**:
- **grant-proposal / review-response**: emitted as *warnings*, not violations.
  A grant may keep such a claim **only** when bound to evidence in the same or
  an adjacent sentence (citation, metric, preliminary data). Otherwise
  downgrade (“拟开展系统研究”, “处于国内先进水平”).
- `state-of-the-art` referring to *prior work* in a comparative sense
  (“state-of-the-art baselines [3-5]”) is conventional and may stay.
- Quoting an award/review (“received the X breakthrough award”) may stay.

## 3. absolute 绝对化

**Definition**: unbounded claims that no finite evidence can support.

- EN: `always / never / completely|totally|entirely prove|show|eliminate /
  guarantee`.
- ZH: 彻底(解决|消除) / 完全解决 / 从根本上解决 / 绝不(会) / 必将 / 百分百.

**Legitimate-use boundary**:
- Mathematical/logical statements with a proof in the text (“never exceeds the
  bound, by construction; see Theorem 2”) may stay — cite the proof in the
  adjudication note.
- Definitions and scope statements (“we never use test labels”) are facts
  about the method, not claims about the world.
- When an absolute claim is weakened, the edit `reason` must say the strength
  changed (see SKILL.md honesty boundary).

## 4. person-misuse 人称误用

**Definition**: person/address forms violating the genre convention.

- EN abstracts: `I` (use *we* / *this paper*), `you/your` (reader address).
- ZH: standalone 我 (use 本文/本项目/本研究); 我们 is a *warning* in
  journal-abstract and thesis, acceptable in grant and review-response.
- review-response: missing courteous first-person-plural framing
  (“We thank … / We have revised …”) is itself a violation; combative
  second person (“you are wrong”, “the reviewer is wrong”, “obviously”)
  is a violation.

**Legitimate-use boundary**:
- 致谢 / acknowledgements sections are personal: 我/我们 are fine there.
  Exclude such sections before linting.
- Quoted reviewer comments may contain any person form — quoted text is data,
  not the author's register.
- Single-author dissertations at venues that mandate “I” exist; if the task
  states such a convention, the task wins over these defaults.
- `I` as a Roman numeral (Section I) is a false positive — adjudicate.

## Severity model

- `violation`: counted in `total_violations`; the scorecard gate compares
  these before/after.
- `warning`: listed but not counted (promotional words in grant proposals,
  我们 in journal-abstract/thesis). Warnings still need an agent decision:
  keep-with-evidence or downgrade.
