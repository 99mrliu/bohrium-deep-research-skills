---
name: resource-constraint-oracle
description: 资源约束与排期可行性裁决 Skill。用于比较候选实验方案时，把「理论上可行」与「本实验室现在可做」分开裁决：核对设备能力与档期、耗材预算与货期、参数窗口三方冲突（方案要求 vs 设备极限 vs 契约/文献域）、人员技能与时间窗、场地与安全审批，并给出逐方案 feasible_now / feasible_after(日期) / infeasible(原因) 结论与最早可启动时间线。当输入给出前瞻性资源/价格/预订契约、有限参数域与多份候选方案、且失败风险是照搬文献流程不核对现状约束时触发。不适用于无资源契约/无档期货期信息的纯文献综述，也不替代安全/伦理的专业审批结论；数值优化与实验设计本身不在范围内。
---

# resource-constraint-oracle — 资源约束与排期可行性裁决

## 解决什么问题

候选实验方案常见的失败：把文献通用流程整段搬来，却不核对本实验室设备是否具备、
耗材是否在预算与货期内、设备档期/耗材货期/场地与安全审批/人员技能与时间窗口。
本 Skill 做**约束满足裁决 + 最早可启动排期**，逐方案区分：

- **理论上可行**：参数窗口落在 设备极限 ∩ 契约给定域 内，文献区间支持；
- **本实验室现在可做**：`feasible_now`（立即可启动）或 `feasible_after(日期)`（等待档期/到货/审批后可启动）且排期不超 deadline；
- **现状不可做**：`infeasible(具体原因)`，并给出 relax_hints（解除条件）。

## 何时使用 / 不适用

- 使用：/input 中有资源/价格/预订契约（设备档期表、耗材货期表、参数域）、多份候选方案、deadline/预算等硬约束，需要回答"哪个方案现在能做、何时能做、为什么别的不能做"。
- 不适用：无任何资源约束信息的纯理论比较；需要真实供应商询价（契约是组织方前瞻性给定情景，**不得**把情景数字说成实测或真实报价）；安全/伦理审批的专业判断本身（本 Skill 只核对审批状态字段）。

## 评测运行时契约（事实）

- Skill 被安装到 `/skills/weekly-skill/`，评测器用官方 DeepSeek Harness 对固定案例逐案运行。
- 输入 `/input/case.json`、`/input/task.md` 及科研材料（真实论文 PDF、前瞻性资源/价格/预订契约、版本化候选方案、有限参数域、rubric/硬阈值）。**必须先读真实文件**，不得凭文件名臆测；PDF 无预抽取答案层。
- 案例是组织方构造的规划情景：契约数字不是真实实验室/供应商报价，不得说成实测。
- 工作目录 `/app/work`；最终结果放 `/app/output/`，必含 `result.json`：`case_id` + `output_contract` 全部原始字段（逐键从 case.json 读取，不漏键不臆造），含诚实 `status`、`sources`、`uncertainty`、变更记录；partial 写明限制。**尽早落盘部分结果，再增量改进**。
- 预算：64 次模型请求、900 秒、每响应 16384 token。**确定性工作全部交给本目录 stdlib 脚本**；模型只做读取、抽取、裁决、文字撰写。
- 结果内容含七类字段——假设、变量、对照、步骤、参数、资源、判读标准——加依据与风险、确认项（安全/伦理/设备可用性/专家确认）；未经确认的建议不得写成可执行事实。

## 分工

- **模型**：读 /input 真实文件 → 抽取资源供给事实（设备能力/档期窗口/耗材货期/审批状态/人员技能）与每方案需求（所需设备/耗材/参数窗口/技能/时长），填入 facts JSON，**每条事实挂 source**（契约文件#位置 / 方案文件#段落）；最后依据脚本报告撰写 result.json 文字。
- **脚本**（纯 stdlib、确定性、退出码 0/2/3）：做全部约束满足与排期算术——区间求交、日期推算、档期扫描、甘特排期、质量门拦截。模型不做算术。

## 工作流（严格按序）

### 步骤 0：读 /input，尽早落盘部分 result.json

1. 读 `/input/case.json` 与 `/input/task.md`：提取 `case_id`、`output_contract` 全部键、reference_date（排期基准日，**用 case 给定值，禁用系统时钟**）、deadline、budget、contract_domain（有限参数域）。
2. 立刻在 `/app/output/result.json` 写入部分结果：`case_id` + output_contract 全部键（值先填 null/占位）、`status: "partial"`、`sources`（已读文件清单）、`uncertainty`、变更记录首条。之后每完成一步增量更新。

### 步骤 1：模型填 facts JSON

按 `references/facts_schema.json` 填写 `/app/work/facts.json`：

- `resources_available`：equipment（id/capabilities 数值窗口/booked_windows 半开区间/available）、consumables（in_stock/lead_time_days/unit_cost/orderable）、approvals（status: granted/pending/rejected/not_started + expected_date）、personnel（skills/available_windows）。全部挂 source。
- `plan_requirements`：每方案 equipment_needs（equipment_id/stage/duration_days/[earliest_use, latest_use)/required_capabilities）、consumable_needs（quantity/needed_by）、parameter_windows（方案要求窗口）、skill_needs、approval_needs、prep_days。
- 拿不准的字段：宁缺毋滥并记入 uncertainty；**不得编造**档期/货期数字。契约未给的窗口不要在 facts 里虚构（脚本按无界处理并记入 notes/假设）。

### 步骤 2：constraints.py 约束满足裁决

```bash
python3 /skills/weekly-skill/scripts/constraints.py \
  --facts /app/work/facts.json --case /input/case.json --out-dir /app/work/constraints
```

对每方案逐项检查：设备存在且能力覆盖且档期窗口与需求相交；耗材可得且货期 ≤ needed_by、总价 ≤ 预算；参数窗口 ⊆ 设备极限 ∩ 契约域（冲突写清具体区间）；技能 ⊆ 人员技能集；审批状态。输出 `constraints_report.json/.md`：每方案 verdict + violations（{type, detail, blocking}）。任一 blocking → 该方案 infeasible；全部 infeasible → exit 3 并输出 relax_hints。

### 步骤 3：window_check.py + timeline.py

```bash
python3 /skills/weekly-skill/scripts/window_check.py \
  --facts /app/work/facts.json --case /input/case.json --out-dir /app/work/windows
python3 /skills/weekly-skill/scripts/timeline.py \
  --facts /app/work/facts.json --case /input/case.json \
  --constraints /app/work/constraints/constraints_report.json --out-dir /app/work/timeline
```

- `window_check.py`：参数窗口三方对照（方案 × 设备 × 契约域），输出交集矩阵 `window_report.json/.md`；**空交集 → exit 3**（报告仍写出）。
- `timeline.py`：资源日历驱动的串行排期（采购等待→准备→执行→表征排队），设备档期/耗材到货/人员窗口冲突时顺延（上限 365 天，超出判 schedule_infeasible）；输出每方案 earliest_start、first_execution_start、earliest_finish、关键等待项、`gantt.md`；超 case deadline → 标记 past_deadline。constraints 判 infeasible 的方案自动跳过。

### 步骤 4：模型写最终 result.json

依据三份脚本报告撰写（文字由模型写，数字一律引用脚本输出，不得手算改写）：

- **七类字段**：假设（含"契约数字为前瞻情景、非实测"）、变量、对照、步骤、参数（引用 window_report 的允许区间）、资源（引用 facts + constraints 裁决）、判读标准。
- **逐方案 feasibility verdict**：必须写明 `feasible_now` / `feasible_after(YYYY-MM-DD 或条件)` / `infeasible(原因)`，并显式区分"理论上可行"（窗口相容、文献支持）与"本实验室现在可做"（现状约束满足且 earliest_finish ≤ deadline）。feasible_after 但 past_deadline 的方案必须如实标注"现在赶不上"。
- 依据与风险：每条 verdict 引用违例/注记清单；时间线引用 gantt 与关键等待项。
- 确认项：pending 审批、无预计日期的等待项、unbounded 参数、人员窗口假设等——**未经确认的建议不得写成可执行事实**。
- `status`：complete / partial（写明限制）；`sources`；`uncertainty`；变更记录追加。
- 把 constraints_report、window_report、timeline_report、gantt 一并拷入 /app/output/（或引用其 work 路径）。

## 脚本用法与退出码

| 脚本 | 用途 | 0 | 3 | 2 |
| --- | --- | --- | --- | --- |
| constraints.py | 约束满足裁决 | ≥1 方案可行 | 全部 infeasible（输出 relax_hints） | 输入/用法错误 |
| window_check.py | 参数窗口三方对照 | 无空交集 | 存在空交集 | 同上 |
| timeline.py | 最早可启动排期 | ≥1 方案排出 | 无可排方案 | 同上 |
| selfcheck.py | bundle 自查 | 全部通过 | 有失败项（清单写 stdout） | 同上 |

所有脚本支持 `--help`；仅用 Python 3 标准库；同一输入双跑产物逐字节一致。

## 输入输出说明

- 输入：facts JSON（模型填，schema 见 `references/facts_schema.json`）、case JSON（case_id/reference_date/deadline/budget_cny/contract_domain）。
- 日期全部 ISO 字符串；**所有区间为半开 [start, end)**；数值窗口 {min, max}，缺省端无界。
- 输出：constraints_report.json/.md、window_report.json/.md、timeline_report.json、gantt.md。

## 异常分类处置

| 异常 | 表现 | 处置 |
| --- | --- | --- |
| 设备不可得 | equipment_missing / unavailable / capability_insufficient | 该方案 blocking；relax_hint：租用/外协/替代设备/收缩窗口 |
| 耗材超预算/货期 | budget_exceeded / consumable_lead_time_exceeded / not_obtainable | blocking；hint：现货供应商/增预算/替代料/顺延需批准 |
| 参数窗口冲突 | parameter_window_conflict；window_check exit 3 | blocking；写清空交集或超出的具体区间；hint：收缩/平移窗口或向契约方申请放宽参数域 |
| 设备档期冲突 | equipment_booking_conflict（窗口内无空档）或 feasible_after（稍后有档） | 前者 blocking，后者写明可启动日期与关键等待项 |
| 全部方案不可行 | constraints exit 3 | **诚实报告**，输出 relax_hints（每个 blocking 的解除条件），不得硬推方案；result.json status=complete 但结论为"现状均不可行+解除条件" |
| 材料缺失/无法判断 | /input 缺契约或方案、PDF 无法抽取 | facts 缺项，uncertainty 写明；result.json status=partial 写明限制 |
| 运行失败 | 脚本 exit 2 | 检查 JSON 格式与字段，修复后重跑；不得绕过脚本手填数字 |

## 自查（selfcheck）

```bash
python3 /skills/weekly-skill/scripts/selfcheck.py
```

自动验证：正例（P1 feasible_now / P2 feasible_after(2026-01-31) / P3 infeasible-空交集）exit 0 命中、window_check 对空交集 exit 3 命中、负例（设备档期全占、耗材货期超 deadline、参数空交集、全部不可行）exit 3 精确命中、relax_hints 覆盖全部 blocking、双跑字节一致。任何一项失败 exit 3 并列缺陷清单。

## 适用边界

- 只做"现状约束满足 + 排期"裁决，不做方案的科学优劣评分（那是评审模型的判断，本 Skill 提供事实底座）。
- 日期粒度为天；不建模小时级机时、并行班组、设备切换准备时间（可在 facts 的 prep_days 中近似）。
- 预算检查按"单方案耗材总价 vs 预算"口径；多方案共享预算的联合优化不在范围。
- 审批只核对契约中的状态字段，不出具安全/伦理结论。

## 合成示例说明

`examples/` 全部输入输出均为**合成示例 / SYNTHETIC EXAMPLE**（虚构契约、虚构方案、虚构数字），
不得冒充正式案例结果。含：P1 全满足（feasible_now）、P2 设备档期冲突（feasible_after(2026-01-31)，README 有手算验算）、P3 参数空交集（infeasible 负例，被 window_check exit 3 与 constraints blocking 精确捕获）、all_infeasible 变体（演示 exit 3 + relax_hints）。命令序列见 `examples/README.md`。
