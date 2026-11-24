# 分阶段交付协议（Delivery Protocol）

本文档是 incremental-delivery-governor 的方法论依据：先合法、再完整、随时可断。

## 一、T0 骨架先行

时间零点（T0）的第一件事不是读数据，而是把合法性钉在磁盘上：

```
python3 stagegate.py init --case /input/case.json --output /app/output
```

骨架落盘之后，即使立即被切断，交付目录里也已经有一份合法的
`in_progress` result.json：case_id 正确、契约字段齐全（null + 理由）、
provenance 含输入 sha256。后续所有工作都只是**改进**这份交付物，而不是
从零创建它。已存在的 result.json 受保护（init 拒绝覆盖，除非 --force），
重复执行不会丢失进度。

## 二、典型阶段序列与预算

以单个案例 900 秒 / 64 次模型请求为基准：

| 阶段 | 目标 | 时间 | 请求 | 出口动作 |
| --- | --- | --- | --- | --- |
| 0 骨架 | result.json 骨架 + budget_plan.md | ≤ 60 s | 第 0 个请求内 | checkpoint（genesis） |
| 1 摄入与画像 | 读数据字典、行数、缺失与类型画像、输入 sha256 | ≤ 90 s | ≤ 8 | set 画像类字段；checkpoint |
| 2 清洗 | 缺失/异常处理，产出清洗表文件 | ≤ 150 s | ≤ 10 | set 清洗字段（带证据） |
| 3 核心计算 | 统计/建模主结果 | ≤ 300 s | ≤ 20 | set 结果字段；checkpoint |
| 4 图件 | 生成图并登记清单 | ≤ 90 s | ≤ 6 | set 图件字段 |
| 5 校验 | 契约对账、证据存在性、数值合理性 | ≤ 120 s | ≤ 6 | anomaly 记录偏差 |
| 6 定稿 | finalize + delivery_summary.md | ≥ 90 s 预留 | ≥ 4 | exit 0 或 4 |

每个阶段的修复重试不超过 2 次模型请求：第 2 次仍失败即记录 anomaly、
为该阶段产出字段写 reason，转入降级路径，把剩余预算让给后续阶段。

## 三、中断演练

假设在任意时刻被硬切断，磁盘上已存在：

- `result.json`：最近一次 set/finalize 之后的状态，status 至迟为
  `in_progress`，每个 null 字段都有理由；
- `/app/work/journal.jsonl`：每条已执行命令的退出码、时长、截断输出；
- `/app/work/checkpoints.jsonl`：链式 sha256，可验证 result.json 自某
  checkpoint 起是否被意外改动；
- 各阶段产出的证据文件（统计 JSON、清洗表、图件）。

这四者共同构成一个**合法 partial**，无需任何善后动作。演练方式：在
`examples/run_example.sh` 演示一的任意两行之间插入 `exit`，检查交付目录。

## 四、诚实规则（不可违反）

1. anomalies 只增不删；失败命令的 anomaly 由 run 自动生成，不得抹除。
2. 覆盖字段允许，但旧值以 sha256 形式留在 change_records 中，可审计。
3. partial 是一等结果：finalize 以 exit 4 交付 partial 完全正当；
   唯一不可接受的是静默 null（finalize 以 exit 1 拒绝）。
4. status 必须如实：`complete` 仅在所有契约字段非 null 时由 finalize 授予，
   不手工设置。
5. reason 必须写真实原因（“预算耗尽”“后端不可用”），不写空话。

## 五、与分析方法的组合

本治理器不关心分析如何实现，只约定四个接触点：

1. 分析脚本以文件为产物（JSON/CSV/图），写入 /app/output 或 /app/work；
2. 分析命令一律经 `stagegate.py run` 包裹，使失败可追；
3. 每个契约字段经 `stagegate.py set --evidence <产物路径>` 填充；
4. 分析内部的告警（假设不满足、数据异常）经 `stagegate.py anomaly` 上报。

因此任何分析技能（统计分析、SQL 查询、机器学习流水线）都可以原样嵌入
本协议：它决定“算什么”，治理器保证“算到哪一步都交得出”。
