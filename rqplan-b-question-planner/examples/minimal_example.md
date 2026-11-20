# 最小调用示例（示意输出，非正式案例结果）

```bash
# 1) 首次校验: 文件不存在,打印模板
python3 .../decompose_check.py --case /input/case.json --input-dir /input \
  --decomposition /app/work/decomposition.json
# {"ok": false, "error": "decomposition 不存在", "action": "请按 resources/decomposition_schema.md 编写后重跑", ...}

# 2) 按模板写入 4 个 SQ 后重跑校验
# {"ok": true, "sqs": 4, "dag_layers": 3, "layer_map": {"0": ["SQ-1"], "1": ["SQ-2", "SQ-3"], "2": ["SQ-4"]}}

# 3) 编译计划
python3 .../plan.py --decomposition /app/work/decomposition.json --work /app/work --input-dir /input
# {"ok": true, "waves": 3, "actions": 6, "budget": {"max_calls": 15, "planned_calls": 9}}

# 4) 执行检索并逐轮记账(示意两轮)
python3 .../roundlog.py append --work /app/work --sq SQ-1 --query "perovskite defect passivation" \
  --source search09_export.json --returned 15 --new-relevant 4 --evidence "s09-001,s09-002,s09-007,s09-014"
# {"ok": true, "seq": 1, "stop_decision": "continue", ...}
python3 .../roundlog.py append --work /app/work --sq SQ-1 --query "perovskite passivation grain boundary" \
  --source search09_export.json --returned 8 --new-relevant 0
python3 .../roundlog.py status --work /app/work
# {"rounds_total": 2, "per_sq": {"SQ-1": {"saturated": true, ...}}, "stop": false, ...}

# 5) 覆盖矩阵 + 收尾
python3 .../coverage.py --case /input/case.json --work /app/work
python3 .../finalize.py --case /input/case.json --work /app/work --out /app/output
# {"ok": true, "status": "partial"}
```

产物：`/app/output/result.json`（subquestions、retrieval_plan、rounds、coverage、gap_analysis、stop_decision、status、uncertainty）、
`coverage_matrix.json`、`gap_analysis.json`；`/app/work/` 下 `decomposition.json`、`retrieval_plan.json`、`rounds.jsonl`。
