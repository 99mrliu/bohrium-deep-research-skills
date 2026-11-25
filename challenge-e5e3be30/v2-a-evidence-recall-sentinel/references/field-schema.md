# 字段 Schema（数据契约）

以下 JSON 结构用于 Agent 与脚本交接，不是预先制作的答案。所有路径均为运行时路径。

## 输入 claims-to-verify.json

```json
{
  "claims": [{
    "claim_id": "C1",
    "question": "待核验问题，不表示命题为真",
    "query_families": [{
      "family_id": "C1-entity",
      "kind": "entity",
      "purpose": "本族负责什么召回风险",
      "variants": [
        "原始措辞",
        {"text": "第二变体", "channels": ["exact_phrase", "token_overlap", "numeric_match"]}
      ]
    }]
  }]
}
```

`kind` 允许 `entity | numeric | synonym | figure_table | restriction | other`。省略 `query_families` 会触发不足 bootstrap，不可签发证书。通道默认为三种全开。

## output_contract 适配

支持示例：

```json
{"fields": [{"name": "case_id", "type": "string"}, {"name": "claim_results", "type": "array"}]}
```

或：

```json
{"type": "object", "required": ["case_id"], "properties": {"case_id": {"type": "string"}}}
```

也可直接用字段名到类型/规范的 dict，或只给字段名 list。`array/list` 默认 `[]`，`object/dict` 默认 `{}`，字符串默认空串，数值默认 null。脚本对固定键的常用别名 `claims/results/verdicts/assessments` 填同一组审查结果，对 `evidence_certificates/no_evidence_certificates` 填证书数组；`search_audit/retrieval_plan/recall_coverage/summary` 为 dict。未知字段由 Agent 在 `result_overrides` 填值。

## pages.jsonl

每行：

```json
{"page_id":"source-001:p0001","source_id":"source-001","source":"paper.pdf","page":1,"text":"实际抽取全文"}
```

`page_ids` 是全文档范围基准。空白 PDF 页也保留，不用“没有候选”代替页面抽取状态。

## retrieval-plan.json

顶层 `claims` 带规范化查询计划；`coverage.page_ids` 为所有已抽取页；`coverage.sources` 是来源清单；`policy` 记录预算、本地转换次数、网络请求 0 和 `candidate_cap=null`。

## search-audit.jsonl

每个 **query variant** 一行：

- `claim_id/family_id/kind/variant_id/query/channels`
- `planned_pages/pages_scanned/full_document_scope`
- `channel_hit_page_ids`：每通道命中的 page ID 数组
- `semantic_verdict=null` 和“hit never support”说明

## candidates.jsonl

每个 claim/page 融合候选一行：

- 稳定 `candidate_id`、定位、来源、页码、`fused_score`
- `origin_families` 与 `matched_variants`，可证明第二族新增召回
- `context` 仅供定位，语义裁决必须查 `pages.jsonl` 全页
- `review_status=reviewed|unreviewed`
- `relevant`、`exclusion_reason`、`review_note`

初始全部 unreviewed。最终 retained evidence 必须 reviewed 且 relevant=true。

## review.json（Agent 写入）

```json
{
  "claim_reviews": {
    "C1": {
      "verdict": "supported | partially_supported | contradicted | insufficient_evidence",
      "rationale": "语义理由，不能只写检索命中",
      "evidence_candidate_ids": ["cand-..."],
      "conflicts": [{"candidate_ids": ["cand-a", "cand-b"], "description": "双方冲突及适用范围"}],
      "uncertainty": "范围限制"
    }
  },
  "candidate_reviews": {
    "cand-...": {
      "status": "reviewed",
      "relevant": false,
      "exclusion_reason": "具体说明哪一项人群/终点/数值不回答该问题",
      "note": "补充说明"
    }
  },
  "result_overrides": {"额外契约字段": "按契约类型的值"}
}
```

支持对应字段为 dict 或自身含 ID 的 list。候选未覆盖而是确实未检出时，candidate_reviews 可为空；有候选但 insufficient 时必须逐项解释。

## 最终 result.json

固定字段：

- `case_id`：原样传递。
- `status`：`partial | complete | error`；finalizer 只在全部验证通过时写 complete。
- `sources`：实际读取来源、抽取方式、页数和页 ID。
- `uncertainty`：失败、范围与契约适配的不确定性。
- `change_records`：skeleton、sources_loaded、retrieval_complete、Agent_review_applied、validated/validation_failed。
- `claim_results`：逐问题四级 verdict、理由、证据 candidate IDs、conflicts、uncertainty；insufficient 内嵌证书。

## no_evidence_certificate

`valid=true` 的必要条件：`query_family_sufficiency=true`、`all_planned_variants_executed=true`、`full_document_scope=true`、`unexplained_unreviewed_candidates=[]`、`unexplained_exclusions=[]`。`unreviewed_candidates` 若非空必须各有解释，但完成案例应为零。

证书含义仅为“在记录的文档范围、查询族与候选审查之后，没有足够回答该问题的证据”。它既不是对现实世界的否定，也不等同于反驳。

## recall_coverage.svg

文本 SVG，由 `coverage-svg` 从实际 plan/audit/candidates 生成。每个查询族一根候选数柱；柱子表示召回覆盖，不表示支持。示例图必须带 SYNTHETIC 标签。
