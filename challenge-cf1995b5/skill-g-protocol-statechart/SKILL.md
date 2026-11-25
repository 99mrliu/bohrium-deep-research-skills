---
name: protocol-statechart-forge
description: 将真实 organizer canonical case 或兼容别名的实验方案编译为带可观测 QC 守卫、有界重试、显式安全终态和确定故障注入的有限状态图，并审计有限域、候选成本/天数、合同资源、路径成本/时间、可达性与覆盖；适用于实验方案生成与优化的下游可执行过程控制。
---

# Protocol Statechart

把实验方案变成**可判定、可终止、可审计的执行图**。重点不是静态 FMEA、资源预约或输出字段填充，而是：状态如何转移、QC 观测量在哪里记录、失败后重试几次、何时必须停止、每条路径花多少成本/时间、哪些分支没有被任何情景测试。

仿真始终是 `synthetic_what_if`：分支标签和故障注入都是规划假设，绝不是实测实验结果。`complete` 仅指规划工件与机器可检仿真完整，不表示科学有效性、安全性或实验成功。仅当 `case.synthetic is true` 才输出“合成示例输出，非正式测评结果”；真实 canonical case 使用一般的未实测协议/假设仿真提示，不能误标为合成示例。

## 固定运行时约定

- Skill：`/skills/weekly-skill`
- 真实输入：`/input/case.json`、`/input/task.md`；材料发现根目录默认为 `/input`（因此直接位于 `/input` 的 PDF/文本也会读取，递归包含 `/input/materials/`）
- 工作区：`/app/work`
- 输出：`/app/output`
- 唯一需要 agent 编写的文件：`/app/work/protocol_spec.json`
- 编译器：`scripts/protocol_statechart.py`，独立 Python 3 stdlib，无网络、无 `eval`、无第三方依赖

## 端到端工作流

### 1. 立即 bootstrap，先落有效 partial

```sh
python3 /skills/weekly-skill/scripts/protocol_statechart.py bootstrap
```

该命令实际读取 case/task/materials，并以 organizer canonical schema 为主：`parameter_domains` 的 `range`（min/max/step）与 `enum`（values）、`resource_contract.budget_cap/deadline_days`、候选 `version`、`cost_items[].unit_price*quantity/subtotal/total_cost/est_days`。旧 `experimental_domains`、`categorical/allowed`、`budget.max_cost/deadline_minutes`、`amount` 和 `duration_items` 仅作兼容别名；天数绝不反推为候选分钟。它逐候选报告错误而非因普通缺字段崩溃，并合并合同 equipment/reagents/resources 与 `equipment_domain_note` 中用 `JSONDecoder.raw_decode` 提取的设备，去重、报告冲突、列出 unknown ID。它写入：

- `/app/work/bootstrap_audit.json`
- `/app/work/protocol_spec.template.json`
- `/app/output/result.json`（诚实的早期 `partial`）

文本材料按 UTF-8 读取。PDF 仅在已有 `pdftotext` 时抽取；否则记录“未抽取 PDF 文本”的限制，绝不声称已读。缺失/不支持的材料内容不得补造。精确排除 case/task 路径，二者只作输入来源记录，不冒充外部科学证据。可用 `--materials-dir /input/materials` 显式缩小范围；默认 `/input` 缺失时给出无材料假设的警告。

### 2. 只编写一个协议规格

```sh
cp /app/work/protocol_spec.template.json /app/work/protocol_spec.json
```

编辑该 `protocol_spec.json`，一次性写全：

1. 可证伪假设及证伪条件；独立/因/控制变量；校准空白等控制；
2. 材料、设备、操作状态、验收标准、风险与修订、规划证据；资源 ID 必须来自实际合同或其 note 中的 extra equipment，note-only 设备可直接使用，未知资源会 FAIL；
3. 仅来自 case 有限域的参数，不臆造科学参数；
4. 每状态精确 `duration_minutes`/`cost` 和已知资源绑定；
5. 每决策的可观测 `metric/operator/threshold/unit/record` 和显式 `else`；
6. 有界重试的显式 `max_visits`、全局 `global_step_cap`、success/failure 终态；
7. 恰好一个 nominal 及每个故障注入情景的结构化分支序列；
8. 顶层可选 `candidate_revisions`（逐候选实际修订记录）、`uncertainty`、`change_log`、`confirmation_items`（数组或对象），这些作者内容会合并进最终 result，不会被模板默认文本覆盖。

精确 schema、guard 和成本口径见 [references/statechart_contract.md](references/statechart_contract.md)；情景写法见 [references/fault_injection.md](references/fault_injection.md)。没有提供的方法参数、实际性能、库存、报价或批准必须保留为 unknown/confirmation item。

### 3. 编译、验证并仿真

```sh
python3 /skills/weekly-skill/scripts/protocol_statechart.py compile \
  --spec /app/work/protocol_spec.json
```

默认仍读 `/input` 并写 `/app/output`：

- `plan.json`, `plan.md`：完整实验计划与状态化程序；
- `statechart.svg`：UTF-8 XML 文本图；
- `validation.json`：逐项图/域/预算/覆盖检查；
- `simulation.json`：nominal + 每个故障情景的路径、事件、访问数、成本、时间和终止原因；
- `path_report.md`：路径及未覆盖分支摘要；
- `result.json`：`case_id`、全部动态 required fields、status/sources/uncertainty/change_log/confirmation_items；候选修订同时进入 `revised_plan.candidate_revisions`、`candidate_revisions` 和对应审计的 `revision_records`。sources 除输入哈希外还登记 `scientific_plan.planning_evidence` 及已有 locator；spec 仅证明作者来源，不是科学证明。

编译覆盖：唯一 ID/start、非终态出边、显式 else、guard 可观测、目标/状态可达、success/failure 终态、SCC 环出口、每环显式 `max_visits`、有限域 Decimal 算术、资源绑定、科学区块、情景终止、分支覆盖和预算/期限包络。

**检查 `result.status`，不能只看进程返回码。** 结构/仿真验证失败返回 2 且 status=partial；输入不可读会 blocked。返回 0 时，未知 required field 或未测分支仍会令 status=partial。未知动态字段使用显式 `{"partial":true,...}`，不得虚构内容。

## 终止与 worst-case 解释

- 每个有环 SCC 必须有出口，环内每个状态必须有显式访问上界；仿真另有全局步数硬上限。
- 超过 `max_visits`、全局步数上限、缺少下一次注入或遇到未知目标都会产生 `detected_failure`，不会静默截断或自动走 else。
- 显式 failure terminal 是正常的 fail-safe 路径，不是编译器故障。
- 报告分别给 nominal、已给情景逐分量最大值，以及 `Σ(max_visits × state cost/time)` 的保守图上界。后者可包含互斥路径，是安全上界而非声称可达的路径。
- canonical `deadline_days` 以 `保守图分钟 / 1440` 作 elapsed-time 比较；输出明确该换算，并要求确认 booking、排队和日历时间可能更长。预算和货币来自 `resource_contract.budget_cap/currency`。候选 `est_days` 保持天数单位，不与 `duration_items` 的旧分钟字段混用。
- 未覆盖分支逐条列出。缺少情景时不得声称 full coverage；即使覆盖全部标签，也只是注入路径覆盖，不是实验或科学覆盖。

## 失败处理表

| 症状 | 输出/退出语义 | 修订动作 |
|---|---|---|
| case/task 不可读，JSON 无效 | blocked，exit 2；尽量保留 result.json | 修复真实输入；不伪造缺失任务 |
| PDF 无可用文本工具 | partial warning；记录未抽取 | 用已有 PDF 文本工具或请求 UTF-8 文本；不假装已读 |
| 候选 subtotal/总成本不一致、离网格、est_days 超期限/超预算 | bootstrap 审计逐条报错 | 在 spec.candidate_revisions 记录实际修订；不得四舍五入掩盖域错误 |
| spec 资源不在合同/note，或合同资源定义冲突 | compile validation FAIL | 使用实际 ID，解决冲突；不得编造资源 |
| 缺 else、未知目标、不可达状态、缺终态 | result partial，validation fail，exit 2 | 修复图后重新 compile |
| 环无出口或环内缺 max_visits | partial/fail，exit 2 | 增加 fail-safe 出口和有限访问界 |
| 分支没有完整 guard/record | partial/fail，exit 2 | 绑定可观测指标、阈值、单位、记录位置 |
| 情景缺下一次注入/超过访问或步数界 | detected_failure，partial，exit 2 | 修正情景或图；不要把截断写成成功 |
| 有决策标签未被情景选择 | warning，result partial，exit 0 | 添加明确 what-if 情景，或保留覆盖缺口 |
| 未知 required_fields | 字段显式 partial，result partial，exit 0 | 人工补动态映射/内容；不编造 |
| 科学/安全/SOP 信息不足 | 保留 uncertainty + confirmation_items | 交由方法/安全负责人确认，不伪造 complete 科学结论 |

## 900 秒 / 64 次模型调用预算策略

1. **前 10% 预算内**运行 bootstrap，确保已有有效 partial；先读 audit，不重读无关材料。
2. 用一次集中编写完成唯一 spec；优先 nominal、一个可恢复故障、一个持续故障，覆盖所有决策标签。
3. 尽早 compile。先修 structural/scientific schema 错误，再补覆盖；避免逐状态反复调用。
4. 保留足够时间检查 `validation.json`、路径终态、成本/时间包络和 `result.status`。预算耗尽时交付最后有效 partial，不删除错误、不声称 complete。
5. 不为“看起来更完整”虚构额外情景、测量值或科学参数；未测分支比虚假覆盖更有用。

## 安全与专家确认边界

实际湿实验前必须由方法负责人确认标准方法、仪器 SOP、试剂适用性、校准/QC 限值和记录含义；安全负责人确认危害、防护、废液和停止条件；资源负责人确认真实库存、价格、设备可用性与日程。编译通过不授予实验批准，路径成本/时间不是报价或预约。持续 QC 故障、观测缺失或资源安全性不明时，应进入明确 fail-safe/人工确认，而不是绕过 guard。

## 本地合成示例

```sh
/skills/weekly-skill/examples/run_example.sh
```

源码包内可等价运行 `./examples/run_example.sh`。示例是合成水样比色硝酸盐测定，含校准空白、有限温度/时间域、QC 回收率守卫、有界重新空白和持续 QC 失败终态。真实生成的 `examples/output/*` 均标记“合成示例输出，非正式测评结果”；运行证据和负向测试见 [examples/example_run.md](examples/example_run.md)。
