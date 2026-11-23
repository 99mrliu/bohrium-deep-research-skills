# 裁定规则与 verdicts.json 格式（evidence-adjudicator）

## 裁定状态机

| verdict | 含义 | 硬性要求 |
|---|---|---|
| `supported` | 原文证据足以支撑答案 | ≥1 条 evidence_for，quote 逐字 |
| `contradicted` | 原文与所问相反 | evidence_for 指向相反陈述；reason 给出数值/条件对比 |
| `not_reported` | 原文未报告 | `searched.for` 非空；evidence_for 必须为空 |
| `ambiguous` | 证据冲突或条件不全 | evidence_against 非空，或 reason 明确命名冲突 |

## verdicts.json

```json
{
  "verdicts": [
    {"q_id": "q1", "verdict": "supported",
     "answer": "…直接回答…",
     "evidence_for": [{"anchor": "c1-2", "quote": "逐字片段"}],
     "evidence_against": [],
     "searched": {"for": ["cyclic life", "cycles"], "against": ["no difference", "failed"]},
     "reason": "简述证据如何支撑答案"}
  ],
  "contract_fields": {"answer": {"…按 output_contract 填充…"}},
  "sources": [], "uncertainty": [], "limits": []
}
```

## 答案纪律

- 答案先行，证据其次，边界第三；保留实验组、对照组、指标定义与单位。
- quote 必须支撑**整个**改写句；引文只支撑一半时，把不支撑的部分拆出去标注为推断或删除。
- 数值比较保留条件（温度、数据集、规模）；脱离条件的“更好/更快”不允许。
- 检索词留痕是 not_reported 的唯一通行证；至少含一个同义/缩写变体。
- 发现冲突时给双侧锚点与条件化结论，不静默选边。
