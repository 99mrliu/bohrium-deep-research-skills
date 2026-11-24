# 对账规则全集与判据（reconciliation_rules）

`scripts/case_reconcile.py reconcile` 执行的检查分为 A–E 五类。每条检查输出
`check_id / category / status(PASS|FAIL|WARN) / candidate_version / description / evidence`。
**FAIL = 修订靶点（必须处置），WARN = 待确认项（进 confirmation_items 候选），PASS = 留档证据。**

## A. cost_arithmetic — 成本算术

| 规则 | 判据 | 状态 |
|---|---|---|
| A-row | 对每个 cost_item：`unit_price × quantity == subtotal`（容差 1e-6） | 不等 → FAIL，evidence 给出 `up×q=expect ≠ subtotal st（差额 st-expect）` |
| A-total | `Σ subtotal == total_cost` | 不等 → FAIL，evidence 给出逐行相加算式与差额；候选缺 total_cost → WARN |
| A 字段缺失 | unit_price/quantity/subtotal 任一非数值 | WARN（无法机械校验，人工核） |

## B. parameter_domain — 参数 vs 有限参数域

| 规则 | 判据 | 状态 |
|---|---|---|
| B-enum | enum 域：参数每个取值 ∈ `values` | 越域 → FAIL |
| B-range | range 域：`min ≤ v ≤ max` | 越界 → FAIL |
| B-step | range 域且定义了 step：`(v-min)/step` 为整数 | 非整数 → WARN（在界内但不在网格上） |
| B-未登记 | 候选参数在 parameter_domains 中无对应条目 | WARN（合法性无机械依据，人工确认） |
| B-非数值 | 参数值非数值 | WARN（跳过域校验） |

列表型参数（如温度梯度 `[80,95,110,...]`）逐元素校验。

## C. contract_coverage — 设备/试剂引用覆盖

| 规则 | 判据 | 状态 |
|---|---|---|
| C-item | cost_items[].item 能匹配已知条目（合同 equipment + reagents + **文本内嵌补充设备**）的 id 或名称（双向子串） | 匹配 → PASS（内嵌来源在证据中注明 origin=text_embedded）；无匹配 → FAIL |
| C-summary | 候选 summary 中出现的 `EQ-*`/`RE-*` 记号能在已知条目中定位 | 不能 → FAIL |

匹配表由 extract 阶段的统一设备表 + 合同试剂清单构成；equipment_domain_note 中解析出的
内嵌设备与 equipment 列表**同等地位**参与匹配。

## D. budget_deadline — 预算 / 周期 / 预约吞吐

| 规则 | 判据 | 状态 |
|---|---|---|
| D-budget | `total_cost ≤ budget_cap` | 超出 → FAIL（给出超支额）；通过 → PASS（给出余量） |
| D-deadline | `est_days ≤ deadline_days` | 超出 → FAIL（给出超出天数） |
| D-booking-cap | 成本行匹配到设备时：`quantity(小时) ≤ slots_per_week × slot_hours × window_days/7` | 超出 → FAIL（预约吞吐不足） |
| D-booking-window | `est_days ≤ 所用设备的 booking.window_days` | 超出 → WARN（排期可行性存疑） |

注意：预算与价格是**前瞻约定**（见 resource_contract.disclaimer），即使 PASS 也不得写成
"已确认报价/已确认排期"。

## E. domain_basis — 参数域依据可定位性

| 规则 | 判据 | 状态 |
|---|---|---|
| E-source | `parameter_domains.*.source`（`case:` 前缀路径）能在 case.json 内解析定位 | 失败 → WARN（依据需人工确认或补材料）；成功 → PASS |
| E-basis-missing | basis 或 source 字段缺失 | WARN |
| E-literature | basis 含"文献"但 `source.paper_pdf` 缺失 | WARN |

`case:` 路径解析支持点号键与 `[n]` 列表索引（如 `case:resource_contract.equipment[0]`）。

## 处置优先级

1. A/C/D 类 FAIL：直接改写成本表、替换合同外条目、压缩排期，重算后在 change_log 记录 check_id。
2. B 类 FAIL：把越域值裁剪/替换到域内最近合法点，注明依据（basis）。
3. 全部 WARN：逐条决定"消解（找到依据）"或"进 confirmation_items"。
4. 修订后的方案必须重新满足全部 A–E 检查（可用同一脚本对新方案构造的临时 case 复跑校验）。
