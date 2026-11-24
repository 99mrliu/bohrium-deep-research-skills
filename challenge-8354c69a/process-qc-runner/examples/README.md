# 最小示例（合成示例，非正式案例结果）

演示过程质量控制三件套：阶段化运行、失败断点、幂等恢复、预算台账、
checkpoint 结果落盘。全部数据为**合成示例**。

## 运行

```bash
cd examples
bash run_example.sh
```

## 预期（captured 于 expected/run_log.txt）

1. 首次运行：阶段 A_stats 成功，阶段 B_needs_file 因输入缺失失败，运行器停在断点
   （exit=2），manifest 保留现场；
2. 修复后同一命令续跑：A_stats 显示 `SKIP (manifest 一致，幂等恢复)`，
   B、C 依次完成；
3. `budget.py report` 输出用量与降级建议；
4. `qc_runner.py status` 全部 OK；`result_kit.py verify` 通过；
5. 第三次运行：全部阶段 SKIP（幂等）。

`expected/` 为一次真实本地运行的日志与 result.json 副本。
