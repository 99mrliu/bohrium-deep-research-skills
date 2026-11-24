# Genre notes — 基金申请书 vs 论文摘要（译法差异）

Same Chinese sentence often needs different English depending on genre.
Identify the genre from the case materials before rewriting; when unsure,
state the assumption in `notes` and proceed with the more conservative
(paper) register.

## 基金申请书 (grant proposal, e.g. NSFC 面上/青年)

Rhetoric: you are selling *future work*. Promises are expected — but they
must be concrete.

- **Person & tense**: *we will / we aim to / we propose* is natural and
  preferred over "this project intends to" (VS01). Future tense for planned
  work; present perfect/past for 前期工作 ("In preliminary work, we
  prepared …").
- **Significance claims**: allowed, but show-don't-tell. Replace
  "has important scientific significance" with the specific gap closed or
  capability unlocked. Reviewers skim; boilerplate reads as padding.
- **本项目拟…** → *We will…* / *We propose to…* / *The project will
  deliver…* (deliverable as subject is fine).
- **预期成果**: "The expected outcomes will …" is acceptable; better to
  name the deliverable ("a validated structure–activity rule for …").
- **拟解决的关键科学问题**: translate as *key scientific questions*, not
  "key scientific issues to be solved urgently".

## 论文摘要 (journal abstract)

Rhetoric: you are reporting *completed* work. No promises, no sales.

- **Person & tense**: past or present for what was done/found ("We
  prepared …", "The catalyst converts …"); present for established facts.
  "will be investigated" has no place in an abstract.
- **This paper/study**: acceptable as subject with a content verb
  ("This study clarifies …"), never with intention verbs ("this paper
  aims to" is tolerated in some journals but *we* + verb is tighter).
- **Significance**: one closing sentence max, and consequence-shaped:
  "The rule transfers to Cu-SSZ-13 systems." not "has important
  scientific significance and application prospects."
- **本文通过…研究了…** → "We combined X with Y to clarify Z." (active) or
  "Z was clarified by combining X with Y." if the journal bans first
  person.
- No future plans, no 致谢-style courtesy, no "in this paper" openers.

## Shared rules (both genres)

- Numbers, units, years, sample names, citation markers `[n]` are
  **load-bearing**: translation may restructure sentences but may not
  drop, add, round, or re-letter them. `align.py coverage` enforces this
  mechanically; a coverage failure forbids `status=success`.
- Boilerplate (CL01–CL12) is never genre-appropriate.
- 术语 consistency: one Chinese term → one English term throughout
  (脱硝 = denitration *or* deNOx, pick one). If the case ships a
  terminology list, it wins over these defaults.
- When a boilerplate phrase is deleted, record it in the change notes —
  deleting 套话 is an edit, and reviewers of the polish should see it.

## Quick decision table

| 中文 cue | grant English | abstract English |
|---|---|---|
| 本项目拟构建 | We will construct | (n/a — abstract reports done work) |
| 前期研究已制备 | In preliminary work, we prepared | We prepared / A catalyst was prepared |
| 阐明…机制（计划） | We will clarify how … | We clarify / We clarified how … |
| 具有重要的科学意义 | name the gap closed | name the consequence |
| 预期成果将为…提供支撑 | We will deliver X for … | (delete or convert to consequence) |
