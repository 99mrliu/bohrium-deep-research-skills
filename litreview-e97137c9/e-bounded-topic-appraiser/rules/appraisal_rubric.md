# 选题评分规则（appraisal rubric）

本规则是 `scripts/appraise.py` 的唯一评分依据。所有分数仅在本案语料内有界成立，
不得外推为"该领域 worldwide 空白/成熟"。

## 0. 预备概念

- **可用文献**：tier ∈ {fulltext, abstract_only} 的文献（metadata_only / failed 不计入分母）。
- **选题 signature**：用 `vocab/facets.json` 的 aliases 给候选选题文本打标得到的 facet 集合。
- **支持文献**（supporting docs）：facet 集合**完全覆盖**选题 signature 的可用文献——
  即语料中已经直接做了这个选题的文献。
- **相关文献**（related docs）：与选题 signature **共享 ≥1 个 facet** 的可用文献——
  即支撑该选题可行性的邻近证据。

## 1. novelty_within_corpus（语料内新颖度）

```
novelty_within_corpus = 1 − |支持文献| / |可用文献|
```

- 支持文献为 0 → 1.0（语料内完全空白，通常绑定 facet_absent 空白）；
- 全部被直接覆盖 → 0.0（重复已有工作）。

## 2. evidence_sufficiency（证据充分度）

```
evidence_sufficiency = min(1, (n_fulltext + 0.5 · n_abstract_only) / 3)
```

- 按**相关文献**计数：fulltext 每篇计 1，abstract_only 每篇计 0.5（降级惩罚）；
- 3 篇等效全文即饱和（1.0）；0 篇相关文献 → 0.0（空白虽新，但无可执行证据底座，
  应被压分而不是被奖励）。

## 3. constraint_fit（约束契合度）

逐条核查 case 约束（`constraints`/`budget`/`limitations`/`requirements` 探测而来）：

- 可识别约束（内置关键词规则）：
  - `样本量≥N` / `sample size N`：相关文献全文中抽取 `n = N`、`N 名/例/participants`
    等样本量表述，最大值 ≥ N 则 satisfied；
  - `体内 / in vivo`：选题 signature 或相关文献 facet 含体内类方法
    （随机对照试验/队列/病例对照/横断面/单臂/荟萃分析/系统综述/动物实验），
    或相关文献全文含 `in vivo|体内|participants|randomized|受试|患者` 则 satisfied；
    选题 signature 含 `体外实验`/`细胞系` 直接 violated；
  - `体外 / in vitro`：对称判定；
  - `随机 / RCT / randomized`：命中 `随机对照试验` facet 则 satisfied，否则 violated。
- 不可识别约束：约束关键词在选题与相关文献全文中检索；
  有命中 satisfied（1.0），无命中 **unverifiable（0.5）** 并写入 uncertainties，
  不得猜测为 satisfied。
- `constraint_fit` = 各约束得分均值（satisfied=1.0 / unverifiable=0.5 / violated=0.0）。
- 无约束时记 **null**，总分权重归一为 `0.6·novelty + 0.4·sufficiency`。

## 4. 加权总分与推荐档位

```
weighted_total = 0.45 · novelty + 0.30 · evidence_sufficiency + 0.25 · constraint_fit
```

| 档位 | 条件 | 含义 |
| --- | --- | --- |
| `strong` | total ≥ 0.75 | 语料内新颖、有可执行证据底座且满足约束，建议立项 |
| `conditional` | 0.45 ≤ total < 0.75 | 部分维度不足（常见：新颖度被已有文献稀释，或证据底座偏薄），需补条件后再议 |
| `not_recommended` | total < 0.45 | 违反约束 / 证据底座过薄 / 语料内已充分覆盖，不建议立项 |

## 5. 绑定与问责

- 每个选题必须列出 `bound_gaps`（命中的 gap_register 条目）：facet_absent 空白按
  signature 命中绑定；single_source / unresolved_conflict 空白按涉及文献与相关文献的
  交集绑定。绑定未裁决冲突的选题，其证据充分度解读必须注明冲突存在（并列，不调和）。
- 评分理由（rationale）必须可复核：给出支持/相关文献清单、约束逐条核查结果，
  禁止"具有重要理论意义"式空泛表述。
