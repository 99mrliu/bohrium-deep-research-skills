# 查询 JSON 规范（queryforge references）

## 结构

```json
{
  "question_id": "q1",
  "question": "原始提问文本",
  "concepts": ["规范概念词", "..."],
  "expansion_log": {"概念词": ["扩展1", "扩展2"]},
  "hard_filters": {
    "year": 2023,
    "date_after": "2023-01-01",
    "date_before": "2023-12-31",
    "project": "ALPHA",
    "batch": "B2023-014",
    "file_type": ["md", "csv"],
    "version": "final | draft | revised | vN",
    "path_contains": "项目ALPHA"
  },
  "unparsed_constraints": ["提问中出现但无法结构化的约束原文"],
  "filter_trace": {"<filter>": {"kept": 整数, "dropped": 整数, "undecidable": 整数}}
}
```

## 硬过滤抽取规则

| 提问中的线索 | 过滤器 |
|-|-|
| 四位年份（1990–2099） | `year`；同时设 `date_after/before` 为该年界 |
| `B\d{4}-\d+` 样式编号 | `batch` |
| "项目X / X项目"或大写项目代号 | `project` |
| 终稿/正式版/定稿 | `version: final` |
| 初稿/草稿 | `version: draft` |
| 修订/修改版 | `version: revised` |
| `v数字` | `version: vN` |
| "PDF/表格/文档/记录"等类型词 | `file_type` |

## 执行语义（不可违反）

1. 过滤器逐条施加，顺序无关；每条记录 kept/dropped/undecidable。
2. 候选**确认不满足** → dropped；条件字段**无法判定**（如文件无日期信息）
   → undecidable，不参与命中，但列入答案供人工查看。
3. 全部过滤后 kept=0 → `no_match`，答案必须给出 filter_trace 与
   "最后一条把候选清零的条件"。
4. 概念打分只在 kept 集合内进行；打分不淘汰，只排序。
5. 任何情况下不得为提高命中率而删除或放宽 hard_filters。

## 版本判定证据优先级

行政/备注文件中的明确声明（引用原文）> 文件名版本标记
（终稿>修订>初稿；vN 按数值）> 文件名内日期 > mtime。
判定依据写入候选的 `version_evidence` 字段。
