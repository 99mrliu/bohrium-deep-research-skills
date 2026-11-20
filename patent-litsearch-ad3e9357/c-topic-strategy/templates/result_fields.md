# 模板：result.json 字段口径

scaffold_result.py 生成的骨架结构如下；所有字段必须保留，缺值用 null 并在
uncertainty 登记（output_contract 的全部字段会被自动镜像）。

```json
{
  "case_id": "取自 case.json",
  "status": "ok | partial | failed",
  "query": {
    "topic": "主题一句话",
    "version": "检索式版本（如 1.1）",
    "mode": "topic | number_lookup",
    "blocks": [{"name": "块名", "terms": [{"term": "词项", "intent": "识别依据"}]}],
    "boolean": "(a OR b) AND (c OR d)  [分面] IPC/CPC=(...) AND 年份=..."
  },
  "hits": {
    "patent": [{"ref": "文件#定位", "title": "", "identifier": "公开号",
                "year": 0, "matched_via": "keyword|classification|number_exact",
                "blocks_matched": ["块名"], "classification_matched": [],
                "duplicates": [{"file": "", "loc": "", "identifier": ""}]}],
    "npl":    [{"ref": "文件#定位", "title": "", "identifier": "DOI", "...": "同上"}]
  },
  "screening": {
    "prisma": {"identified": 0, "duplicates_removed": 0, "screened": 0,
               "excluded": 0, "included": 0},
    "decisions": [{"ref": "", "title": "", "track": "patent|npl",
                   "decision": "include|exclude", "reason_codes": ["I1"],
                   "rationale": "相关性依据/排除理由"}],
    "threshold_blocks": 0
  },
  "ranking": [{"ref": "", "title": "", "track": "", "decision": "", "score": 0.0,
               "breakdown": {"block_coverage": 0.0, "field_strength": 0.0,
                             "class_overlap": 0, "year_proximity": 0}}],
  "omissions": {"zero_hit_blocks": [], "unclassified_records": [],
                "skipped_files": [], "notes": []},
  "sources": ["实际读取的语料文件路径"],
  "uncertainty": ["未核验项与边界声明"],
  "change_log": [{"ts": "ISO8601", "action": "", "detail": ""}]
}
```

## status 诚实判定（scaffold_result 自动规则，可用 --status 覆写）

| 情形 | status |
| --- | --- |
| 语料为空 / 无任何记录可解析 | failed |
| 零纳入、存在无法判定记录、存在零命中概念块 | partial |
| 其余（全链跑通且无上述减损） | ok |

## 写作纪律

- result.json 是最终交付，文字结论引用 ref（file#loc）与 score 分解，不引用裸分。
- 部分完成必须说明界限：哪一步没做、为什么、影响哪些字段。
- change_log 追加每次人工修改（改检索式、改纳排、改 status），含时间与原因。
