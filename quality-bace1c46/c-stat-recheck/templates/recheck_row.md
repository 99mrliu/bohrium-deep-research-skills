# 复核行模板（recheck row）

recheck/<doc_id>.jsonl 每行一个 JSON 对象，字段如下：

```json
{
  "id": "doc_001:freq_vs_percent:1",
  "doc_id": "doc_001",
  "check_type": "freq_vs_percent | stratified_sum | abstract_vs_body | p_value_recompute | effect_direction | completeness:<item>",
  "status": "pass | discrepancy | not_recomputable | reported | absent | not_applicable | unclear",
  "sides": [
    {"quote": "verbatim 摘录（所在句）", "page": 3},
    {"quote": "另一侧 verbatim 摘录", "page": 5}
  ],
  "computed": 48.3333,
  "reported": 46.7,
  "tolerance": 0.05,
  "note": "重算 48.3333% vs 报告 46.7%（容差 ±0.05 个百分点）；超出容差……",
  "verification": {"verified": true, "offsets": [{"side": 0, "page": 3, "found": true, "offset": [1204, 1291]}]},
  "downgraded": false
}
```

字段约束：

- `sides` 必须 verbatim（从抽取文本原样截取，可整体取句）；缺口类行（absent/
  not_applicable）允许空 sides。
- `computed`/`reported`/`tolerance` 三件套让复核人无需重跑脚本即可看懂判定；
  not_recomputable 时 computed 为 null 且 note 说明缺什么。
- `verification` 由 verify_quotes.py 追加；`downgraded=true` 表示摘录校验
  失败整行降级。
- Markdown 渲染时的表头（见 recheck_report.md）：
  `| id | 检查项 | 结论 | 已验证 | 重算值 | 报告值 | 容差 | 页 | 摘录（截断） | 说明 |`
