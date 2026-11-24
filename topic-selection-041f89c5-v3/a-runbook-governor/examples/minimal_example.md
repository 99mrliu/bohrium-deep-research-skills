# 最小示例（合成，非正式测试案例结果）

## 输入

`examples/input/`：虚构案例 `SYNTH-RUNBOOK-001`（5 字段契约）+ 虚构任务书 + 2 篇虚构文献。
所有内容均为合成示例，仅演示接口与流程。

## 运行

```bash
bash examples/run_example.sh
```

脚本做的事（全部真实执行，产物写入 `examples/output/`）：

1. `runbook.py init`：锁定 case_id，写出契约合法的 result.json 骨架（示例用 `--requests 10`
   小预算以便演示降级）；
2. 依次 enter/exit intake、question、retrieve、extract，每阶段写过程产物并 `tick` 自报消耗；
3. 故意把 10 次请求预算用尽，`status` 显示 L2；
4. `triage` 强制把 result.json 收为合法 partial；
5. `finalize --status partial --reason ...` 机检通过；
6. `run_state.json` 复制为交付附件。

## 预期输出（示例产物，标注为合成示例）

- `examples/output/app_output/result.json`：`status=partial`，5 个契约字段齐全，
  `case_id` 与输入逐字一致；空字段保留为 null 并在 uncertainties 中带 triage 说明；
- `examples/output/app_output/run_state.json`：完整审计轨迹（阶段耗时、预算台账、事件流）；
- `examples/output/work/checkpoints/result_*.json`：两次 checkpoint 快照；
- `examples/output/work/`：inventory.md、question_frame.md、screening_log.md、
  coverage_boundary.md、evidence_table.md。

关键观察点：**synthesize 与 closeout 根本没执行，交付依然契约合法**——这就是本技能要保的下限。
