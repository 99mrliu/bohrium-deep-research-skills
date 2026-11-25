---
name: contract-mirror-assembler
description: 文献筛选任务的下游交付合规引擎。从 /input/case.json 真实发现 output_contract 并逐字段镜像装配 result.json（含 case_id 回显、全记录覆盖、诚实 partial），配合一次批量相关性判定完成可复核的筛选与排序交付。当任务要求按平台契约交付结构化筛选结果、字段不可缺省、状态必须诚实时使用。
---

# contract-mirror-assembler

## 用途与重心

本 Skill 的重心是**下游交付合规**：评分案例各自声明 `output_contract`，失分常源于结果字段缺失、`case_id` 不回显、或未完成部分被静默吞掉。本 Skill 把"契约发现 → 逐字段装配 → 交付前校验"做成确定性脚本，模型只在一次批量调用中完成逐条相关性判定，其余全部由脚本保证。它不替代判据设计，而是保证任何判据产生的决定都能合规、完整、可核验地交付。

## 适用条件

- 输入为 `/input/case.json`（固定科研案例：研究问题、实际查询输入、有限候选快照，search09 类案例含已标注的合成重复导出夹具）与 `/input/task.md`。
- 候选快照约 9 条真实署名文献，要求**全记录筛选**（每条输入恰好出现在输出分桶中一次）。
- 平台运行契约：在 `/app/work` 下工作，最终结果写入 `/app/output/result.json`，必须含 `case_id` 与 `output_contract` 声明的全部字段；部分完成必须显式标注。

## 运行契约与预算纪律（64 次模型请求 / 900 秒）

按以下四步执行，模型调用 ≤2 次，任何一步失败都要跳到第 4 步交付诚实 partial：

1. **契约发现（脚本，无模型调用）**
   `python3 /skills/weekly-skill/scripts/contract_engine.py inspect --case /input/case.json --task /input/task.md --out /app/work/plan.json`
   读取 plan.json：`contract_fields` 是结果必须逐字段镜像的清单；`record_ids` 是全覆盖基线；`missing_metadata` 直接进入遗漏说明。
2. **批量判定（1 次模型调用）**：对 plan.json 中全部记录一次性输出判定 JSON（每条：`record_id,label∈{keep,pending,exclude},relevance,score∈[0,100],rationale,evidence`＝摘要原文逐字引用），存为 `/app/work/judgments.json`。判据来自案例自带的标注标准；判不了的一律 `pending`，不得编造。9 条规模禁止逐条调用模型。
3. **装配（脚本）**
   `python3 /skills/weekly-skill/scripts/contract_engine.py assemble --case /input/case.json --plan /app/work/plan.json --judgments /app/work/judgments.json --out /app/output/result.json`
   脚本完成：三态分桶、确定性排序（label 层级→分数降序→record_id，同分显式 `tie_group`）、`evidence_records`、遗漏/覆盖说明、契约字段镜像——不可产出的字段以显式 `null` + `status.incomplete` 说明，绝不静默丢弃。
4. **交付校验（脚本）**
   `python3 /skills/weekly-skill/scripts/contract_engine.py validate --case /input/case.json --result /app/output/result.json`
   FAIL 则按打印的问题清单修复后重跑第 3 步；PASS 才视为可交付。时间不足时：省略第 2 步，assemble 会以全 pending 产出诚实 partial，先保底再改进。

## 输入 / 输出

- 输入：`/input/case.json`、`/input/task.md`；中间物：`/app/work/plan.json`、`/app/work/judgments.json`。
- 输出：`/app/output/result.json`，含 `case_id`、`screened_records`（全记录，含 label/relevance/score/rank/rationale/evidence）、`ranking`、`evidence_records`、`summary`、`status{state,completed,incomplete,limits}`、`uncertainty`、`change_records`，以及契约声明的每个其他字段。
- 异常处理：case.json 无法解析 → 脚本以非零退出并说明；契约为空 → `status.limits` 记录；判定文件缺失 → 全 pending 的 partial；字段不可产出 → 显式 null + 原因。不补造文献、不把夹具标注当作预期答案（仅作 provenance 引用）。

## 方法说明与限制

- 排序是确定性的：同一 judgments 必得同一 result.json，可独立复核；k 值与平局处理见 `references/contract-playbook.md`。
- 判定的语义质量取决于第 2 步；本 Skill 保证的是交付合规性、全覆盖与可核验性。
- 局限：契约字段名拼写与平台不一致时按案例原文镜像，不做语义猜测；schema 未知的字段保持 null 而非猜测填充。
- 自查方法：validate PASS 且 `status.state` 与人工预期一致；示例见 `examples/minimal/`（合成示例，不冒充正式案例结果）。
