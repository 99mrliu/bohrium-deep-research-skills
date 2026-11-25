# 段号约定（Bundle B）

- 段 ID：`p001…pNNN`，按源文出现顺序分配，全任务稳定，不重排。
- 块类型：`heading`（章节标题）、`paragraph`（正文段）、`caption`（Figure/Table 开头块）、
  `formula`（独立公式行）、`listitem`（列表块）。
- 每块记录：`{id, kind, page, text, sha256}`；page 来自 `\f` 分页符或抽取时的页信息。
- 追加新内容用新 ID；不得回收已删除段的 ID。

## 跨栏修复留痕格式

```json
{"type": "dehyphen", "from": "electri-\\ncal", "to": "electrical"}
{"type": "join-line", "from": "<前段尾40字符>\\n<次段头40字符>", "to": "<合并后80字符>"}
```

只修排版伪影；真段落边界（空行、标题、题注、公式行）永不合并。
