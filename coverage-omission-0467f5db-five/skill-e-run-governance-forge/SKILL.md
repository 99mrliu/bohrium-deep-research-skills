---
name: run-governance-forge
description: 运行治理与证据绑定交付技能。用于"检索覆盖率与遗漏分析"类任务的过程质量控制与下游渲染：为整次运行建立可复跑证据链——run_manifest.json 记录脚本哈希、全部输入哈希与各阶段产物哈希；--replay 模式确定性复跑并逐阶段比对哈希、报告漂移；用一套与主管线不同的独立判定实现对确定性抽样记录复核，报告一致率与分歧清单；最终 coverage_report.md 中每个关键数字携带绑定号，binding_map.json 把绑定号映射到账本 JSON 路径，并渲染纯文本 SVG 覆盖图。当任务要求结果可复算、可抽检、可独立验证时使用。边界：复核分歧不自动改判，转人工并保留主管线状态；复跑比对基于剔除时间戳的规范 JSON；不做实时检索。
---

# 运行治理与证据绑定交付（run-governance-forge）

## 重心与适用条件

重心是**过程质量控制与下游渲染工程**：覆盖率报告本身也是工程产物，其中的每个数字都必须能回溯到机器可读的账本单元，整次运行必须能被第三方复跑验证。四道质量控制：

1. **运行清单**：`run_manifest.json` = 脚本 SHA-256 + 全部输入文件 SHA-256 + 各阶段产物哈希（基于剔除时间戳的规范 JSON）；
2. **确定性复跑**：`--replay` 重算全部阶段并逐阶段比对哈希；漂移阶段点名写入 `replay_verdict.json` 并以退出码 4 报警；
3. **独立复核抽检**：主管线用 Jaccard≥0.80，复核实现用 token 包含率≥0.90（故意不同的算法），对每第 3 条记录重判，报告一致率；**分歧不自动改判**——转人工、保留主管线状态、写入 uncertainty；
4. **证据绑定渲染**：报告数字带 `[Bn]` 绑定号，`binding_map.json` 映射到 `coverage_ledger.json#/denominator` 这类账本路径；附 SVG 覆盖图（纯文本渲染，零依赖）。

## 运行环境

- 输入 `/input/case.json`、`/task.md`；材料递归扫描。工作 `/app/work`，交付 `/app/output`。
- Python 3 标准库，零依赖，不联网。预算 ≤64 请求 / ≤900 秒。

## 调用方式

```bash
# 主运行
python3 /skills/weekly-skill/scripts/governance_forge.py \
  --input /input --work /app/work --output /app/output
# 交付前自检：确定性复跑
python3 /skills/weekly-skill/scripts/governance_forge.py \
  --input /input --work /app/work --output /app/output --replay
```

退出码：`0` 完成（或复跑一致）；`2` partial；`3` 契约字段缺失；`4` 复跑漂移。

## 产物

| 产物 | 内容 |
|---|---|
| /app/output/result.json | case_id、output_contract 全字段、status、sources（含哈希）、uncertainty、change_log |
| /app/output/coverage_report.md | 带 [Bn] 绑定号的报告 |
| /app/output/coverage_chart.svg | 覆盖图（逐条记录色块 + 命中比例条） |
| /app/output/replay_verdict.json | 复跑比对结论（--replay 时） |
| /app/work/run_manifest.json | 脚本/输入/阶段哈希清单 |
| /app/work/coverage_ledger.json、audit_report.json、binding_map.json | 账本、抽检台账、绑定映射 |

## 异常处理

- 参考集或查询材料缺失：status=partial，各环节分别降级说明；
- 复核实现与主管线分歧：记入 audit_report.discrepancies 与 result.json uncertainty，主统计不变；
- 输入文件在两次运行间变化：--replay 阶段哈希漂移，点名漂移阶段，绝不静默通过；
- 抽样基数为 0（参考集为空）：audit.agreement=null 并注明。

## 最小调用示例（合成示例）

`examples/input/` 为**合成**数据：7 条参考题录、2 条查询。运行：

```bash
python3 scripts/governance_forge.py --input examples/input --work examples/run/work --output examples/run/output
python3 scripts/governance_forge.py --input examples/input --work examples/run/work --output examples/run/output --replay
```

预期（合成示例，非正式案例结果）：覆盖 5/7；抽检 3 条，一致率 1.0；`--replay` 输出 `{"replay_ok": true, "drifted_stages": []}`。详见 examples/README.md。

## 自查方法

1. result.json 含 case_id 与契约全部字段，sources 每条带 SHA-256；
2. 报告中每个 [Bn] 都能在 binding_map.json 解析到存在的账本路径；
3. `--replay` 退出码 0 且 drifted_stages 为空；
4. audit_report.json 中 agree=false 的记录同时出现在 result.json uncertainty。
