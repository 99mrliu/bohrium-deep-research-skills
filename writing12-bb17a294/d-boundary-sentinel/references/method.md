# Boundary rules — 语义边界与引用保留方法

（合成示例与本方法文档配套；适用于 EN→ZH 学术翻译。）

## 1. The three laws of the boundary (边界三律)

1. **Never drop a qualifier.** Every negation, hedge, quantifier and
   attribution present in the source must have an explicit counterpart in
   the translation. If no natural Chinese rendering exists, use the closest
   one and record the deviation in `change_log.md`.
2. **Never shift claim strength.** Do not strengthen (suggest → 证明) or
   weaken (demonstrate → 可能与……有关) a claim. Causal-strength classes:
   - **strong**: demonstrate / prove / confirm / establish → 证明 / 证实 /
     表明 / 显示 / 确立
   - **moderate**: show / indicate → 表明 / 显示 / 提示
   - **weak**: is associated with / correlates with / is consistent with →
     与……相关 / 与……一致 / 符合 / 提示
3. **Never add what the author did not say.** No new claims, no new
   citations, no "first ever / breakthrough" (首次/突破性) wording unless
   the source says it. Unavoidable clarifications become **bracketed
   translator notes**: `[译者注: …]`, never silent insertions.

## 2. EN→ZH hedge mapping table (语气词映射表)

| English hedge | class | accepted Chinese renderings |
|---|---|---|
| may / might / could | possibility | 可能 / 或 / 或许 / 也许 / 有望 |
| suggest(s) | suggestion | 提示 / 表明(初步) / 可能 / 暗示 |
| appear(s) / seem(s) | appearance | 似乎 / 看来 / 貌似 / 显得 |
| approximately / about / around | approximation | 约 / 大约 / 左右 / 近 |
| up to | up_to | 至多 / 高达(保留上限) / 不超过 / 最高 |
| at least | at_least | 至少 / 不少于 / 不低于 |
| at most | at_most | 至多 / 最多 / 不超过 |
| potentially | potentially | 潜在地 / 可能 / 有望 |
| likely | likely | 很可能 / 可能 / 有望 |
| unlikely | unlikely | 不太可能 / 不大可能 / 未必 |
| only | restriction | 仅 / 只 / 唯有 / 仅限 |

Deviations from this table are allowed only when the accepted renderings are
grammatically impossible in context; every deviation MUST be recorded in
`change_log.md` (source sentence, chosen rendering, reason) and, when the
deviation affects meaning, queued as `[待确认]`.

Negations (no/not/never/none/neither/fails to/without) must map to explicit
Chinese negation: 不 / 无 / 没有 / 未 / 并非 / 不能 / 缺乏 / 而非. A double
negation stays a double negation (or is flagged `[待确认]`).

## 3. Citations when translating (引用处理)

- **Numbered style** (`[12]`, `[3-5]`): keep the marker **verbatim** —
  same brackets, same numbers, same range form. Reference list keeps the
  original numbering and original order; titles may be translated but
  authors, year, venue and identifier stay.
- **Author–year style** (`(Smith, 2020)`, `Smith et al. (2021)`): keep the
  author surname and the year. `et al.` may be kept as `et al.` or rendered
  `等` — pick one convention per document and note it in `change_log.md`.
- **Never**: renumber citations to "fit" the translation, drop markers that
  look redundant, merge two references, or add a reference the source does
  not contain. `citation_check.py` enforces: every in-text marker preserved,
  every reference entry present exactly once, in original order, no
  fabricated entries.
- Mixed or unusual styles (superscripts, footnotes) → preserve as-is and
  flag `[待确认]` for human confirmation.

## 4. The [待确认] human-confirmation workflow

1. A finding (script error/warning, agent doubt, ambiguous source) that
   cannot be resolved faithfully is written as a `[待确认]` item:
   `[待确认] <source sentence id> — <issue> — <provisional decision>`.
2. Every `[待确认]` item appears in THREE places: the deliverable itself
   (inline, at the relevant location), `change_log.md`, and the
   `uncertainty` field of `result.json`.
3. Resolved findings are also logged in `change_log.md` with their verdict
   and fix, so the audit trail is complete (every resolved AND every
   acknowledged finding).
4. Never silently drop a finding. An acknowledged finding is a decision;
   a dropped finding is a defect.

## 5. Limits of heuristic detection

`extract_markers.py`, `audit_boundary.py` and `citation_check.py` are
pure-regex, **recall-oriented** heuristics: they flag candidates for human
check; they do not prove that a marker is present, absent, or correctly
translated. Known limits: sentence splitting can break on unusual
abbreviations/decimals; substring matching can over-accept (e.g. 或 inside
或者) or under-accept paraphrases; multi-reference clusters and exotic names
may misparse; alignment by order with ±1 tolerance can misalign heavily
restructured translations. The agent (and ultimately the human) resolves all
flags. When a heuristic misfires, record it in `change_log.md` and decide
manually — do not "fix" the source to please the tool.

## 6. One-line mentions (out of scope here)

- **Numbers/units**: re-verify every numeral against the source; log a one-line
  confirmation in `change_log.md`.
- **Terminology**: keep one consistent Chinese term per concept; log choices
  in one line (no termbase machinery in this bundle).
- **Alignment**: scripts align by order with ±1 tolerance; note any manual
  re-alignment in one line.
