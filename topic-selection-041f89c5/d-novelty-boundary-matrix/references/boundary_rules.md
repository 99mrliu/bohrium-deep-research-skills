# 对账与划界规则

## judgments.jsonl 格式

```json
{"claim_id": "C1", "work_id": "W1", "relation": "covers",
 "evidence_anchor": "paper3.txt#Abstract", "note": "该工作已实现同机制"}
```

- `relation` ∈ {covers, partial, none}：
  - `covers`：该工作已实现陈述的**实质**（同一机制/同一数据/同一场景），不要求措辞相同；
  - `partial`：覆盖一部分要素（如方法相同但场景不同）；
  - `none`：任务不同、层面不同，或仅背景相关。
- `covers`/`partial` 必须附 `evidence_anchor`（来源文件#页码/小节/记录 ID）；`none` 宜写 note 说明为何无关。

## 判定规则（novelty_matrix.py 强制）

| 规则 | 条件 | 判定 |
|---|---|---|
| V1 | 任一 judgment 为 covers | covered |
| V2 | 无 covers，任一 partial | partial |
| V3 | 全部 none 且已声明 search_boundary | uncovered |
| V4 | 无 judgment，或全部 none 但无边界声明 | indeterminate |

一致性违例：X1 covers/partial 缺锚点；X2 引用不存在的 claim_id；X3 类型非法。有违例时脚本退出码 1，判定结果不得交付。

## 判定的语义边界

- `uncovered` = 在声明的来源与时间窗内未见覆盖。**不**等于"国际首创""填补空白"；边界扩大必须重新对账。
- `covered` 不妨碍提案仍有价值（工程化、严谨复现、边界条件扩展），但"新颖性"一项不成立——备忘录应如实区分"无新颖性"与"无价值"。
- `partial` 必须写清覆盖的是哪一部分、剩下的增量是什么；增量部分按 uncovered 的边界纪律对待。

## 冲突处理

两篇已有工作对同一 claim 的对账结论冲突（一说 covers 一说 none）时：保留两条 judgment，在 note 写明分歧原因（版本差异/指标定义差异），判定时按 covers 优先（V1），但备忘录必须登记冲突双方。
