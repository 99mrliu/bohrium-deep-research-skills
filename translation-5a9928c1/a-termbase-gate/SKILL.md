---
name: termbase-gated-translation
description: 面向科技论文英译中的术语一致性治理技能：先抽取候选术语并锁定术语库（source_term → 唯一强制译法 + 禁用变体），再逐段翻译，最后机器审计译文，术语漂移阻断交付。术语库是可执行工件，而非提示词建议。Use this skill whenever an agent must translate a scientific paper (EN→ZH) and guarantee that every occurrence of a domain term uses one locked rendering.
---

# termbase-gated-translation

## 目的 / Purpose

将术语库从"提示词里的建议"变成**可执行的机器工件**：抽取候选术语 → 锁定唯一译法与禁用变体 → 翻译 → 脚本审计。审计发现任何违规（term-drift / forbidden-variant）即阻断交付，直到修复为止。

## 何时使用 / 何时不用

**使用**：英译中科技论文（标题/摘要/正文/图注/结论）且要求术语全文一致；译文需可审计、可复验。
**不用**：非翻译任务；逐句意译创作类文本；源文无文字层且无法获取（直接报 `unable_to_determine`）；用户明确允许术语自由变体。

## Runtime contract

- 本技能安装在 `/skills/weekly-skill`。
- 输入：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md` 及案例材料（一篇真实论文 PDF，**无预抽取的答案层**——用 `pdftotext` 自行读取）。
- 工作目录：`/app/work`；最终产物放 `/app/output`。
- `/app/output/result.json` 必须包含原始 `case_id` 以及 `output_contract` 声明的**每一个字段**。
- 预算约 64 次模型请求 / 900 秒：**先用 `scripts/make_result.py` 写入占位 result.json**，再就地改进。
- 诚实的状态值：`success` / `partial` / `unable_to_determine` / `refused`。
- 绝不编造缺失内容；无法获得的信息显式标注"未报告 / 无法判断"。

## 工作流 / Workflow

1. **先保底**：运行 `scripts/make_result.py --case /input/case.json --out /app/output/result.json --status partial`，立即产生含 `case_id` 和全部合同字段的 result.json。
2. **识别材料与问题边界**：读 `/input/task.md`，确认论文 PDF 路径、目标语言、交付字段；用 `pdftotext -layout` 抽取文本到 `/app/work/paper.txt`。
3. **抽取候选术语**：`scripts/extract_terms.py --src /app/work/paper.txt --out /app/work/termbase_draft.json`（缩略语定义 + 高频大写/连字符多词短语）。
4. **填写译法并锁定**：agent 为每条候选写译法生成 `translations.json`；运行 `scripts/lock_termbase.py --draft ... --translations ... --out /app/work/termbase.locked.json`。锁定后译法不得再改。
5. **逐段翻译**：按 seg_id/section/source/target 产出 `/app/work/pairs.jsonl`（每行一个 JSON，section ∈ title/abstract/body/caption/conclusion/reference）。
6. **审计闸门**：`scripts/audit_translation.py --termbase termbase.locked.json --pairs pairs.jsonl --out /app/output/audit_report.json --md /app/output/audit_report.md`。**修复每一个违规**后重跑，直到 exit 0 才可定稿。
7. **交付**：`result.json`（status 视审计结果）+ `termbase.locked.json` + `audit_report.json/.md` + `pairs.jsonl`，全部置于 `/app/output`。

## 输出要求 / Output requirements

- `result.json`：含原始 `case_id`、`output_contract` 全部字段、`change_record` 审计轨迹；status 为四类诚实值之一。
- `termbase.locked.json`：每条 entry 有非空 `target`（或经 `_drop` 说明弃用），含 `termbase_sha256`。
- `pairs.jsonl`：字段 `seg_id`、`section`、`source`、`target` 齐全；source 为原文原句，不得改写以规避审计。
- `audit_report.json`：`summary.violations == 0` 方可标 `success`；否则 `partial` 并附违规清单。

## 异常处理 / Exception handling

| 情况 | 处理 |
|---|---|
| PDF 无文字层 | 先 `pdftotext` 试抽；为空则报 `unable_to_determine`，result.json 注明"无文字层"，不编造 |
| 扫描版 PDF | 同上；不臆测 OCR 结果 |
| 公式/表格为图片 | 公式用 LaTeX 占位 `\( ... \)` 保留，表格说明"未报告（图片表格）" |
| 参考文献无法解析 | 参考文献段可原文保留不译，section 标 `reference`，审计默认不强制术语（除非你把它纳入术语库） |
| 中英混排源文 | 中文原样保留；仅对英文源句建 pair 并审计 |
| pdftotext 缺失 | extract_terms.py 会给出明确报错；改用已抽好的 .txt 输入 |

## 自检清单 / Self-check

- [ ] result.json 在动手翻译前已存在且含 case_id + 全部合同字段
- [ ] termbase.locked.json 每条非 drop 条目 target 非空，sha256 存在
- [ ] pairs.jsonl 覆盖 title/abstract/body/caption/conclusion
- [ ] audit_translation.py 最终 exit 0（violations == 0）
- [ ] 未编造任何源文中不存在的内容；缺失处显式标注
- [ ] 所有产物在 /app/output，UTF-8 纯文本
