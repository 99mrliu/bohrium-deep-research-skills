# consistency_rules.md — 一致性检查规则表

`scripts/check_consistency.py` 对 `index.json` 应用的规则。报告按
`(rule, 首个 file, 首个 line)` 排序后编号 ISSUE-001…；存在 error 级问题时退出码为 1。

| 规则 ID | 级别 | 触发条件 | 修复建议 |
|---|---|---|---|
| dangling-float-reference | error | 正文引用点（图/表/Figure/Fig./Table x-y）在全部题注中无同类型同编号题注。编号先做归一化（全角→半角、连字符变体→`-`、`.`→`-`）再比较。 | 核对目标题注编号：题注存在则为笔误，改正文引用；图表已删则删除或改写该引用。 |
| orphan-float | warn | 题注存在，但全文无任何同类型同编号的正文引用点。 | 在正文合适位置补"如图 x-y 所示"式引用，或删除该图表。 |
| duplicate-float-number | error | 同一类型（figure/table）同一编号出现 ≥2 个题注。 | 保留其一，其余按顺序重新编号；用 `impact.py --anchor K:x-y --renumber K:x-y=新编号` 列出全部需同步修改的题注与引用点。 |
| heading-number-gap | error | 同一文件内、同父前缀的同级标题编号不连续（如 1.1 之后直接 1.3）。 | 补齐缺失小节，或重排后续标题编号。 |
| citation-without-entry | error | 正文 `[n]`（含 `[1-3]`、`[1,3]` 展开）的编号在参考文献小节中无对应条目。**参考文献小节缺失时本条整体降级为 warn。** | 补充对应文献条目，或删除/改写该引用点。 |
| orphan-reference-entry | warn | 参考文献条目编号从未被正文引用（仅在找到参考文献小节时启用）。 | 在正文补 `[n]` 引用，或删除该条目。 |
| abbrev-redefined-differently | error | 同一缩略语的全称定义彼此不兼容（两个全称互不包含，排除句首前缀噪声后仍不同）。 | 统一全称，仅保留首次定义点。 |
| duplicate-definition-across-chapters | warn | 同一缩略语同一全称（或互相包含的全称）在 ≥2 个文件中重复定义。 | 仅在首次出现的章节定义，后续章节直接使用缩略语。 |
| term-variant-residue | warn | `--terms` 指定术语组中 >1 个变体在正文出现（参考文献条目行不纳入统计）。报告列出各变体全部位置（每组最多 20 处）。 | 按工单统一为规范写法；文献标题保持原文。 |
| non-thesis-structure | warn | 全语料既无编号标题、也无图表题注、也无 `[n]` 引文：材料可能不是分章节论文结构。 | 结构性规则已降级，仅 float/citation 计数可用；人工确认材料形态后再决定是否适用本 Skill。 |

## 说明

- 题注识别：行首（剥掉 markdown 修饰符 `>*_~\`` 后）以 图/表/Figure/Fig./Table + 编号
  开头的行；其余位置的同模式匹配记为引用点。编号形如 `2-1`、`2.1`、`10-2-3`，
  容忍全角/半角空格（含 U+3000）与连字符变体（U+2010–U+2015、U+2212）。
- 参考文献小节：标题文本为 `参考文献`/`References`/`Bibliography`（大小写不敏感），
  小节止于同级或更高级标题；条目匹配 `[n] …` 或 `n. …` / `n、…`。
- 缩略语定义：`全称（ABBR）` 或 `full name (ABBR)`，ABBR 为 2–12 位大写字母/数字。
  全称聚类时互相包含者视为同一定义（吸收"本工作选用乙烯-…（EVA）"的句首噪声）。
- 本 Skill 只做结构性检查，不判断科学内容正误。
