# 检索覆盖率与漏检归因报告（模板）

- case_id: {{CASE_ID}}
- 状态: {{STATUS}}（ok / partial / failed）
- 生成时间: {{GENERATED_AT}}

## 分母口径

- 可用参考数（分母）: {{N_USABLE}}
- 剔除规则: 撤稿 / 重复 / 题录缺失，剔除清单逐条公布
- 剔除清单: {{EXCLUDED_LIST}}

## 覆盖率（仅从命中矩阵复算）

- 总体: {{HITS}}/{{TOTAL}} = {{RECALL}}，Wilson95=[{{CI_LO}}, {{CI_HI}}]

### 分来源

| 来源 | 命中 | 召回率 | Wilson95 |
| --- | --- | --- | --- |
| {{SOURCE}} | {{HITS}}/{{TOTAL}} | {{RECALL}} | {{CI}} |

### 分查询

| query_id | 来源 | 命中 | 召回率 |
| --- | --- | --- | --- |
| {{QUERY_ID}} | {{SOURCE}} | {{HITS}}/{{TOTAL}} | {{RECALL}} |

## 漏检归因（每条恰好一个主类别）

| ref_id | 主类别 | 致漏查询 | 致漏字段 | 证据文件 | 证据片段 |
| --- | --- | --- | --- | --- | --- |
| {{REF_ID}} | {{CATEGORY}} | {{QUERY_ID}} | {{FIELD}} | {{EVIDENCE_FILE}} | {{EVIDENCE_SNIPPET}} |

## 补检前后对比（同一冻结参考集）

- 补检前: {{RECALL_BEFORE}}；补检后: {{RECALL_AFTER}}；Δ={{DELTA}}
- 边际增益（新增命中）: {{MARGINAL_GAIN}} 条 {{NEW_HIT_IDS}}
- 零增益时必须原样写明「零边际增益，遗漏未削减」

## 限制与不确定性

- {{LIMITATION_ITEM}}

## 可复算性

所有覆盖率数字可由 hit_matrix.csv / hit_matrix.json 独立复算；漏检归因证据见
miss_attribution.csv；补检评估见 supplement_eval.md。
