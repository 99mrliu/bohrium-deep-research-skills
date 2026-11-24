# run_plan 模板（由 budget_ledger.py plan 生成 run_plan.json；本模板为人读版结构说明）

```json
{
  "case_id": "<case_id>",
  "budget_total": 64,
  "reserve_verify_repair": 6,
  "allocation": {
    "reserve": 6, "screening": 1, "digests": "<按深度分批合计>",
    "themes": "3–8", "evidence_ledger": "≥2", "draft": "2–4",
    "total": "<≤ budget_total>"
  },
  "reading_plan": [
    {"doc_id": "D1", "tier": "fulltext", "depth": "full|sections|abstract|skip",
     "overlap_score": "<与研究问题的关键词重叠得分>",
     "duplicate_of": null, "batch_hint": "full 档每批≤2 篇合并 1 次请求"}
  ],
  "degradations": ["<已触发的降级决策，逐条留痕>"],
  "notes": ["<skip 原因等说明>"],
  "phases": [
    {"phase": "screening|digests|themes|evidence_ledger|draft|verify_repair",
     "planned_artifact": "<预期产物路径>"}
  ]
}
```

执行纪律：
- 深度与批次数以 run_plan.json 为准，模型阶段不得擅自突破；确需调整时重跑
  `budget_ledger.py plan` 并在 change_log 说明理由。
- `reserve`（verify+repair 6 次）任何阶段不得挪用。
- 每完成一个阶段立即 `budget_ledger.py mark --phase <名> --requests <实耗>` 登记。
