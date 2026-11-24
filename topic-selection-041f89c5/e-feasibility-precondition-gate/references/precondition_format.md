# 前提台账格式（preconditions.jsonl）

每行一个 JSON 对象：

```json
{"id": "P1", "category": "data", "statement": "两个公开基准数据集可直接下载",
 "status": "ok", "backing": "source", "evidence_ref": "paper1.txt#sec2.1", "note": ""}
```

## 字段

| 字段 | 取值 | 说明 |
|---|---|---|
| id | P1, P2… | 唯一，备忘录与风险登记册引用 |
| category | data / compute / experiment / time / personnel | 五类前提 |
| statement | 自由文本 | 可判定的前提陈述，写清量级 |
| status | ok / blocked / unknown | ok=已有证据成立；blocked=确定不成立；unknown=无法确定 |
| backing | source / assumption | 依据性质 |
| evidence_ref | 文件#定位 | backing=source 时必填 |
| note | 自由文本 | backing=assumption 时必填（假设理由）；其余情况写风险说明 |

## 登记纪律

- 一条前提只断言一件事；"数据够且算力够"拆两条。
- statement 写清量级与口径："8 卡 A100 可用 4 周"而非"算力充足"。
- source 的 evidence_ref 必须能回到具体文件位置；任务书、约束场景、文献原文都算合法来源。
- assumption 的 note 写"为什么这样假设"以及"假设不成立的后果"。
- 不利前提（blocked）必须登记——它决定返工方向，删掉它结论就是粉饰。
