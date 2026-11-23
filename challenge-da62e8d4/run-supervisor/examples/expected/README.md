# examples/expected/ 说明（合成示例，非正式案例结果）

本目录两个文件是 `run_example.sh` 一次真实运行的**预期副本**，用于对照结构：

- `result.json`：finalize 之后（status 重算为 `partial`，合约 lint PASS）。
- `state.json`：同一时刻的监督器状态机。

注意：

1. **合成示例（synthetic），非正式案例结果**：其中所有指标、结论、路径均为演示数据，
   不构成任何论文数值复现。
2. **时间戳、墙钟秒数、绝对路径以实际运行为准**，逐字段 diff 时应忽略
   `ts / started / ended / wall_seconds / *_dir / *_path / start_*` 等字段。
3. 关键结构断言（应恒定）：`status == "partial"`；六阶段均 `done`；
   `runs` 中 `method_ok.exit_code == 0` 且 `method_fail.exit_code == 1`；
   五个合约字段（metric_table / chosen_candidate / discrepancy_cause /
   reproducibility_verdict / data_gaps）均非 null；`change_records` 含
   init、phase×6、run×2、finalize 条目。
