# Terminology method — 术语规则

These rules govern how a termbase is curated and locked in this bundle
(术语资产工程). The enforcement scripts check the mechanical consequences;
the judgments below are made by the agent.

## 1. One term, one translation (术语锁定)

Within one case, each source term has **exactly one** target rendering,
recorded in `glossary.json` as `{source, target}`. The lock applies to every
register: abstract, body, figure/table captions, footnotes, and appendix.

- Choose the target by domain convention (standard textbooks, GB/ISO Chinese
  terminology, prevailing journal usage), not by sentence-level euphony.
- If two renderings are both defensible, pick one as `target` and list the
  other(s) in `forbidden_variants` — this converts a judgment call into a
  machine-checkable rule.
- Varying a locked term "for style" is a defect, not a flourish.
  `check_consistency.py` treats any `forbidden_variant` hit as an error with
  line numbers.
- Synonymous *source* forms (e.g. "photovoltaic cell" vs "solar cell" used as
  true synonyms) may share one target; make each a separate glossary entry
  with a `note` pointing at the other, so both are checked.

## 2. Discipline disambiguation (学科消歧)

The same surface form means different things in different disciplines. Decide
the sense from the actual source context and **record the chosen discipline in
the glossary `discipline` field** — this is what makes the choice auditable.

| source | sense A | sense B |
|---|---|---|
| cell | 细胞 (biology) | 电池 (electrochemistry / photovoltaics) |
| bond | 化学键 (chemistry) | 债券 (finance) |
| charge | 电荷 (physics) | 费用 / 指控 (finance / law) |
| deposition | 沉积 (materials) | 证词 (law) |
| stress | 应力 (mechanics) | 心理压力 (psychology) |

- Put the *rejected* sense's standard rendering into `forbidden_variants`
  (e.g. for a photovoltaics paper, entry `cell → 电池` gets
  `forbidden_variants: ["细胞"]`). A stray rejected-sense rendering then fails
  the consistency check instead of silently shipping.
- If the genuinely intended sense is unclear from the source, do NOT silently
  pick: mark the entry `note` and the case uncertainty log with `[待确认]`
  and state the working choice explicitly.

## 3. First-mention convention (首现约定)

For terms with an established English name and abbreviation:

1. **First occurrence in the target text:**
   `中文全称（English full name, ABBR）`
   e.g. `光电转换效率（power conversion efficiency, PCE）`
2. **Thereafter:** the abbreviation (PCE) or the locked short Chinese form —
   whichever the glossary entry locks; do not alternate.

Store the exact first-mention string in the entry's `first_mention` field;
`check_consistency.py` warns if that exact form never appears in the
translation. For ZH→EN cases, mirror the convention:
`English full name (中文全称, ABBR)` where the case requires Chinese retention.

## 4. Source-internal inconsistency (源文本不一致)

Sources are imperfect. If the source itself uses two forms for one concept
(e.g. "spin coating" vs "spin-coating", "PSC" defined but never reused):

- Pick the dominant/most formal form as the glossary `source` key; other
  surface forms become additional entries locked to the same `target` if they
  appear often enough to matter.
- Record the discrepancy with `[待确认]` in the entry `note` AND in the case
  uncertainty log (`result.json` → uncertainty, and `change_log.md`).
- **Never silently normalize** and never silently pick between conflicting
  source definitions (e.g. two different expansion of one acronym). When in
  doubt, keep the source's own first definition and flag it `[待确认]`.

## 5. Captions and appendix inherit the lock (图注与附录继承锁定)

Captions, table headers, figure labels, and appendices are the classic
drift sites because they are translated last and in isolation. Rules:

- The lock applies there with **no shorthand exceptions**: a caption may not
  abbreviate a Chinese term (光电转换效率 → 转换效率) unless that short form is
  itself the locked `target`.
- Section-wise checking enforces this: `check_consistency.py` requires the
  locked target to appear in **every section** (heading-delimited or
  blank-line block) where the source term appears — a caption-only miss is a
  `section_lock_violation` error.
- Translate captions/appendix with the glossary open, and re-run the check
  after adding them; do not treat them as a separate mini-project.

## 6. Workflow hooks (one line each)

- Extraction: `extract_terms.py` proposes; the agent disposes (drafts are
  candidates, not truth).
- Curation gate: `lint_glossary.py` exit 0 before translating.
- Enforcement gate: `check_consistency.py` exit 0 before delivery.
- Numbers/facts, alignment, and boundary records are handled by the case's
  other machinery — this method file governs terms only.
