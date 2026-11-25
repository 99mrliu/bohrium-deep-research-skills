# 评分模型说明（scoring model）

本文件是 transparent-relevance-ranker 的唯一权威公式定义。
任何人拿到同一份 `records.json`（题录）、`anchors.json`（锚定命中）与
`config/scoring_config.json`（全部参数），都能手工或用脚本复算出完全相同的分数。
**不使用任何 embedding / ML 打分、随机数或时间戳。**

## 1. 总分公式

```
total(r) = coverage(r) + recency(r) + type_points × type_weight(ptype(r)) − diversity_penalty(r)
```

其中 `coverage(r) = coverage_points × Σ_f [ w_f × hit_frac(f, r) ]`，
`hit_frac(f, r) = facet f 中在记录 r 的题名/摘要里锚定命中的不同词数 ÷ f 的词总数`。

默认参数（`config/scoring_config.json`，修改权重只能改这个文件）：

| 参数 | 值 |
| --- | --- |
| coverage_points | 70 |
| recency_points | 10 |
| type_points | 15 |
| facet 权重 | population 0.30 / intervention 0.30 / comparator 0.10 / outcome 0.20 / study_design 0.10（和=1.0） |
| rounding_decimals | 4 |

## 2. 各分项规则

### 2.1 facet 覆盖（0–70 分）
- facet 集合由研究问题决定（人群/干预/对照/结局/研究设计），词表由模型在运行时填写；
- 每个词的命中必须经过 `anchor_hits.py` 锚定（见 anchoring_rules.md），未命中的词计 0；
- 同一词在同一记录中命中多处只计一次（按"不同词数"计覆盖，不按频次，避免灌水）。

### 2.2 时效分（0–10 分）
- `reference_year` = 语料内最大发表年份（离线快照下唯一确定，不用真实时钟）；
- `age = reference_year − year`：`age ≤ 0` 或 `age ≤ recency_window_years`（默认 5）→ 满分；
- `age ≥ window + decay_span`（默认 5+5=10）→ 0 分；其间线性衰减；
- 年份缺失 → `recency_points × unknown_year_factor`（默认 0.5）。

### 2.3 文献类型权重（0–15 分）
- `type_weights` 表（randomized controlled trial 1.0 → editorial 0.05，unknown 0.3）；
- publication_type 经同样规范化后查表，查不到按 unknown；
- 类型权重只反映"该类型对回答研究问题的典型证据价值"，不代表质量评价。

### 2.4 来源多样性调整（≤0 分）
- 多样性键：规范化期刊名，缺省回退第一作者姓氏；
- 同一键在语料出现 n 次，则该键下每条记录罚 `penalty_per_extra × (n−1)`（默认 2.0），封顶 `max_penalty`（默认 5.0）；
- 目的：避免同一期刊/团队批量导出垄断榜单前列；与处理顺序无关，可复算。

## 3. 分档与并列

| 档位 | 条件（默认阈值） |
| --- | --- |
| high | score ≥ 60 |
| medium | 30 ≤ score < 60 |
| low | score < 30 |

- 名次 = 按总分降序（同分按 record_id 字典序定序，仅用于稳定展示）；
- **并列如实标注**：舍入后总分完全相等的记录共用名次（竞赛排名 1,2,2,4），
  标同一 `tie_group`，绝不追加伪精度小数强排；
- 档位是阅读优先级建议，**不构成纳入/排除判定**。

## 4. 敏感性（rank instability）

- 对每个 facet 权重单独做 ±20% 扰动，其余权重按比例缩放保持和为 1（共 2×facet 数 个方案）；
- 每个方案用同一 `compute_scores()` 复算并重新分档；
- 任一方案下换档的记录进入 `rank_instability` 列表，含义：
  该记录的档位依赖权重选择，排序结论不稳，人工核阅时应优先注意。

## 5. 手工复算示例

设记录 X：population 命中 2/3 词、intervention 1/2、comparator 1/1、outcome 1/2、
study_design 1/3；year = reference_year；类型 RCT（1.0）；期刊键出现 4 次。

```
coverage = 70 × (0.30×2/3 + 0.30×1/2 + 0.10×1/1 + 0.20×1/2 + 0.10×1/3)
        = 70 × (0.2 + 0.15 + 0.1 + 0.1 + 0.0333…) = 70 × 0.5833… = 40.8333
recency  = 10
type     = 15 × 1.0 = 15
diversity = min(5, 2 × (4−1)) = 5
total    = 40.8333 + 10 + 15 − 5 = 60.8333  → tier high（≥60）
```

（此例即合成示例中 R08/R09 的真实计算，见 examples/selftest_log.md 的手工复核记录。）
