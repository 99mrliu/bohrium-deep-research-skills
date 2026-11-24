# 检索协议模式（search_protocol.json）

```json
{
  "question_id": "rq-synth-glp1",
  "question_text": "...",
  "search_date": "2026-11-24",
  "snapshot_policy": "有限快照：……不声称实时或全局召回。",
  "queries": [
    {
      "database": "pubmed",
      "query": "(\"type 2 diabetes\"[tiab] OR ...) AND (...)",
      "field_scope": "title/abstract [tiab]；日期 [dp]",
      "date_limit": {"from": "2015-01-01", "to": "2026-12-31"},
      "language_limit": ["en"],
      "block_trace": [
        {"block_id": "P", "label": "population: ...", "clause": "(...)"}
      ]
    }
  ],
  "assembly_note": "概念块内 OR、块间 AND；……"
}
```

## 必填性与语义

- `search_date`：检索执行日；覆盖范围声明以它为准，缺省视为协议未定稿；
- `snapshot_policy`：必须保留——本技能不承认任何"实时数据库""全局召回"措辞；
- `block_trace`：概念块 → 查询子句的映射，是 map_criteria.py M4 核验与
  事后复核"为什么这个词在检索式里"的唯一依据；
- `date_limit` / `language_limit`：与检索式内的限定并列登记；
  执行侧落实差异（如某库语种限定只能界面勾选）写入 notes。

## 输入模式（research_question.json）

`concept_blocks[]` 每项：`block_id`（短大写标识）、`label`（人读）、
`terms`（同义自由词数组，块内 OR）。块间一律 AND。需要 NOT 块或
邻近算符时，不硬编码进生成器——在协议 notes 说明并由操作者确认后
手工增改，改完必须重过 lint 门禁。

## 变更管理

- 协议任何修改（词表、库、日期）生成新版本文件，旧版本保留，
  修改原因写入 result.json 的 change_records；
- 禁止"口头改检索式"：执行记录里的检索式必须能在某个协议版本中找到原文。
