# 最小调用示例（合成示例，非正式案例结果）

本目录演示 rq-coverage-compass 的完整接口。**全部数据为合成**：虚构研究问题、
9 条虚构快照记录（`10.0000/synth.cc.*` 为虚构 DOI）、虚构子问题分解。

## 输入（input/）

- `case.json`：中文研究问题（2021–2024 钙钛矿：晶界钝化效率 / 湿热稳定性 /
  铅泄漏生物毒性），10 个 `output_contract` 字段。
- `decomposition.json`：按 references/subquestion-template.md 手写的 3 个子问题，
  模拟平台流程中 Agent 写入 /app/work 的那一步（运行时先复制到 work 目录）。
- `search_export.json`：9 条合成记录，刻意设计——
  SQ-1 对应 3 条窗内记录（→ sufficient）；
  SQ-2 对应 2 条窗内记录（其中 1 条缺年份/DOI）+ 1 条 2019 出窗记录 +
  1 条 `conflict_opinion` 夹具（→ thin）；
  SQ-3 无任何对应记录（→ starved，触发 handoff_to_human）；
  另有 2 条主题不命中的陪跑记录。
- `task.md`：合成任务说明。

## 运行

```bash
mkdir -p /tmp/cc/work /tmp/cc/out
cp input/decomposition.json /tmp/cc/work/decomposition.json   # 模拟 Agent 写分解清单
python3 ../../scripts/measure.py  --case input/case.json --input-dir input --work /tmp/cc/work
python3 ../../scripts/finalize.py --case input/case.json --work /tmp/cc/work --out /tmp/cc/out
```

## 期望输出（expected/，由上述命令真实生成）

- `result.json`：`status=partial`；`sufficiency` = SQ-1 sufficient / SQ-2 thin /
  SQ-3 starved；`stop_decision.decision` = `handoff_to_human`（理由：SQ-3 零可用证据，
  缺口 no_records）；`candidates` 5 条；uncertainty 5 条（thin 声明、冲突夹具登记、
  元数据缺失、starved 触发 handoff、停止决定转述）。
- `coverage_matrix.json`：SQ×证据矩阵全量数字（SQ-2：可用 2 / 争议 1 / 出窗 1 /
  缺元数据 1，边际收益 1）。
- `stop_decision.json`：决定 + 可复核理由 + 逐 SQ 建议。

异常路径（未收入 expected/，可自验）：删去 work/decomposition.json 重跑，
脚本自动派生 5 个子问题（3 sufficient / 2 thin），停止决定变为
`marginal_gain_low` 并标注 `decomposition_source=auto_derived`；
以空目录作 input 重跑，measure exit=2、result.json `status=blocked`。

注意：本示例的输出**不是**平台正式案例的结果，仅用于说明接口与流程。
