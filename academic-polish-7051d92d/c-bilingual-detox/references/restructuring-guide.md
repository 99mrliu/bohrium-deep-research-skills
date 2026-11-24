# Restructuring guide — 中译英主语选择与信息重心重排

The lint (`detox.py`) flags *what* to fix; this guide tells the Agent *how*
to rewrite. Core principle: **translate the information structure, not the
word order.** 中文是话题优先语言（topic–comment，重心在句尾，可无主语）；
英文是主语优先语言（subject–predicate，主语早出现，新信息靠后）。

## 1. Subject selection (主语选择)

For every Chinese sentence ask: *who/what actually does or undergoes the
action?* That entity becomes the English subject — usually NOT the first
noun of the Chinese sentence.

| 中文句式 | 默认英文主语 | 例 |
|---|---|---|
| 本项目/本文拟… | **We** (grant) / verb-first with real object (paper) | 本项目拟构建核壳催化剂 → *We will construct a core-shell catalyst.* |
| 无主句（开发…成为热点） | the driver, not "with…" | 随着标准日益严格，开发…成为热点 → *Stricter standards have made … a priority.* |
| 通过A与B相结合，阐明C | We + verb | 通过原位红外与DFT相结合，阐明机制 → *We will combine in situ IR with DFT to clarify the mechanism.* |
| …具有…结构/性能 | compound modifier, subject = the thing | 构建具有核壳结构的催化剂 → *construct a core-shell catalyst* |
| …的研究表明 / 文献报道… | the finding or the paper | 文献[2]报道的体系易失活 → *The system reported in [2] deactivates readily.* |

Rules of thumb:
1. **People before things**: if the team does it, say *we*. Agent-less
   future passives (will be elucidated) hide the worker — allowed
   occasionally, not three times per paragraph.
2. **Things before placeholders**: avoid opening with *there is / it is
   important / with the development of*. Front the real entity.
3. One sentence = one subject–verb spine. If the Chinese sentence carries
   two spines (流水句), split it.

## 2. Information focus (信息重心)

Chinese puts the new/important information at the end; English wants the
topic early and the comment at the end — but with the **given→new** flow
matching the previous sentence, not the Chinese source.

- 话题照搬 check: if the English subject is a long nominalization
  ("the development of highly efficient and stable low-temperature
  denitration catalysts"), the real news is buried. Unpack it:
  *Efficient, stable low-temperature deNOx catalysts are now a priority.*
- End-focus check: the sentence should end on what the paragraph is about
  (mechanism, number, consequence), not on filler ("in the field of air
  pollution control", "and application prospects").
- 重心后移陷阱: "对NH3吸附活化的调控机制" — the head noun 机制 carries
  seven modifiers. Convert the head to a verb: *how the interface regulates
  NH3 adsorption and activation*.

## 3. 无主句与流水句

- 无主句 in grants → *we* + active verb. In abstracts → passive or
  "this study + verb".
- 流水句 (comma-chained clauses): map each clause to (a) main clause,
  (b) subordinate clause with an explicit logic word, or (c) a new
  sentence. Never join with bare ", so / , which / , and".
- 顿号并列 (A、B、C): keep as a three-part list only if truly parallel;
  otherwise rank them ("mainly A and B").

## 4. Long-sentence splitting (长句切分)

Trigger: draft English sentence > ~35 words, or >1 subordinate clause plus
a participle. Procedure:
1. Underline every verb in the Chinese sentence — each verb is a candidate
   spine.
2. Pick the spine that carries the new information; make it the main clause.
3. Demote background clauses to *because/although/which* phrases or cut
   them into their own sentence.
4. Re-check conservation afterwards (numbers/names must survive the split
   on *some* side of the pair — align by meaning, then re-run coverage).

## 5. Minimal-edit principle

Fix the flagged pattern and its fallout only. Do not rephrase sentences
that pass the lint and read well — every gratuitous rewrite is a new
chance to drift data, citations, or claim strength. After rewriting, the
polished text should score **0 lint hits** (idempotency check) and the
alignment coverage must still be fully conserved.
