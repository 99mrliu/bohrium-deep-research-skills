# 合成示例（synthetic，非正式案例结果）

本目录数据 **完全虚构**，仅用于端到端演示 `d-grade-engine` 的等级推导、弃权传播与双人比对流程；不是任何真实案例的评估结果。

## 输入

- `input/case.json` — 合成案例 `SYNTH-CASE-001`，含 2 篇虚构文献（DOC-S1、DOC-S2）与 `output_contract`。
- `input/verdicts.jsonl` — 评定者 A 的 10 条维度判定。DOC-S2 故意设置 **3 个 `insufficient_evidence` 维度**，用于演示弃权传播。
- `input/verdicts_b.jsonl` — 评定者 B 的 10 条判定，含 **2 处蓄意分歧**（DOC-S1/measurement_outcomes、DOC-S2/statistical_analysis）。

## 真实运行命令

```bash
B=/path/to/d-grade-engine
W=$(mktemp -d); O=$(mktemp -d)
python3 "$B/scripts/derive.py"       --verdicts "$B/examples/input/verdicts.jsonl" --workdir "$W"
python3 "$B/scripts/second_rater.py" --rater-a "$B/examples/input/verdicts.jsonl" \
                                     --rater-b "$B/examples/input/verdicts_b.jsonl" --workdir "$W"
python3 "$B/scripts/build_result.py" --workdir "$W" --output-dir "$O" --case "$B/examples/input/case.json"
```

三次运行退出码均为 `0`。

## 真实输出摘录（本会话实际运行，未手工修改）

### 1) 弃权传播如期触发（derivation_report.md，DOC-S2）

```
## DOC-S2 → 总评: **insufficient_evidence**
- 推导链:
  - [domain] `internal_validity` ← 规则 `R-DOM-02`: 域内任一维度证据不足 → 域级 = 证据不足（弃权向域级传播） | 输入: `{"domain": "internal_validity", "members": ["design_adequacy", "sample_sampling"], "member_level_counts": {"insufficient_evidence": 2}}`
  - [domain] `inference_validity` ← 规则 `R-DOM-01`: 域内任一维度为高担忧 → 域级 = 高担忧 | 输入: `{"domain": "inference_validity", ..., "member_level_counts": {"insufficient_evidence": 1, "high_concern": 1}}`
  - [domain] `transparency` ← 规则 `R-DOM-03`: 域内任一维度为部分担忧（且无高担忧、无弃权）→ 域级 = 部分担忧 | ...
  - [overall] `overall` ← 规则 `R-OV-01`: 5 个维度中 ≥3 个证据不足 → 总评 = 证据不足（弃权传播，不被平均稀释） | 输入: `{"dimension_level_counts": {"insufficient_evidence": 3, "high_concern": 1, "some_concern": 1}, ...}`
```

注意：尽管 `inference_validity` 为高担忧核心域，按量表规则顺序 R-OV-01 优先命中，总评为 **insufficient_evidence** 而非 high——弃权绝不参与平均。

DOC-S1 则经 R-DOM-04 × 3 + R-OV-07 派生总评 **low**。

### 2) 双人比对（reliability_report.md）

```
- 配对判定数: 10
- 总体一致率: 80.0% (8/10)
- Cohen's kappa: 0.7059 (substantial (高度一致))

## 分歧列表 (待裁决, 2 条)
- `DOC-S1` / `measurement_outcomes`: A=**low_concern** vs B=**some_concern**
- `DOC-S2` / `statistical_analysis`: A=**high_concern** vs B=**some_concern**
```

（kappa 由 `scripts/second_rater.py` 以纯标准库直接实现：po=0.8，pe=0.32，kappa=(0.8−0.32)/(1−0.32)≈0.7059。）

### 3) result.json 头部（build_result.py 输出）

```json
{
  "case_id": "SYNTH-CASE-001",
  "skill": "d-grade-engine",
  "scale_version": "1.0.0",
  "status": "success",
  "status_reason": "全部期望文献均已派生等级。",
  "output_contract_mirror": { "output_contract": [ { "required_fields": ["case_id", "status", "grades", "reliability", "uncertainties", "change_records"], ... } ], ... },
  "grades": { "scale_version": "1.0.0", "docs": [ ... ], "rejected_count": 0 },
  "reliability": { "paired": 10, "agreement_pct": 80.0, "kappa": 0.7058823529411764, ... },
  "uncertainties": [],
  "change_records": [ ... ]
}
```

## 负向行为验证（开发者在 mktemp 目录另行实测）

- 含未知维度 `made_up_dimension`、未知等级 `super_bad`、重复判定、非法 JSON 的判定文件：4 行全部写入 `rejected_verdicts.jsonl` 并附原因，**运行继续**，退出码 0，合法行照常派生等级；
- 判定文件不存在：退出码 **2**；
- 零有效判定：result.json `status="partial"`，原因为「零有效判定……」；
- 仅 DOC-S1 有判定：`status="partial"`，`status_reason` 列出缺失文献 `DOC-S2`；
- A 缺一条判定时，second_rater 报告 `未配对 1`（仅 B 给出 DOC-S2/reporting_completeness），不静默丢弃。
