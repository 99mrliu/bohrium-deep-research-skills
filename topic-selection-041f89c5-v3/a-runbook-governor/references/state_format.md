# run_state.json 结构

由 `runbook.py init` 生成，此后由脚本原子更新；Agent 不手工编辑。

```json
{
  "case_id": "与 case.json 逐字一致",
  "contract_fields": ["字段1", "字段2"],
  "phases": {
    "intake": {"entered": 1764000000.0, "exited": 1764000030.5, "note": "..."},
    "question": {"entered": null, "exited": null, "note": null}
  },
  "active_phase": "intake | null",
  "budget": {
    "requests_cap": 64,
    "seconds_cap": 900,
    "requests_used": 0,
    "started_epoch": 1764000000.0
  },
  "result_path": "/app/output/result.json",
  "case_path": "/input/case.json",
  "checkpoints": ["/app/work/checkpoints/result_20261124T120000_intake.json"],
  "events": [{"t": 1764000000.0, "event": "init", "detail": "..."}],
  "finalized": {"status": "partial", "reason": "...", "t": 1764000900.0}
}
```

字段说明：
- `events` 是仅追加的审计日志；init/enter/exit/tick/checkpoint/triage/finalize 各记一条。
- `checkpoints` 保存每次 checkpoint 的快照路径；快照是 result.json 在那一时刻的逐字节副本，
  用于事后回放"结果是如何逐步长出来的"。
- `budget.requests_used` 是 Agent 自报的模型请求台账；脚本不联网核验，诚实依赖自报——
  漏报的唯一后果是降级触发过晚，损害的是运行者自己。
- 交付时把本文件复制到 /app/output/run_state.json，作为运行可复核性证据。
