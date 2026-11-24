# 证据表模板（evidence_ledger.jsonl，每行一个 JSON 对象）

```json
{"evidence_id":"E1","doc_id":"D3","locator":"p2.¶4","verbatim_quote":"逐字摘录","supports":"该摘录支撑的论断（一句）","theme":"T2","strength":"established|suggestive|contested","quote_lang":"en|zh"}
```

填写规则：
1. evidence_id 连续编号 E1…En，不得重复。
2. verbatim_quote 从 pages/<doc_id>.jsonl 对应页复制；locator 页码必须与摘录所在页一致。
3. strength 不超过该 doc 信任层上限（T1→established；T2→suggestive；T3→禁止使用）。
4. 冲突证据成对出现，两条都标 contested，supports 写清各自条件。
5. 主动检索过反面证据但未找到时，写一行
   `{"evidence_id":"E#","doc_id":"*","locator":"-","verbatim_quote":"","supports":"no_adverse_found: 主题Tx 已检索 D1,D2,D4 的结果与局限段落","theme":"Tx","strength":"suggestive"}`。
