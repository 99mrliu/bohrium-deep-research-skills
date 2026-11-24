---
name: deliverable-forge
description: 当审查结论（findings）已产出、需要把 result.json 变成可机械验收、可被人复核的正式交付物时使用。对 case.json 的 output_contract 做逐字段机械验收（FAIL 自动降级为诚实 partial），并把 findings 渲染成人读审查报告（Markdown + 自包含 HTML + 严重度看板 + 修改优先级清单）。适用于任何"学术规范与合规检查"案例的收尾交付阶段。
---

# deliverable-forge：下游交付渲染工程

## 1. 用途与新增价值

本 skill 解决交付环节的三个失效点：

1. **交付物缺字段却自称 complete**：`contract_validate.py` 拿 case.json 的
   `output_contract.required_fields` 对 result.json 逐字段机械验收（存在性、非空、status 枚举、
   findings 要素完整性）。验收不通过时**自动改写 result.json**：status 降级为 `partial`
   （原来更差如 `blocked` 则保持）、`change_log` 追加降级记录、`uncertainty` 追加缺失字段清单。
   交付物的 status 从此不是 Agent 自己说了算，而是机械验收说了算。
2. **findings JSON 没人读得动**：`report_render.py` 把 result.json 渲染成 `audit_report.md`
   （人读审查报告：概要、severity×类别交叉表、逐条问题卡片、修改优先级清单）和
   `audit_report.html`（自包含 CSS 单文件，无外部依赖，可直接发给人看）。
3. **复跑一致性无凭据**：`summary_dashboard.py` 产出 `dashboard.json`（severity×type 计数、
   覆盖面记账、待复核清单、top 3 优先行动），既是 Agent 回复用户时的引用底稿，也是两次
   运行之间 diff 的结构化基准。

三个脚本均为纯 Python 3 标准库、确定性输出（无时间戳、无随机数）、单次 <5 秒、缺键不崩。

## 2. 适用条件与不适用情况

**适用**：
- 审查主体已完成（findings 已逐条定位、定级、给建议），进入交付/收尾阶段；
- 需要在交付前自检 result.json 是否满足 output_contract；
- 需要把机器可读 findings 转成人类可复核的报告；
- 需要一份结构化摘要供回复用户或复跑 diff。

**不适用**：
- findings 尚未产出：先用上游 skill（锚定、覆盖账、外部核验、校准）完成审查本体，本 skill
  不替你做审查判断；
- 本 skill 不判定任何问题的真伪与严重度——它只机械验收格式与渲染已有结论。报告中每条
  问题的成立性仍依赖其 `evidence` 与逐字 `quote`；
- 需要联网核验时不要用本 skill（它完全不联网）。

**重要**：本 skill 是交付重心，不改变任务全貌——case.json 声明的**全部审查面**都必须被审查并
进入报告。未覆盖的审查面必须列入 result.json 的 `not_reviewed` 并写明原因，报告概要会如实
展示该清单。

## 3. 运行时契约与路径

- 输入：`/input/case.json`（含 `case_id`、`output_contract.required_fields`）、`/input/task.md`、
  案例材料（通常在 `/input/`）。
- 工作目录：`/app/work`（中间产物、报告草稿）。
- 交付目录：`/app/output`，最终至少含：
  - `result.json`（满足 output_contract，经机械验收 PASS 或已诚实降级）
  - `validation.json`（机械验收明细）
  - `audit_report.md`、`audit_report.html`（人读报告）
  - `dashboard.json`（结构化摘要）
- 脚本安装路径：`/skills/weekly-skill/scripts/`，引用资料在 `/skills/weekly-skill/references/`。
- 所有脚本：`python3 <script> --help` 查看用法；显式输入路径 → 显式输出路径；输入缺键/缺文件
  不崩溃，exit 0 并在输出 JSON 中如实记录。

## 4. 工作流

> 前置：审查本体已完成，findings 已按统一要素写好（见第 5 节与 references/result_schema.md）。

**步骤 1：组装 result.json 全字段草稿**
在 `/app/work/result.json` 写入 `output_contract.required_fields` 声明的每个字段
（通常：`case_id`、`status`、`findings`、`summary`、`sources`、`uncertainty`、`change_log`、
`not_reviewed`）。拿不准的字段写空列表/占位说明也行——验收器会告诉你哪里不行，但诚实写全
比被降级强。写作规范见 `references/result_schema.md` 与 `references/report_style.md`。

**步骤 2：机械验收（缺字段会自动降级）**
```bash
python3 /skills/weekly-skill/scripts/contract_validate.py \
  --case /input/case.json \
  --result /app/work/result.json \
  --out /app/work/validation.json
```
读 `validation.json` 的 `verdict`：
- `PASS` → 进入步骤 4；
- `FAIL` → result.json 已被自动降级为 `partial` 并记账。打开 `validation.json` 的 `details`，
  逐条补齐/修正后**重跑本步骤**（修复后 status 可由你改回 `complete`，再让验收器确认）。

**步骤 3：修复循环**
对每条 FAIL 明细：缺字段补字段、空字段填内容、非法 status/severity 改枚举值、findings 缺
quote 回原文抄逐字摘录。修完重跑步骤 2 直到 `PASS`。若某字段确实无法补齐（如外部核验断网），
保留 `partial`，在 `not_reviewed`/`uncertainty` 写明原因——诚实 partial 优于虚假 complete。

**步骤 4：渲染人读报告**
```bash
python3 /skills/weekly-skill/scripts/report_render.py \
  --result /app/work/result.json \
  --out-md /app/output/audit_report.md \
  --out-html /app/output/audit_report.html
```
目检 `audit_report.md`：每条问题卡片六要素（定位/逐字 quote/依据/严重度/建议/verdict_status）
是否齐全；是否有"建议检查格式是否规范"这类无定位空话（有则回步骤 3 改 findings）。

**步骤 5：生成结构化摘要**
```bash
python3 /skills/weekly-skill/scripts/summary_dashboard.py \
  --result /app/work/result.json \
  --out /app/output/dashboard.json
```
回复用户时直接引用 dashboard 的计数与 `top_actions`；复跑时用 dashboard diff 判断结论是否漂移。

**步骤 6：交付落盘**
把 `result.json`、`validation.json` 一并复制到 `/app/output/`，确认五个交付文件齐全。

## 5. 输出契约

result.json 顶层字段（以 case.json `output_contract.required_fields` 为准，常见如下）：
`case_id`、`status`(complete/partial/blocked)、`summary`、`findings`、`sources`、`uncertainty`、
`change_log`、`not_reviewed`。完整规范见 `references/result_schema.md`。

findings 统一要素（每条）：
- `id`：稳定编号（如 F01）；
- `type`：问题类型细分（如 figure_data_mismatch）；
- `category`（建议）：fact_error / insufficient_evidence / norm_issue / suggestion 四选一；
- `severity`：critical / major / minor / info；
- `location`：`{file, page, section, quote}`，quote 必须是材料原文逐字摘录；
- `evidence`：判定依据（本地规则名 / 规范条款 / 外部来源及检索到的原文）；
- `suggestion`：可执行修改建议（具体动作，禁止空话）；
- `verdict_status`：`确认` 或 `待复核：〈理由〉`。

## 6. 失败模式与止损表

| 失败模式 | 症状 | 止损 |
|---|---|---|
| 缺 contract 字段 | validation.json verdict=FAIL，status 被降为 partial | 读 details 逐字段补齐后重跑验收 |
| findings 缺 quote 或 quote 为空 | FAIL 明细指向具体 finding id | 回原文抄逐字摘录；抄不到就把该条 verdict_status 改 `待复核：` 并给依据 |
| status 自称 complete 但有 not_reviewed | 语义矛盾（验收器不拦，评审会拦） | 有未覆盖审查面时 status 必须 partial |
| 报告出现无定位空话 | 卡片 suggestion 如"建议检查格式" | 按 references/report_style.md 改写为具体动作 |
| 输入文件路径错误/JSON 损坏 | 输出 JSON 含 error 说明，exit 0 | 检查路径与 JSON 合法性，脚本不会替你猜 |
| 渲染后 HTML 打不开 | 浏览器报错 | 用 audit_report.md 交付（内容等价），HTML 为可选增强 |

## 7. 降级策略（honest partial）

- 机械验收 FAIL 时脚本**自动**把 status 降为 `partial`（原为 `blocked` 则保持，不会反向升级），
  并在 `change_log` 与 `uncertainty` 留痕——这条降级是机械保证的，不依赖 Agent 自觉。
- 修复后可把 status 改回 `complete` 并重跑验收；只有 PASS 的 complete 才算数。
- 确实补不齐的（断网、材料缺页、预算耗尽）：保留 partial，`not_reviewed` 列出未覆盖审查面
  及原因，`uncertainty` 列出不确定项。报告与看板会如实呈现这些局限，不得隐藏。

## 8. 预算意识

- 三个脚本共 <1 秒、零模型请求——验收、渲染、摘要全部交给脚本，不要用模型逐字段核对 JSON。
- 先写全字段草稿立刻跑一次 `contract_validate.py`（相当于落盘保底 + 缺口清单），再按
  details 迭代；不要等最后才发现缺字段。
- `dashboard.json` 是回复用户的现成底稿，直接引用，不要让模型重新数 findings。
- 修复循环每轮只改 details 指出的条目，避免整份 result.json 重写浪费 token。
