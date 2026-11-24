---
name: incremental-delivery-governor
description: >-
  当任何处于运行时契约之下、需要在 900 秒与 64 次模型请求的硬预算内诚实交付
  result.json 的案例时使用本技能：它在第 0 个模型请求内落盘由 output_contract
  派生的合法骨架，随后以带证据的字段填充、命令日志、链式 sha256 校验和与诚实
  finalize 保证任何时刻中断都留下一个合法 partial。它只治理交付过程，可与任意
  分析方法组合。当任务只是单次琐碎查询、治理开销明显超过其价值时不使用。
---

# 增量交付治理器（Incremental Delivery Governor）

## 重心与设计理由

本技能治理的是**交付过程**，而不是分析本身。典型的失败模式是：智能体把几乎全部
预算投入计算，被时间或请求数硬切断时，磁盘上要么没有任何 result.json，要么只有
一份静默 null 的 JSON——平台无从区分“没做”与“做了但没写完”，此前全部投入归零。
本技能的对应原则是：**先交付合法性，再追求完整性**。骨架在第一分钟内落盘，此后
每一次字段填充、每一条命令、每一次覆盖都在磁盘上留痕，因此任何时刻的中断点都
天然是一个合法的 partial：有 case_id、有已填字段、有逐字段的缺失理由、有异常
清单、有来源与变更记录。partial 是一等结果，不是失败的遮羞布。

## 固定路径与运行契约

- 输入：`/input/case.json`（case_id 与 output_contract）、`/input/task.md`、数据文件。
- 暂存：`/app/work`（journal.jsonl、checkpoints.jsonl、中间产物）。
- 交付：`/app/output`，其中 result.json 必须包含：
  - `case_id`：与 case.json 一致；
  - output_contract 声明的**每一个**字段：已计算则为真实值，未计算则为 null 且
    必须在 `missing_fields` 中有非空理由；
  - `status`：`complete` / `partial` / `in_progress`，必须诚实；
  - `anomalies`：异常清单，只增不删；
  - `provenance`：输入 case.json 的 sha256、工具与 Python 版本、平台、起始时间；
  - `change_records`：init、set、overwrite、reason、finalize 的逐条留痕；
  - `missing_fields`：`[{field, reason}]`，是 partial 的合法依据。

## 执行协议

以下命令中 `SG` 指 `scripts/stagegate.py`，输出目录以 `/app/output` 为例。

1. **第 0 个模型请求内落盘骨架**（在任何计算之前）：
   `python3 $SG init --case /input/case.json --output /app/output`
   若 result.json 已存在则拒绝覆盖（保护既有进度），确需重来加 `--force`。
   init 同时写出 budget_plan.md。
2. **每个阶段的真实命令一律经 run 包裹**（shell=False，退出码透明传递）：
   `python3 $SG run --output /app/output --journal /app/work/journal.jsonl -- <真实命令>`
   非零退出会自动追加一条 `stage_command_failed` anomaly。
3. **字段填充一律经 set 并附证据**：
   `python3 $SG set --output /app/output --field statistics --value-file /app/work/stats.json --evidence stats.json`
   大对象用 `--value-file`，小值用 `--value-json`。
4. **异常随时记录**：`python3 $SG anomaly --output /app/output --kind K --detail D`。
5. **未填字段写明理由**：`python3 $SG reason --output /app/output --field F --text "…"`。
6. **阶段切换前做链式校验**：
   `python3 $SG checkpoint --output /app/output --work /app/work --note "阶段说明"`。
7. **不确定进度时查询**：`python3 $SG status --output /app/output --work /app/work`，
   它会按已用时间给出“继续 / 收尾 / 立即 finalize”的建议。
8. **时间或请求预算触及阈值时立即定稿**：
   `python3 $SG finalize --output /app/output --case /input/case.json --journal /app/work/journal.jsonl`。
   退出码：0 为 complete，4 为 partial（诚实可接受），1 为 invalid（存在静默
   null，必须修复后重试）。

## 预算分配建议表

以 900 秒 / 64 次模型请求为基准，三个案例按同一比例各自执行：

| 阶段 | 时间预算 | 请求预算 | 说明 |
| --- | --- | --- | --- |
| init 落盘骨架 | ≤ 60 秒 | 第 0 个请求内 | 先合法，后计算 |
| 数据摄入与画像 | ≤ 10%（90 秒） | ≤ 8 次 | 字典、行数、缺失画像、输入 sha256 |
| 核心计算 | ≤ 60%（540 秒） | ≤ 36 次 | 每个子阶段修复重试 ≤ 2 次，超限记 anomaly 并降级 |
| 校验与复核 | ≤ 20%（180 秒） | ≤ 10 次 | 契约字段对账、证据存在性、数值合理性 |
| finalize 预留 | ≥ 90 秒 | ≥ 4 次 | 任何情况下不得挪用，到点立即 finalize |

## 异常处理

- **命令失败**：run 会把 exit code、起止时间、截断的 stdout/stderr 写入
  journal.jsonl，并自动追加 anomaly；治理器以子进程退出码退出，绝不吞错。
  每个子阶段的修复重试不超过 2 次，超限即降级为 partial 路径。
- **字段名不在契约**：set 不会静默写入，而是把值转存 `extras{}` 并打印警告，
  change_records 记为 `set_extra`。
- **重复 set 覆盖**：允许，但 action 记为 `overwrite`，并附旧值的 sha256，
  历史不可抵赖。
- **治理字段**（status、anomalies、provenance、change_records、missing_fields）
  不接受 set，由治理器自动维护。
- **静默 null**：finalize 校验到“值为 null 且无理由”时退出 1，拒绝定稿。

## 最小调用示例（合成）

```bash
SG=scripts/stagegate.py
python3 $SG init --case /input/case.json --output /app/output
python3 $SG run --output /app/output --journal /app/work/journal.jsonl -- \
    python3 analysis.py --csv /input/data.csv --out /app/output
python3 $SG set --output /app/output --field statistics \
    --value-file /app/output/stats.json --evidence stats.json
python3 $SG anomaly --output /app/output --kind figure_skip --detail "预算不足，跳过绘图"
python3 $SG reason --output /app/output --field figures --text "预算耗尽，见 anomaly"
python3 $SG checkpoint --output /app/output --work /app/work --note "统计完成"
python3 $SG finalize --output /app/output --case /input/case.json \
    --journal /app/work/journal.jsonl   # exit 0 / 4 / 1
```

完整可运行演练见 `examples/run_example.sh`（含故意失败命令与阴性测试）。

## 局限性

本技能**不能**提高任何单次计算的正确性：统计方法是否恰当、数值是否准确，仍由
与之组合的分析方法负责。它只保证三件事：交付物在契约下合法、过程全程可审计、
中断点即为诚实 partial。对单次琐碎查询（如只回答一个数）而言，骨架与日志的
开销超过其价值，不应使用本技能。此外，finalize 的证据检查是尽力而为的存在性
检查，不验证证据内容本身的真实性。
