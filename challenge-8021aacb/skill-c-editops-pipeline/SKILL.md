---
name: editops-change-engineer
description: |
  以可执行编辑操作为交付核心的结构改稿管线（Edit-Op Change Engineering）。重心在下游「改得动」：结构诊断的每一条 finding 都翻译成编辑操作 DSL（move/merge/split/narrow/delete_duplicate/insert_transition/reorder_section/add_limitation），机器校验 op 的块引用与逐字引文，模拟应用器在动笔前生成修订稿骨架与变更日志，最后渲染作者决策表（采纳/部分采纳/驳回逐条勾选）。不产出另起炉灶的全文改写稿。
  触发：task.md 要求结构诊断并交付作者可直接执行的修改方案、保留修改记录时。不触发：语言润色、整篇代写、科学正确性裁决。
  Trigger: actionable structural editing — validated edit operations, simulated application with revised skeleton, author decision sheet. Not for: language polish, full ghostwriting, scientific-correctness adjudication.
---

# 编辑操作工程师（Edit-Op Change Engineer）

## 0. 定位与差异化

本 Skill 的重心是**下游可执行性**：多数结构诊断的失败在交付形态——作者拿到一份原则性意见或一篇重写稿，无从对照、无法圈定执行范围。本管线的交付物是一条**操作链**：

1. 稿件抽成带块 ID（`B001…`）的块库，所有操作按块寻址；
2. 每条 finding 翻译成 DSL 操作（`references/editop_dsl.md` 八种 op）；
3. `editop_check.py` 机器校验引用与逐字引文；
4. `apply_editops.py` 模拟应用，产出 `revised_skeleton.md` + `change_log.json`——作者动笔前就能看到改后结构；
5. `decision_sheet.py` 渲染决策表，作者逐条勾选采纳/部分采纳/驳回。

## 1. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 逐字段抄录到 result.json，不凭题目猜。 |
| 工作目录 | `/app/work`（块库、诊断、ops 中间稿）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）、`editops.json`、`editop_check.json`、`revised_skeleton.md`、`change_log.json`、`decision_sheet.md`、`diagnosis.md`。 |
| 预算 | 64 次模型请求 / 900 秒 / 16384 tokens 每响应。尽早写有效 partial result.json。 |
| Skill 安装路径 | `/skills/weekly-skill`；路径不同时替换命令前缀。 |
| 材料读取 | 读真实文件（PDF 用 `pdftotext -layout` 后按空行切块）；不可读部分如实记 uncertainty。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 契约与块库
读 case.json/task.md；把稿件存为 `/app/work/ms.md` 后：
```
python3 /skills/weekly-skill/scripts/outline_extract.py /app/work/ms.md /app/work/blocks
```
核对 `outline.json`：章节数、标题层级是否与稿件实际相符；乱码/截断记 uncertainty。立即手写 partial result.json（`case_id` + 契约字段占位 + status=partial）。

### 步骤 1 — 六维诊断（finding 层）
在块库上完成六类结构问题诊断（研究问题/章节结构/论证链/段落关系/重复内容/结论边界），每条 finding：`id/dimension/block_id/quote(逐字)/defect_class/severity`。写入 `/app/output/diagnosis.md`（每维一节，含「已检查无重大问题」记录）。

### 步骤 2 — 翻译为编辑操作
按 `references/editop_dsl.md` 与 `references/phasing.md` 把可修复 finding 翻译成 ops，写入 `/app/work/editops.json`：`{"case_id":..., "ops":[...]}`。每条 op 带 `finding_id` 与 `rationale`；相位 P1→P5 排列。无法翻译的 finding 标 `needs_human_confirmation`。

### 步骤 3 — 机器校验
```
python3 /skills/weekly-skill/scripts/editop_check.py /app/work/blocks/blocks.jsonl /app/work/editops.json /app/output/editop_check.json
```
`valid: false` 时按 problems 逐条修复，直到通过（退出码 0）。

### 步骤 4 — 模拟应用
```
python3 /skills/weekly-skill/scripts/apply_editops.py /app/work/blocks/blocks.jsonl /app/work/editops.json /app/output
```
检查 `change_log.json`：`skipped` 的 op 修正或撤下后重跑；最终交付版必须全部 `applied`。人工目检 `revised_skeleton.md` 结构是否合理。

### 步骤 5 — 决策表与收尾
```
python3 /skills/weekly-skill/scripts/decision_sheet.py /app/work/editops.json /app/output/change_log.json /app/output/decision_sheet.md
```
填 result.json 契约字段；`change_record` 逐条列 op 与应用状态；skipped>0 时 status 不得为 `ok`。

## 3. 异常处置

| 情况 | 处置 |
|---|---|
| 稿件无标题结构 | 大纲为空不视为失败：按段落块工作，reorder_section 退化为 move |
| op 引用块不存在 | editop_check 拦截；多为块库版本过期，重新抽取后刷新 ID |
| delete_duplicate 被拒 | 两块非逐字重复：改用 narrow/merge，不得强删 |
| 预算不足 | 优先 P1–P2 结构级 ops + 模拟验证；句级 ops 如实 partial |

## 4. 自查清单

- [ ] editop_check 退出码 0；change_log 全部 applied
- [ ] 每条 op 指回 finding_id，每条可修复 finding 至少一条 op
- [ ] 六维诊断各有条目或 clearance
- [ ] revised_skeleton.md 已目检；decision_sheet.md 可逐条勾选
- [ ] result.json 契约字段齐、status 诚实

## 5. 最小示例

`examples/`：**合成示例**（非正式案例）。`bash examples/run_example.sh` 演示块库抽取 → op 校验（含一条故意坏引用被拦截）→ 模拟应用 → 决策表；`expected/` 为真实跑出的示意输出。
