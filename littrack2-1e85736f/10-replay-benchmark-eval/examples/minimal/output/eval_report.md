# 增量质量评测报告（time-replay benchmark evaluation）

- case_id: case-1e85736f-syn-010
- **数据性质：合成示例（synthetic）**。本案例中的快照、候选清单与历史运行记录均为人工构造的合成数据，仅用于演示与自测本 Skill 的测量流程；其中所有文献、DOI、arXiv 号与日期均为虚构，不代表任何真实文献或真实检索结果。
- 真值来源: snapshot_pair (t_prev import state + t_now current snapshot)
- 快照对: prev=`/Users/liuhengshen/Desktop/bhr_product/littrack2-five/bundles/10-replay-benchmark-eval/examples/minimal/materials/snapshot_prev.json` now=`/Users/liuhengshen/Desktop/bhr_product/littrack2-five/bundles/10-replay-benchmark-eval/examples/minimal/materials/snapshot_now.json`
- 时间窗口: 2026-11-01 ~ 2026-11-24（两端含）

## 1. 真值构造（机械构造，非人工标注）

| 类别 | 条数 |
| --- | --- |
| 快照对新增候选（t_now − t_prev） | 6 |
| truth_new（窗口内发表） | 4 |
| truth_backfill（窗口前发表、晚入库） | 1 |
| truth_out_of_window（窗口后发表） | 1 |
| unclassifiable（发表日期缺失/无法解析） | 0 |

## 2. 指标总览

| 指标 | 值 |
| --- | --- |
| precision | 0.6667 |
| recall | 0.5000 |
| duplicate_rate | 0.2500 |
| false_alert_rate | 0.3333 |
| backfill_misclassification | 1（占 truth_backfill 比例 1.0000）

计数：候选条目 4，唯一声明 3，重复声明 1；TP=2 FP=1 FN=2。

## 3. TP（命中真新增）

- canonical_key=doi:10.1000/syn.201 | now[6] doi=10.1000/syn.201 arxiv=None title=Self-Driving Labs for Perovskite Optimization
- canonical_key=arxiv:2611.10234 | now[7] doi=None arxiv=2611.10234 title=Multimodal Retrieval for Materials Literature

## 4. FP（误报，含 backfill 误报为 new）

- canonical_key=doi:10.1000/syn.099 | fp_reason=backfill_misreported_as_new | now[10] doi=10.1000/syn.099 arxiv=None title=Calorimetric Data Curation Practices

## 5. FN（漏报的真新增）

- canonical_key=doi:10.1000/syn.203 | now[8] doi=10.1000/syn.203 arxiv=None title=Bayesian Optimization of Flow Chemistry Conditions
- canonical_key=doi:10.1000/syn.204 | now[9] doi=10.1000/syn.204 arxiv=None title=Benchmarking LLM Agents for Hypothesis Generation

## 6. 重复声明

- identity=doi:10.1000/syn.201 | 候选第 0 条与第 2 条重复

## 7. 回归对比

- 基线 run: run1-synthetic；verdict: **REGRESSION**

| 指标 | 基线 | 本次 | delta |
| --- | --- | --- | --- |
| precision | 0.7500 | 0.6667 | -0.0833 |
| recall | 0.7500 | 0.5000 | -0.2500 |
| duplicate_rate | 0.0000 | 0.2500 | 0.2500 |
| false_alert_rate | 0.2500 | 0.3333 | 0.0833 |
| backfill_misclassification_rate | 1.0000 | 1.0000 | 0.0000 |

回归标记：
- **recall_regression**：recall 0.7500 -> 0.5000（下降 0.2500，阈值 0.05）
- **false_alert_regression**：false_alert_rate 0.2500 -> 0.3333（上升 0.0833，阈值 0.05）
- **duplicate_regression**：duplicate_rate 0.0000 -> 0.2500（上升 0.2500，阈值 0.02）
- **new_false_negatives**：本次新漏报 1 条: ['doi:10.1000/syn.203']

## 8. 假设与局限

- 真值完全由快照对机械构造：t_now 有而 t_prev 无者 + published/窗口分类；未做人工标注。
- 若记录在两快照间被修改标题且缺 DOI/arXiv 号，可能被误判为新增（见 references/truth_construction.md）。
- backfill 判定依赖 published 字段的准确性；published 缺失者单列 unclassifiable，不猜测。
- 本报告只做测量，不产出、不背书任何追踪管道本身的检索结果。
