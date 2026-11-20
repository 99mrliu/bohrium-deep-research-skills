# 合成示例走查（示例，非正式案例结果）

> 本文件为**合成示意**：以下文献、数字与结果全部为演示虚构，用于说明
> 管线行为，**不是任何正式案例的运行结果**。

## 0. 输入

`/input/case.json`（节选）：

```json
{"case_id": "fixture-001",
 "documents": [{"path": "doc1.txt", "title": "Synthetic trial"},
               {"path": "crossref_snapshot.json"}],
 "output_contract": {"grade": null, "findings": null, "audit_trail": null}}
```

`/input/doc1.txt`（虚构短文，含一处刻意不一致）：

```text
Abstract
A total of n = 120 patients were enrolled: n = 60 were assigned to the
treatment group and n = 60 to the control group. The sample size was based
on a power calculation (80% power). In the treatment group, 31/60 (52%)
responded, compared with 27/60 (45%) in the control group. The difference
was statistically significant (t(118) = 2.31, p < 0.05). A secondary
endpoint also improved (χ² = 4.61, p = 0.032). The odds ratio was
OR = 1.8 (95% CI: 1.1 to 2.9), a significant increase. Overall,
58/120 (46.7%) responded.
```

（`crossref_snapshot.json` 为虚构 Crossref 风格快照，摘要含
`n = 45`、`40% (18/45)`。）

## 1. 采集（harvest_numbers.py 输出节选）

```json
{"doc_id":"doc_001","kind":"sample_size","value_fields":{"n":120},"sentence":"A total of n = 120 patients were enrolled: ...","page":1,"span":[...]}
{"doc_id":"doc_001","kind":"freq_percent","value_fields":{"count":31,"total":60,"percent":52.0,"percent_decimals":0},"sentence":"In the treatment group, 31/60 (52%) responded, ...","page":1}
{"doc_id":"doc_001","kind":"test_stat","value_fields":{"stat":"t","df":[118],"value":2.31},"page":1}
{"doc_id":"doc_001","kind":"p_value","value_fields":{"comparator":"<","value":0.05},"page":1}
{"doc_id":"doc_001","kind":"test_stat","value_fields":{"stat":"chi2","df":null,"value":4.61},"page":1}
{"doc_id":"doc_001","kind":"effect","value_fields":{"measure":"OR","value":1.8},"page":1}
{"doc_id":"doc_001","kind":"ci","value_fields":{"lo":1.1,"hi":2.9},"page":1}
{"doc_id":"doc_001","kind":"freq_percent","value_fields":{"count":58,"total":120,"percent":46.7,"percent_decimals":1},"page":1}
```

## 2. 重算（recheck.py 输出节选）

```json
{"check_type":"stratified_sum","status":"pass","computed":120,"reported":120,"note":"同句分组 n 之和 120 vs 总 n=120"}
{"check_type":"freq_vs_percent","status":"pass","computed":51.6667,"reported":52.0,"tolerance":0.5,"note":"31/60 重算 51.6667% vs 52%（容差 ±0.5）"}
{"check_type":"freq_vs_percent","status":"pass","computed":45.0,"reported":45.0,"tolerance":0.5}
{"check_type":"p_value_recompute","status":"pass","computed":0.0226,"reported":"p<0.05","note":"t(118)=2.31 近似重算 p≈0.0226（t 双侧，不完全β近似）< 0.05"}
{"check_type":"effect_direction","status":"pass","computed":{"lo":1.1,"hi":2.9},"reported":1.8,"note":"OR=1.8 与 CI [1.1, 2.9] 方向一致"}
{"check_type":"p_value_recompute","status":"not_recomputable","note":"检验统计量 chi2=4.61 缺少自由度，不可重算。"}
{"check_type":"freq_vs_percent","status":"discrepancy","computed":48.3333,"reported":46.7,"tolerance":0.05,
 "note":"重算 48.3333% vs 报告 46.7%（容差 ±0.05）；超出容差，属报告内部不一致，需人工核对（不代表论文错误）。",
 "sides":[{"quote":"Overall, 58/120 (46.7%) responded.","page":1},{"quote":"58/120 (46.7%)","page":1}]}
{"check_type":"completeness:sample_size_justification","status":"reported","sides":[{"quote":"The sample size was based on a power calculation (80% power).","page":1}]}
{"check_type":"completeness:multiplicity","status":"absent","note":"多重性控制：全文未检出相关报告（缺口，非过失）。"}
```

刻意不一致即最后一条 freq_vs_percent：31+27=58，58/120=48.33%，
而原文报告 46.7%，差 1.63 个百分点 ≫ 0.05 容差 → discrepancy。

## 3. 门控校验（verify_quotes.py）

所有 discrepancy/pass 行的摘录经归一化（连字符断行还原+空白折叠）后
在所标页命中，`verify_report.json`：`{"total_rows": N, "verified_rows": N, "failed_rows": 0}`。
若某行摘录被人为改过一个词，则该行 `downgraded=true`，其 discrepancy
在分级时按未验证降权。

## 4. 缺口表（节选）

| 文献 | 检查项 | 状态 |
|---|---|---|
| doc_001 | 样本量依据/功效 | reported（"…80% power" p.1） |
| doc_001 | 主结局效应量与精度 | reported（OR=1.8 + CI） |
| doc_001 | 缺失数据处理 | absent |
| doc_001 | 多重性控制 | absent |
| doc_001 | 不良事件 | not_applicable（未命中 trial 词表则为 other） |
| doc_002（快照） | 全部项 | 摘要口径判定，标 limited |

## 5. 等级推导（aggregate_grade.py）

```text
机械复核 8 行：pass=5，discrepancy（已验证）=1，not_recomputable=2。
关键完整性缺口 absent=2。
命中 concerns 阈值：已验证 discrepancy ≥1（1）；关键统计项 absent ≥2（2）。
→ grade = "concerns"
```

doc_002 为仅摘要条目 → 若案例仅含此类文献则 `limited=true`。

## 6. result.json 片段

```json
{"case_id": "fixture-001",
 "status": "completed",
 "output_contract": {"grade": null, "findings": null, "audit_trail": null},
 "contract_fields": {"grade": "concerns", "findings": {"pass": 5, "discrepancy_verified": 1},
                     "audit_trail": "audit_trail.md"},
 "statistics_grade": {"grade": "concerns", "limited": false, "derivation": ["..."]},
 "verification_summary": {"total_rows": 14, "verified_rows": 14, "failed_rows": 0},
 "uncertainties": ["p 值重算为近似实现……", "含仅摘要文献：仅做摘要口径复核……"]}
```
