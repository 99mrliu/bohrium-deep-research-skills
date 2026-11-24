# 规格账本（spec ledger）模式与溯源规则

本 Skill 的一切结论挂在**规格账本**上：每条格式要求是一个结构化条目，
必须能回溯到具体文件与位置，否则不得进入账本。

## 条目模式（spec.json）

```json
{
  "id": "page.margin.top",
  "category": "page | style | text | caption | refs | content",
  "property": "margin_top",
  "value": 3.17,
  "unit": "cm",
  "status": "measured | stated | assumed | conflict-resolved",
  "source": {"file": "template.docx", "pointer": "word/document.xml#body/sectPr/pgMar@top", "quote": "top=1797 twips"}
}
```

## status 语义（诚实等级，禁止上调）

| status | 含义 | 允许进入交付结论？ |
|---|---|---|
| measured | 从模板 DOCX 的 OOXML 实测（docx_spec.py） | 是 |
| stated | 任务说明/投稿须知文本中明确写出（rules_spec.py，带行号与原文） | 是 |
| assumed | Agent 阅读材料后的人工补项（材料未明示、靠版式常识判断） | 只能进 uncertainties，不得当规格执行 |
| conflict-resolved | 多来源冲突，按优先级裁决（spec_merge.py 记录落选值） | 是，但必须在 uncertainties 点名 |

## 单位换算（OOXML）

- 页面尺寸、页边距：twips（1/20 pt）→ cm 除以 567。
- 字号：`w:sz@val` 为半磅 → pt 除以 2。
- 段前/段后：`w:spacing@before|after` 为 1/20 pt → pt 除以 2。
- 行距：`w:spacing@line` + `lineRule=auto` 时除以 240 得倍数；`exact/atLeast` 时为 1/20 pt。
- 栏数：`w:cols@num`，缺省为 1。

## 中文字号 ↔ pt（识别辅助表，非规格来源）

初号 42、小初 36、一号 26、小一 24、二号 22、小二 18、三号 16、小三 15、
四号 14、小四 12、五号 10.5、小五 9、六号 7.5、小六 6.5。
仅用于把"正文小四"这类文字规则换算成 pt；案件材料若直接给出 pt，以材料为准。

## 冲突裁决政策

1. 任务说明（task.md / case.json 明示）> 投稿须知/院系补充规定 > 模板文件实测。
2. spec_merge.py 退出码 1 表示存在已裁决冲突——这不是错误，但每一条冲突
   必须出现在 result.json 的 `uncertainties` 中，写明采用值与落选值。
3. 同来源内部矛盾（如同一须知两行给出两个行距）：不自动裁决，两项并列保留，
   标 `assumed`，交人工确认（manual_confirm）。

## spec_check 判定语义

- PASS：输出 DOCX 实测值与规格值在容差内（默认 ±0.06，单位随项）。
- FAIL：实测值存在且超差——必须修复输出或修正规格（若是规格抽取错误）。
- UNKNOWN：该项不是机器可核对的（如题注措辞、参考文献著录细节）。
  UNKNOWN 不等于通过：逐条进入 result.json 的 `manual_confirm`，
  交付前由 Agent 凭渲染预览或原文核对逐条落实。
