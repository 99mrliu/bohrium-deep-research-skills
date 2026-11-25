# Rubric 打分表与阈值规则

> 打分由 `scripts/rubric_score.py` 机械执行，本文件解释配置语义。所有加减分逐条
> 记录在每条决策的 `score_entries` 中，可逐分复核。

## 1. 维度结构

`case.json -> screening_rubric.dimensions` 中每个维度：

| 字段 | 含义 |
|---|---|
| `points` | 命中一次所加（正）或所减（负）的分值；每个维度至多记一次 |
| `terms` | 词表，大小写不敏感子串匹配，搜索范围为 `title + abstract` |
| `weak_terms` | 可选，弱命中词表及各自分值（如只说 "interval training" 算弱命中 +1） |
| `comment` | 维度语义说明，仅供人读 |

典型维度（以 PICO 类研究问题为例）：

| 维度 | 分值 | 作用 |
|---|---|---|
| `population` | +3 | 研究对象匹配（如 "type 2 diabetes"） |
| `intervention` | +3（弱 +1） | 干预/方法匹配（如 "high-intensity interval" / "sprint interval"） |
| `study_design` | +2 | 设计匹配（如 "randomized"） |
| `outcome` | +2 | 结局匹配（如 "hba1c"、"glycemic control"） |
| `negative_population` | −4 | 错对象（儿童、1 型、妊娠、动物…） |
| `negative_method` | −3 | 错方法（药物/膳食等非目标干预） |
| `negative_outcome` | −2 | 错结局（非目标结局为主） |

规则细节：
- 每个维度命中任意一个词即记一次分，不重复叠加；先查 `terms` 再查 `weak_terms`。
- 命中位置（title 还是 abstract）写入 `score_entries[].field`，供证据装订定位。
- 摘要缺失时只搜标题，整条记录打 `title_only=true`（诚实降级，不补零分假装评过）。

## 2. 阈值与决策

配置：`include_threshold`（T）、`borderline_delta`（δ）。

| 条件 | 决策 |
|---|---|
| `score > T + δ` | `included` |
| `|score − T| ≤ δ` | `needs_human_review`（边界带，**不强行二分**） |
| `score < T − δ` | `excluded` |

示例（T=6, δ=1）：score≥7 且 |score−6|>1 → included；score∈[5,7] → review；
score≤4 → excluded。因此 10 分入选、5/6 分待复核、4 分及以下排除。

## 3. 排除类别推导

- 若任何负向维度被触发，用 `category_map` 把该维度映射为排除类别
  （如 `negative_population → wrong_population`），命中词记入 `category_evidence`。
- 若无负向命中但分数低于带下界 → `off_topic_low_score`。
- 规范化标题与更高优先来源条目相同 → 无论得分均为 `duplicate_of_kept`
  （来源优先级 `prefilter.source_priority`）。

## 4. 配置原则（给 rubric 编写者）

1. 词表只放**可逐字核验**的词/短语；命中即证据，证据必须能从原文切出。
2. 正向维度总分应显著高于 T，使"对象+方法+结局"齐全的条目稳定过带。
3. 负向维度的减分应足以把单维度错配的条目压到带外或带内，宁可进边界带也不
   强行排除存疑条目。
4. 改动 T/δ 后必须重跑并在 result.json 的 `screening_window`/`prisma_flow` 旁
   保留当时所用 threshold/delta（决策表每条自带 threshold/delta 字段）。
