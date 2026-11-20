# judgments.jsonl 逐行格式说明

模型对每条记录（study_group）× 每条标准输出一行 JSON 判定。判定的 `record_id` 可用 group_id（如 G0001）或该组任一副本的 record_id（推荐 canonical record_id），引擎自动解析。

## 行格式

```json
{"record_id": "records-0001", "criterion_id": "INC1", "verdict": "pass", "evidence_snippet": "adults with type 2 diabetes", "note": ""}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| record_id | 是 | group_id 或任一副本 record_id |
| criterion_id | 是 | criteria_table 中已定义的 INC1../EXC1.. |
| verdict | 是 | `pass` / `fail` / `uncertain` |
| evidence_snippet | 条件必填 | verdict 为 pass/fail 且该标准 evidence_required=true 时必填；必须是该记录 title 或 abstract 的**原文连续片段**（引擎做 NFKC/小写/空白归一后做子串校验，不通过则整体 exit 3 重判） |
| note | 条件必填 | verdict 为 uncertain 时必填，说明不确定原因 |
| reason_code | 可选 | 仅用于标记边界码（BND-*）；缺省取标准注册码 |

## 示例（虚构）

```jsonl
{"record_id": "records-0001", "criterion_id": "INC1", "verdict": "pass", "evidence_snippet": "adults with type 2 diabetes", "note": ""}
{"record_id": "records-0001", "criterion_id": "EXC2", "verdict": "pass", "evidence_snippet": "randomly assigned", "note": ""}
{"record_id": "records-0003", "criterion_id": "INC1", "verdict": "fail", "evidence_snippet": "adolescents aged 12 to 17 years", "note": "未成年人群"}
{"record_id": "records-0008", "criterion_id": "INC1", "verdict": "uncertain", "evidence_snippet": "adults with type 2 diabetes or prediabetes", "note": "糖尿病/糖尿病前期混合人群，部分重叠", "reason_code": "BND-PARTIAL-OVERLAP"}
```

## 批量产出建议（节省模型请求预算）

- 一次模型请求尽量批量完成多条记录×全部标准的判定，直接输出 JSONL 多行。
- 每行必须独立可解析；不要输出 JSON 数组包裹，不要加注释。
- evidence_snippet 从 normalized.jsonl 的 title/abstract 中**复制**，不要改写、不要翻译、不要概括。
