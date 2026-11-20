# result.json 字段模板

```json
{
  "case_id": "<镜像自 case.json：case_id/id/caseId 依次尝试>",
  "status": "completed | partial | failed | in_progress",
  "skill": "design-typed-itembank-assessor",
  "generated_at": "<ISO 时间戳>",
  "output_contract": "<case.json 中 output_contract 的原文镜像，未改动>",
  "<output_contract 的每个字段名>": "<有对应产出则填值，否则 null>",
  "documents": [
    {
      "doc_id": "doc_001",
      "title": "<标题或 null>",
      "source_path": "<源文件路径>",
      "tier": "fulltext | abstract_only | failed",
      "word_count": 0,
      "design_type": "rct | cohort | case_control | cross_sectional | diagnostic | systematic_review | other | unassessable",
      "design_confidence": 0.0,
      "design_uncertain": false,
      "design_overridden": false,
      "matched_signals": [{"signal": "randomized", "weight": 2, "count": 3}],
      "grade": "high | moderate | low | ungradable",
      "derivation": ["R4: ... → moderate"],
      "stats": {"n_items": 16, "met": 10, "partial": 2, "not_met": 1,
                "not_assessable": 3, "core_not_met": ["C-03"], "core_na": [],
                "na_ratio": 0.188},
      "assessments": [
        {"item_id": "C-01", "dimension": "研究设计", "question": "...",
         "core": true, "judgment": "met", "quote": "...", "locator": "p1.¶3",
         "rationale": "...", "verification": {"status": "ok"}}
      ]
    }
  ],
  "sources": [{"doc_id": "doc_001", "source_path": "...", "tier": "fulltext",
               "method": "pdftotext", "sha256": "..."}],
  "uncertainties": ["<所有不确定性与异常处置记录>"],
  "change_records": [{"doc_id": "doc_001", "type": "design_type_override",
                      "from": "rct", "to": "cohort", "reason": "..."}],
  "verification_summary": {"total": 0, "ok": 0, "wrong_page": 0, "not_found": 0,
                           "missing_quote": 0, "skipped_na": 0, "invalid_judgment": 0},
  "artifacts": {"assessment_table_md": "assessment_table.md",
                "verify_report": "verify_report.json", "grades": "grades.json"}
}
```

约束：
- `status` 语义：completed=全部文献完成分级；partial=存在 ungradable/失败文献；failed=零文献。
- 任何失败点之前，extract_corpus.py 已写入 status=in_progress 的部分版本。
- output_contract 一律原样镜像；其字段若有产出则填值、无产出填 null 并在
  uncertainties 说明，不杜撰内容。
