# notes.json 结构约定（delivery-studio）

```json
{
  "title": "论文标题（或案例名）",
  "card": {
    "研究问题": {"value": "…", "anchor": "p1-l12"},
    "方法": {"value": "…", "anchor": "s3¶1"},
    "局限": "…（普通字符串也接受）"
  },
  "sections": [
    {"heading": "3. Results", "body": "该节目的/方法/结果/结论…",
     "anchors": ["p2-l30", "p2-l41"]}
  ],
  "comparison": {"columns": ["配置", "指标", "条件"],
                 "rows": [["A", "8.2%", "partial shading"]]},
  "open_questions": ["…"],
  "limits": ["…"],
  "change_records": [{"before": "…", "after": "…", "why": "…"}]
}
```

规则：

- card 字段值可为字符串或 `{value, anchor}`；有锚点必给锚点。
- sections 必须保持论文原有章节顺序与标题，不套用通用摘要模板。
- comparison 仅当内容确有可比结构时使用（多配置/多论文/多指标）。
- open_questions 放“论文没回答但重要”的问题；limits 放交付自身的缺口（两者不要混）。
- change_records 记录交付过程中的所有修正（改锚点、改措辞、降级裁定）。
