# 合成示例（synthetic example）

**注意：本目录所有数据均为合成。** `synthetic-input/oracle.py` 是一个"合成 oracle"
（隐藏的二次响应面 + 基于 sha256 的确定性小噪声 ±0.005），用来代替真实实验；
它只证明工作流可运行、可复核，不提供任何真实科学结论。

## 输入（synthetic-input/）

| 文件 | 内容 |
|---|---|
| `case.json` | `case_id = synthetic-ec02b694-001`；`output_contract` 三字段：`experiment_plan` / `evidence_and_risk` / `confirmation_items`；材料路径 |
| `param_space.json` | 3 参数空间：温度 300–500°C step 10（21 水平）、时间 1–6 h step 0.5（11 水平）、流量 50–300 mL/min step 10（26 水平），共 6006 组合；目标 maximize |
| `budget.json` | 预算 10 个新实验点，历史点 0，种子 20240611 |
| `oracle.py` | 合成 oracle：读 next_batch 决策 JSON，把该批点的"实验结果"追加进 results.csv |

## 一键复现

```bash
cd <bundle 根目录>
python3 examples/run_demo.py
```

脚本会重建 `synthetic-output/` 的全部产物并打印每一步；任何脚本 traceback 都会让演示失败退出。

## 手工复现（等价的固定命令顺序）

```bash
# (a) 生成计划：6006 组合 > 10 预算 -> staged_sequential（筛选 4 / 加密 4 / 确认 2）
python3 scripts/plan_search.py --space examples/synthetic-input/param_space.json \
    --budget 10 --history 0 --seed 20240611 --output search_plan.json

# (b) 逐轮"做实验"直到 STOP（预算耗尽）：
python3 scripts/next_batch.py --plan search_plan.json --results results.csv \
    --log decision_log.jsonl --output next_batch.json      # EMIT 轮1 筛选 4 点
python3 examples/synthetic-input/oracle.py --points next_batch.json --round 1 --csv results.csv
python3 scripts/next_batch.py --plan search_plan.json --results results.csv \
    --log decision_log.jsonl --output next_batch.json      # EMIT 轮2 加密 4 点
python3 examples/synthetic-input/oracle.py --points next_batch.json --round 2 --csv results.csv
python3 scripts/next_batch.py --plan search_plan.json --results results.csv \
    --log decision_log.jsonl --output next_batch.json      # 改进 32.75% >= 2% -> EMIT 轮3 确认 2 点
python3 examples/synthetic-input/oracle.py --points next_batch.json --round 3 --csv results.csv
python3 scripts/next_batch.py --plan search_plan.json --results results.csv \
    --log decision_log.jsonl --output next_batch.json      # STOP budget_exhausted

# (c) 重放校验（通过，退出码 0）
python3 scripts/search_log.py verify --log decision_log.jsonl \
    --results results.csv --output verify_report.json

# (d) 负例：篡改 decision_log.jsonl 第 1 条记录的 results_digest 后重放，
#     报告 digest mismatch，退出码 1（见 verify_tampered.json）
```

## 输出（synthetic-output/，全部可由 run_demo.py 重建）

| 文件 | 说明 |
|---|---|
| `search_plan.json` | 分阶段计划：策略理由、决策表、轮 1 的 4 个 LHS 候选点（数值确定）、轮 2/3 的确定性生成规则、停止判据、种子 |
| `search_plan_rerun.json` | 同种子第二次运行的计划，用于字节比对 |
| `determinism_check.json` | `byte_identical: true` —— 确定性验证结论 |
| `next_batch_seq1..4.json` | 4 次决策：EMIT 筛选 → EMIT 加密 → EMIT 确认 → STOP(budget_exhausted) |
| `results.csv` | 10 行合成"实验结果"（round, temperature, time, flow, response） |
| `decision_log.jsonl` | 追加式决策日志，4 条记录，seq 1–4 |
| `verify_report.json` | 重放通过：seq 单调、digest 一致、快照与 results.csv 交叉核对 0 缺失 |
| `tampered_log.jsonl` | 第 1 条记录 digest 被篡改的日志副本 |
| `verify_tampered.json` | 负例报告：`status: fail`，digest mismatch 被抓，校验命令退出码 1 |
| `result.json` | 按 case.json 的 output_contract 动态填充的契约产物（status: success，uncertainty 明确标注合成来源） |
