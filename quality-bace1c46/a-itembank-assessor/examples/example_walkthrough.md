# 端到端走查示例（示例，非正式案例结果）

> 本文档使用**完全虚构**的合成文献演示全链路，仅供理解数据流，不是任何真实案例的评测结果。

## 0. 合成输入

`/input/case.json`：

```json
{
  "case_id": "demo-001",
  "documents": [{"path": "paper_demo.txt"}],
  "output_contract": {"assessment_table": "...", "overall_summary": "..."}
}
```

`/input/paper_demo.txt`（虚构短文，节选）：

```text
Title: A randomized trial of demo drug in demo disease

We aimed to evaluate the efficacy of demo drug. This was a randomized controlled trial.
Patients were randomly assigned using a computer-generated random number sequence.
The study was double-blind. Primary outcome was symptom score at week 8.
Statistical analysis used t-test with SPSS 26.
```

## 1. 解析锚定（extract_corpus.py）

`docs.jsonl` 产生一行（词数 < 500，故按仅摘要分级——真实 PDF 通常远超此阈值）：

```json
{"doc_id": "doc_001", "source_path": "/input/paper_demo.txt", "tier": "abstract_only",
 "method": "direct_read", "word_count": 62, "n_pages": 1, ...}
```

`pages/doc_001.jsonl`：`{"page": 1, "text": "Title: A randomized trial ..."}`；
`anchors/doc_001.json` 含 `p1.¶1`、`p1.¶2` 等锚点。`/app/output/result.json`
在 10 秒内先落盘 `status=in_progress` 部分版本。

## 2. 分型（classify_design.py）

```json
{"doc_001": {"design_type": "rct", "confidence": 0.82, "uncertain": false,
  "matched_signals": [{"signal": "randomized controlled trial", "weight": 3, "count": 1},
                      {"signal": "randomly assigned", "weight": 3, "count": 1},
                      {"signal": "double-blind", "weight": 2, "count": 1}]}}
```

## 3. 条目匹配与判断（match_evidence.py → 模型）

`candidates/doc_001.json` 对 R-01 给出候选 `{anchor: "p1.¶2", hits: ["randomization", "randomly assigned"], ...}`。
模型回到原文核对后写 `assessments/doc_001.jsonl`（示例 3 条）：

```json
{"item_id": "R-01", "judgment": "met", "quote": "Patients were randomly assigned using a computer-generated random number sequence.", "locator": "p1.¶2", "rationale": "随机序列生成方法描述具体。"}
{"item_id": "C-07", "judgment": "met", "quote": "Statistical analysis used t-test with SPSS 26.", "locator": "p1.¶2", "rationale": "统计方法与软件明确。"}
{"item_id": "R-02", "judgment": "not_assessable", "quote": "", "locator": "", "rationale": "全文无分配隐藏描述，报告缺失不等于未实施。"}
```

## 4. 门控校验（verify_quotes.py）

R-01、C-07 摘录归一化后在第 1 页命中 → `verification.status=ok`；R-02 弃权跳过校验。
`verify_report.json`：`{"total": 3, "ok": 2, "skipped_na": 1, "downgraded": []}`。

## 5. 聚合分级（aggregate_grade.py）

tier=abstract_only → 触发 R5（封顶 moderate）；无核心 not_met、core_na=1 < 3 → R5a：

```json
{"doc_001": {"grade": "moderate",
  "derivation": ["R5: 仅摘要文献，等级上限为 moderate（不允许 high）",
                 "R5a: 无核心条目 not_met 且核心缺口可接受 → moderate"]}}
```

## 6. 组装交付（build_result.py）

`/app/output/result.json` 片段：

```json
{
  "case_id": "demo-001",
  "status": "completed",
  "output_contract": {"assessment_table": "...", "overall_summary": "..."},
  "assessment_table": null,
  "overall_summary": null,
  "documents": [{"doc_id": "doc_001", "design_type": "rct", "grade": "moderate", ...}],
  "verification_summary": {"total": 3, "ok": 2, "skipped_na": 1}
}
```

（`assessment_table`/`overall_summary` 为镜像的契约字段，若无产出填 null 并记入
uncertainties。）同时渲染 `/app/output/assessment_table.md` 人读评价表，
复制 `verify_report.json` 随交付。
