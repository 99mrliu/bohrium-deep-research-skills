# 补检账本与边际收益报告

- case_id: `synthetic-demo-ledger-001`
- 覆盖：分母 9 / 命中 7 / 漏检 2（0.7778）
- 账本：5 条查询，3 轮；总新挽回 7 条参考记录
- 停止建议：建议停止（触发：S1_zero_gain_round）

## 查询账本

| 行 | 查询 | 轮 | 来源 | 命中记录 | 新挽回 | 边际收益 |
|---|---|---|---|---|---|---|
| 1 | Q1 | 1 | Crossref | 2 | R001,R002 | 2 |
| 2 | Q2 | 1 | EuropePMC | 3 | R003,R004 | 2 |
| 3 | Q3 | 2 | Crossref | 2 | R005,R009 | 2 |
| 4 | Q4 | 2 | EuropePMC | 2 | R006 | 1 |
| 5 | Q5 | 3 | Crossref | 2 | - | 0 |

## 停止规则判定

- **S1_zero_gain_round** 触发 — latest round 3 produced zero new recovered references（账本行：5）
- **S2_low_marginal_yield** 未触发 — marginal yield above floor (1.00)（账本行：3,4,5）
- **S3_budget_exhausted** 未触发 — no budget field in case materials; rule not evaluable — declared, not assumed（账本行：-）

## 残余遗漏估计

```json
{
  "method": "chapman-corrected lincoln-petersen over two query families",
  "family_A": {
    "source": "Crossref",
    "captured": 4
  },
  "family_B": {
    "source": "EuropePMC",
    "captured": 5
  },
  "overlap": 2,
  "estimated_total_recoverable": 9.0,
  "estimated_residual_omission": 2.0,
  "assumptions": [
    "equal catchability within each family (likely violated by topic heterogeneity)",
    "independence of the two families",
    "closed population = frozen reference set"
  ],
  "caveat": "estimate is a lower-bound heuristic when families share retrieval bias; report alongside per-record miss list, never as a replacement"
}
```
