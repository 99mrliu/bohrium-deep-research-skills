# 预算编排规程（Runbook）——开题报告任务的过程质量控制

硬预算：64 次模型请求 / 900 秒墙钟 / 每响应 16384 tokens（含推理）。本规程的第一原则：
**任何时刻 /app/output/result.json 都必须是有效 JSON 且诚实标注完成度**；改进只能在其上叠加，不得回退已交付状态。

## 1. 请求预算分配表（总计 64）

| 阶段 | 请求预算 | 出口门（不满足不得推进） |
|---|---|---|
| 0 契约读取 | 2 | `checkpoint.py init` 完成；output_contract 字段逐字抄录进骨架 |
| 1 材料通读 | ≤10 | 全部材料读过或登记不可读；PDF 已 `pdftotext -layout` 解析；来源清单落 sources |
| 2 要素起草 | ≤20 | 七要素逐一成段，**每完成一要素立即 checkpoint**；论断带来源编号 |
| 3 校验修订 | ≤16 | 引文逐字抽验 ≥30%；指标阈值逐条核对约束（周期/经费/人员） |
| 4 收尾 | 4 | contract_guard 终检；status 与完整度一致；guard_report.json 落盘 |
| 机动余量 | ≥8 | 仅用于熔断后的降级重起草与修复，禁止提前挪用 |

纪律：每三次模型调用至少记一次台账（`budget_ledger.py add`）；起草阶段每完成一个要素必须
`checkpoint.py save`，不得把多个要素攒成一次大改。

## 2. 时间检查点（墙钟，自启动计时）

| 时刻 | 强制条件 |
|---|---|
| T+30s | 步骤 0 必须完成：有效 partial result.json 已落盘 |
| T+120s | result.json 必须可被 `checkpoint.py status` 正常解析，且至少含 sources 初值 |
| T+300s | 材料通读应已结束；未结束则剩余材料按「部分可读」记 uncertainty 并降级 |
| T+600s | **冻结改进**：禁止新起草与重构，只允许填空缺字段、校验、收尾 |
| T+840s | contract_guard 必须已运行；guard_report.json 必须已落盘 |

## 3. 降级阶梯（保序收缩，只降不升需说明理由）

| 层级 | 交付形态 | 触发条件 |
|---|---|---|
| L0 | 完整七要素 + 引文映射 + 校验通过 | 预算与时钟均在表内 |
| L1 | 七要素齐全，缺润色（语言粗糙、格式未统一） | 校验修订预算不足，但要素成稿 |
| L2 | 缺风险细化（risk_register 有骨架但触发信号/备选不全） | 起草预算超支，牺牲风险深度保全文骨架 |
| L3 | 骨架 + 来源映射：七要素标题就位，正文要点化，fact_source_map 完整 | 材料部分不可用或时间过 T+600s 仍缺多要素 |
| L4 | 仅契约骨架：字段就位但多为 null/占位，uncertainty 全量点名 | 材料整体不可用或严重超支 |

降级动作本身必须写入 checkpoint 日志（`--level`）并在 uncertainty 中点名原因；
升级（如 L3→L2）允许，但需在 note 中说明预算依据。

## 4. 超限预警与强制收尾

- `budget_ledger.py report` 判定用量 >80%（已用请求 >51）时输出强制收尾指令并以退出码 2 报警；
- 收到预警或到达 T+600s 后，只允许三个动作：填当前层级可完成的空缺字段、跑 contract_guard、
  按 guard_report 修复可速修项；
- 禁止事项：开新章节、重写已成稿要素、为润色消耗机动余量。

## 5. 收尾协议（固定四步，对应收尾预算 4 请求）

1. `budget_ledger.py report`：确认预算余量，决定是否允许修复轮；
2. `contract_guard.py`：终检；任何 fail 项都会把 result.json 强制回 `status:"partial"` 并在 uncertainty 点名；
3. 可速修项（缺 sources、缺 change_records、单字段空值）就地修复后重跑一次 guard；
4. `checkpoint.py status` 输出最终交付状态，连同 guard_report.json 一并作为交付凭证。

status 判定：契约字段全部非空且七要素检测全过 → 允许 `ok`；否则 `partial`；
材料整体不可用导致只有 L4 骨架 → `partial` 且 uncertainty 首条注明「材料不可用」。
