# payload.json 结构（render_review_pack.py 的输入）

载荷是"数据"与"渲染"的边界：分析结论全部先进 payload，报告由脚本渲染。

```json
{
  "title": "……选题评估报告",
  "case_id": "与 case.json 一致",
  "question": {
    "statement": "一句话可检验问题陈述",
    "object": "研究对象",
    "variables": "自变量/因变量/混杂",
    "baseline": "比较基线",
    "falsifiable_if": "可证伪条件"
  },
  "prior_work": [
    {"id": "W1", "task": "...", "method": "...", "data": "...",
     "metric": "...", "result": "...", "comparability": "可比/不可比+原因"}
  ],
  "novelty_claims": [
    {"id": "C1", "claim": "提案创新陈述原文或改写",
     "type": "method|data|scenario|conclusion",
     "verdict": "covered|partial|uncovered|indeterminate",
     "basis": "依据（引用证据ID与检索边界）"}
  ],
  "feasibility": {
    "verdict": "可行/有条件可行/不可行/证据不足",
    "conditions": ["条件1"],
    "premises": [
      {"item": "数据可得性：...", "backing": "source|assumption",
       "ref": "来源定位或假设说明"}
    ]
  },
  "uncertainty": ["冲突证据取舍说明", "无法确定项"],
  "evidence_matrix": [
    {"ref": "E1", "source": "paper1.txt", "field": "结论",
     "value": "取值或摘录", "locator": "page 3"}
  ]
}
```

纪律：

- 所有键可缺省，缺省段落在报告中标注"未提供"——这是有意设计：报告真实反映数据缺口，而不是用模板文字填满。
- `novelty_claims[].verdict=uncovered` 时，`basis` 必须写明检索范围边界（哪些来源、什么时间窗），否则该判定无效。
- `feasibility.premises[].backing=source` 时 `ref` 必须给出定位；`assumption` 时 `ref` 写明假设理由。
- 渲染是确定性的：同一 payload 字节级同输出；要改报告，改 payload 重渲染。
