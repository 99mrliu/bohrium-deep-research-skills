---
name: decision-forge-qc
description: 把实验方案比较结果锻造成可独立复核的选择决策包，管「最后一步的可辩护交付」。当已完成候选方案比较、需要产出最终选择结论、淘汰决策日志、权重敏感性分析与自包含报告时触发；尤其针对结论强度靠语气不靠证据、改选方案说不清原因、确认项未完成却写成已执行事实等失败。不适用于上游材料抽取与方案生成（须先读 /input 真实文件完成比较）、不替代实验本身的科学判断（维度分与裁决仍由模型负责）、不处理无比较对象的单方案撰写任务。
---

# decision-forge-qc：选择决策包锻造与过程质量门

## 解决什么问题

方案比较的最后一里路最容易丢分：结论写得斩钉截铁却拿不出淘汰证据；权重稍微
一变首选就翻，但报告里完全没有交代；确认项（安全/伦理/设备可用性/专家）还没
完成，建议已经被写成可执行事实；`result.json` 漏了 `output_contract` 的键。
本 Skill 把比较结果组织成**可独立复核的决策包**（decision_package.json），用
三个确定性脚本守住交付质量：质量门（缺陷拦截）→ 敏感性分析（翻转点）→
自包含报告渲染（HTML+MD），最后由模型写最终 `result.json`。

## 何时使用与不适用

- **使用**：已有 ≥2 个候选方案的比较材料（七类字段、分数、权重、确认项），需要
  产出最终选择/淘汰结论与交付物。
- **不适用**：尚未读取 `/input` 真实材料（先完成上游比较，本 Skill 不替你读论文
  PDF）；单方案撰写无比较对象；需要真实实验室/供应商数据核验（本 Skill 不伪造、
  不联网核验，情景数字就是情景数字）。

## 评测运行时契约（必须遵守）

- Skill 安装于 `/skills/weekly-skill/`；输入为 `/input/case.json` 与
  `/input/task.md` 及 `/input/` 下的科研材料（PDF、前瞻性契约、版本化候选方案、
  rubric/硬阈值）。**必须先读真实文件**，不得凭文件名臆测；案例契约是前瞻性
  情景，不是真实报价/审批，不得说成实测。
- 工作目录 `/app/work`；最终产物放 `/app/output/`，必含 `result.json`：
  `case_id` + `output_contract` **全部原始键**（逐键从 case.json 读取，不漏键
  不臆造），另含诚实 `status`、`sources`、`uncertainty` 与变更记录；partial
  必须写明限制。**尽早落盘部分 result.json，再增量改进**。
- 预算 64 次模型请求 / 900 秒 / 每响应 16384 token：**确定性工作全部交给本
  Skill 的 stdlib 脚本**，模型只做读取、抽取、裁决、文字撰写。

## 分工（模型 vs 脚本）

| 角色 | 职责 |
|------|------|
| 模型 | 读 /input 真实材料；撰写各方案七类字段与条目 id；给维度分并写评分依据；裁决淘汰规则与证据引用；判断确认项状态（confirmed/pending）；撰写 selection.rationale 与 discarded_reasons；最终写 result.json 全文 |
| quality_gate.py | 七类字段完整性、淘汰规则+证据引用存在且可解析、确认项隔离（pending 不得被引用为已确认）、pending ⇒ provisional 降级、result_skeleton 对账 output_contract |
| sensitivity.py | 权重 ±50% 单维扰动 + 等权重档的排名表、rank-flip 报告、解析翻转阈值、robust/sensitive verdict |
| report_render.py | 决策包 + 敏感性结果 → 自包含 report.html + report.md（确定性，无时间戳） |

脚本只做词面/结构/数值检查；语义正确性（评分是否公道、证据是否真的支持淘汰）
仍是模型的责任，脚本拦截不能替代判断。

## 工作流（严格按序）

**步骤 0 — 读输入、尽早落盘**：读 `/input/case.json`、`/input/task.md` 与全部
科研材料（真实打开，不臆测）。立刻在 `/app/output/result.json` 写入部分结果：
`case_id` + `output_contract` 全部键（值暂为 null/占位）+ `status:"partial"` +
`sources` + `uncertainty`。后续每完成一个阶段就增量更新。

**步骤 1 — 汇集 decision_package.json**：在 `/app/work` 把各方案比较材料按
`references/package_schema.json` 汇集为 `decision_package.json`：
- `plans`：候选方案清单（plan_id 唯一）；
- `matrix`：每方案**七类字段**（assumptions/variables/controls/steps/
  parameters/resources/evaluation_criteria），每条目带稳定 id（如 `A-RES-1`）；
- `eliminations`：`[{plan_id, rule, evidence_refs}]`，谁被淘汰、依据哪条规则、
  哪条证据（引用必须指向包内真实存在的条目 id）；
- `scores` / `weights`：维度分与权重（模型裁决并留依据）；
- `confirmations`：确认项显式分 confirmed vs pending（safety/ethics/
  equipment_availability/expert 四类）；
- `selection`：`{selected_plan_id, status, rationale, discarded_reasons}`；
- `result_skeleton`：步骤 0 落盘的骨架原样嵌入。

**步骤 2 — 质量门**：
`python3 /skills/weekly-skill/scripts/quality_gate.py --package /app/work/decision_package.json --case /input/case.json --outdir /app/work`
- exit 0：进入步骤 3；
- exit 3：按 stdout 缺陷清单逐条修复决策包后重跑，**不得**带病交付；
- exit 2：检查路径/JSON 合法性。

**步骤 3 — 敏感性分析**：
`python3 /skills/weekly-skill/scripts/sensitivity.py --package /app/work/decision_package.json --outdir /app/work`
读 verdict：`robust` 直接在 rationale 中声明稳健；`sensitive` 必须在 rationale
与 result.json 的敏感性字段中写明触发权重与翻转阈值（如「reliability 权重降
至 0.307692 以下首选翻转为 P_C」）。

**步骤 4 — 渲染交付报告**：
`python3 /skills/weekly-skill/scripts/report_render.py --package /app/work/decision_package.json --sensitivity /app/work/sensitivity.json --outdir /app/output`
生成 `/app/output/report.html`（自包含，浏览器直接打开目检）与
`/app/output/report.md`。目检：决策日志、确认项分区、敏感性表、页脚案例 id。

**步骤 5 — 写最终 result.json**：模型把 `result_skeleton` 填成全文：`case_id`
+ `output_contract` 全部键的真实内容（选择结论、决策日志、置信度、敏感性
摘要、关键风险等，键名逐字对齐 case.json）+ `status`（final/partial/
provisional）+ `sources` + `uncertainty` + 变更记录。provisional 时写明哪些
确认项 pending、限制是什么。

## 脚本用法与退出码

全部脚本：`python3 <script> --help` 可查用法；纯 Python 3 标准库；确定性输出
（无 wall-clock/随机数；报告默认无时间戳，可用 `--generated-at` 显式传入固定
标注）；同一输入双跑产物逐字节一致。

| 脚本 | 关键参数 | 退出码 |
|------|---------|--------|
| quality_gate.py | `--package`（必需）`--case`（对账 output_contract）`--outdir` `--note`（可选） | 0=通过；2=输入/用法错误；3=质量门拦截（缺陷清单打 stdout，gate_report.json/md 仍写出） |
| sensitivity.py | `--package`（必需）`--outdir` `--note`（可选） | 0=成功（sensitivity.json/md）；2=输入错误；3=前置条件不满足（缺 scores/weights、基线首选并列） |
| report_render.py | `--package`（必需）`--sensitivity` `--outdir` `--generated-at` | 0=成功（report.html/report.md）；2=输入错误；3=渲染必需字段缺失 |
| selfcheck.py | 无参数 | 0=全部断言通过；2=自身用法错误；3=存在失败断言 |

`--note <文本>` 为可选标注参数（quality_gate.py / sensitivity.py）：在 JSON 产物
顶层加 `note` 键、Markdown 产物首行加 `> …` 引用标注；生成示例/演示产物时必须
传入合成示例标注，不传时产物与原行为逐字节一致（report_render.py 的横幅为内置，
无此参数）。

## 输入输出说明

- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`、
  `/input/` 科研材料；中间产物 `/app/work/decision_package.json`（结构见
  `references/package_schema.json`）。
- 输出：`/app/work/gate_report.{json,md}`、`/app/work/sensitivity.{json,md}`、
  `/app/output/report.html`、`/app/output/report.md`、`/app/output/result.json`。

## 七类字段与确认项的落地方式

- 七类字段在 `matrix.<plan_id>.<category>` 下以 `{id, text}` 条目落地；id 全包
  唯一，供淘汰证据引用与报告回查。每组非空由质量门机检（`FIELD_GROUP_EMPTY`）。
- 确认项在 `confirmations` 数组中逐项登记 `{id, kind, item, status, note}`。
  **未经确认的确认项（status=pending）不得写成已确认事实**：其 id 不得出现在
  selection 任何文本中（机检 `SELECTION_CITES_PENDING`）；存在 pending 项时
  `selection.status` 必须为 `provisional`（机检 `SELECTION_NOT_PROVISIONAL`），
  result.json 的 `confidence_level` 相应降级并写明原因。报告第 2 节把
  confirmed/pending 分区渲染，复核者一眼可见。

## 异常分类处置

| 异常 | 处置 |
|------|------|
| 材料缺失（/input 文件找不到、PDF 无法读取、契约缺页） | result.json `status:"partial"`，`uncertainty` 列明缺失项；质量门照跑，缺失导致的字段空缺按缺陷修复或如实降级，不得编造补齐 |
| 确认项未完成 | 结论降级 `provisional`（selection 与 result.json 同步），报告 pending 分区可见；绝不把 pending 写成 confirmed |
| 设备不可得 / 耗材超预算或货期 | 记入该方案 resources 条目；触发硬约束则进 `eliminations`（rule 如 `equipment_unavailable`/`budget_exceeded`，证据引用该条目） |
| 参数窗口冲突 | 记入 parameters 条目并在 rationale/discarded_reasons 说明；构成硬淘汰时进 eliminations |
| 候选方案全部不可行 | `selected_plan_id: null`，status 写明 `infeasible` 情形与理由，eliminations 逐一记录，结果诚实交付不硬选 |
| 无法判断（证据不足打分/裁决） | 对应维度分在 uncertainty 中声明；宁可 provisional 也不编造分数 |
| 运行失败（脚本 exit 2/3、写盘失败） | 按 stderr/缺陷清单修复重跑；最终仍失败则 result.json `status:"partial"` 写明失败点 |

## 自查（selfcheck）

`python3 /skills/weekly-skill/scripts/selfcheck.py`（无参数）对 `examples/` 合成
示例跑全流程并断言：正例 gate exit 0；负例 gate exit 3 且 4 个 booby-trap 缺陷
代码精确命中；sensitivity verdict、触发扰动与翻转阈值同手算值一致；报告关键
内容完整；全流程双跑产物逐字节一致；缺失输入 exit 2。全部通过 exit 0，任一
失败 exit 3 并打印失败项。

## 适用边界

- 敏感性分析是**加权求和模型**下的 one-at-a-time 扰动与解析阈值；非线性聚合、
  维度间交互不在范围内，需要时由模型在 uncertainty 中声明。
- 确认项隔离机检是**按 id 的词面检查**；改写措辞绕过检查属于模型失信，语义层
  自查义务不因机检通过而免除。
- 不生成、不核验真实实验室/供应商数据；情景数字按情景处理。

## 合成示例说明

`examples/` 全部为**合成示例 / SYNTHETIC EXAMPLE**（文件内 notice 字段与报告
横幅双重标注），不是正式案例结果：`case.example.json`（含 5 键 output_contract
示例）、`package_good.json`（3 方案正例）、`package_bad.json`（埋 4 缺陷的
booby-trap 负例，被质量门 exit 3 精确捕获）、`outputs/`（真实跑出的 gate 报告、
sensitivity、report.html/md）、`README.md`（命令序列、浏览器目检方法、敏感性
手算验算）。
