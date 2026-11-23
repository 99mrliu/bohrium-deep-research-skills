# 语料与抽取的 JSON 模式（corpus schema）

本文档定义本技能涉及的全部 JSON 结构。所有文件为 UTF-8 文本。

## 1. 输入层（/input）

### 1.1 corpus-manifest.json（来源清单）

```json
{
  "corpus_id": "string",
  "sources": [
    {"source_id": "P1", "role": "primary|secondary", "path": "primary-material.json",
     "doi": "string", "title": "string"}
  ]
}
```

- `role=primary` 的来源**至多一个**；DOI/title/authors 等根元数据只属于 primary。
- 归一化器用 manifest 交叉核对 material 内嵌元数据，不一致记 warning。

### 1.2 material.json（聚合索引，三种容忍形态）

```json
[{"source_id": "P1", "role": "primary", "path": "primary-material.json"}]
{"materials": [...]}          // 亦接受 items/sources/files 键
{"P1": {"role": "primary", "path": "primary-material.json"}}   // 映射形态
```

条目可内嵌内容（`material`/`content` 字段）替代 `path`。material.json 缺失时，
归一化器回退到目录内 `*-material.json` 逐文件发现。

### 1.3 primary-material.json / secondary-material.json（JATS-like 原文）

```json
{
  "source_id": "P1",                       // 可缺省，由索引/文件名推定
  "role": "primary",                       // 可缺省，按文件名推定
  "jats": {
    "article-meta": {"doi": "...", "title": "...", "authors": ["..."]},
    "body": {
      "paragraphs": [...],                 // 扁平形态（可选）
      "sections": [                        // 分节形态（推荐）
        {"id": "P1.sec1", "title": "Introduction",
         "paragraphs": [{"id": "P1.p1", "text": "..."}]}
      ]
    }
  }
}
```

- 段落对象字段：`id`（可缺省，归一化器自动编址为 `{source_id}.auto{n}` 并告警）、
  `text`（原文，必须逐字符保留，含单位与空格）、`section`（可选）。
- 段落文本中的内联公式必须以**线性化文本**给出（如 `E = mc^2`），
  不允许图片占位或二进制对象。
- 外层包装 `{"material": {...}}` 会被自动剥除。

### 1.4 case.json

```json
{
  "case_id": "string",
  "output_contract": {"case_id": null, "nodes": null, "...": null},
  "query_specs": [{"query_id": "q1", "query": {"type": "neighborhood", "node": "...", "hops": 1}}]
}
```

- `output_contract` 的**键集合**即 result.json 必须精确镜像的键集合；
  值为占位符，装配器按类型填充，无法填充的置 `null` 并在 ledger 说明。
- `query_specs` 为待执行查询声明（可缺省，缺省时执行器仍可单条查询）。

## 2. 中间层（/app/work）：normalized_corpus.json

```json
{
  "format": "normalized-corpus/1",
  "input_dir": "/input",
  "sources": [
    {"source_id": "P1", "role": "primary", "doi": "...", "title": "...",
     "authors": ["..."], "path": "primary-material.json",
     "paragraph_count": 3,
     "paragraphs": [{"id": "P1.p1", "section": "Introduction", "text": "..."}]}
  ],
  "duplicate_paragraph_ids": {"P1": ["P1.pX"]},
  "skipped": [{"path": "secondary-publisher.xml", "bytes": 0, "sha256": "...", "reason": "..."}],
  "warnings": ["..."]
}
```

- `duplicate_paragraph_ids`：出现重复段落 id 时，首次出现保留，
  该 id 进入此清单，之后任何证据引用它都判为“地址歧义”错误。
- `skipped`：非 JSON 旁挂文件（如 secondary-publisher.xml）只登记不解析，
  含字节数与 SHA-256 以供审计。

## 3. 抽取层：candidate_extraction.json（模型产出）

```json
{
  "case_id": "string",
  "primary_paper": "n_paper_p1",
  "nodes": [
    {"node_id": "n_sample_al_p1", "kind": "sample", "label": "sample AL-P1",
     "canonical_key": "sample:AL-P1",
     "attributes": {"material": "alumina", "value": "可选", "unit": "可选"},
     "evidence": [{"source_id": "P1", "paragraph_id": "P1.p1", "quote": "原文精确子串"}]}
  ],
  "edges": [
    {"edge_id": "e3", "type": "produced_by", "subject": "n_sample_al_p1",
     "object": "n_method_fc", "evidence": [...]}
  ],
  "merges": [
    {"merge_id": "m1", "node": "n_method_fc",
     "members": ["n_method_fc_p1", "n_method_fc_s1"],
     "justification": "合并依据（规范化键 + 语义说明，合并不断言相同样本/参数/数值）",
     "evidence": [...]}
  ],
  "nonmerges": [
    {"nonmerge_id": "nm1", "members": ["n_a", "n_b"],
     "reason": "不合并理由（同名通用术语但物理对象不同）", "evidence": [...]}
  ],
  "conflicts": [
    {"conflict_id": "c1", "topic": "...", "claims": [{"node": "n_x"}, {"node": "n_y"}],
     "resolution": "preserved", "note": "...", "evidence": [...]}
  ],
  "unreported": [
    {"topic": "sintering dwell time", "reason": "...", "evidence": [...]}
  ]
}
```

字段约束（由 verify_evidence.py 机械执行）：

- `kind ∈ {paper, sample, method, condition, metric, claim}`（可扩展，但预览分层
  仅内置上述六类）；
- 每个节点/边**至少一条**证据；每条证据三字段齐备；
- `kind=paper` 的节点：证据只能来自单一来源，`attributes.doi/title/authors`
  必须与该来源 article-meta 逐字符一致；
- merge：`node` 为合并后的规范节点，`members` ≥2 且均为已声明节点；
  `node` 的证据源集合必须等于各 member 证据源之并且跨 ≥2 来源；
  `node` 与全部 member 的 `canonical_key` 完全一致；
  member 若均带 `attributes.value`，数值必须全部相等；
- 边不得引用 merge 的 member（必须引用合并后的 `node`）；
- nonmerge：两个互异已声明节点 + 非空 reason；
- 归一化后同 label 的未合并节点对必须被某条 nonmerge 覆盖；
- conflict 的 `resolution` 恒为 `"preserved"`。

## 4. 输出层（/app/output）

| 文件 | 说明 |
| --- | --- |
| result.json | 含 case_id + output_contract 精确键集合；查询结果子图带完整证据 |
| graph.json | `format=provenance-kg/1`，nodes/edges/merges/nonmerges/conflicts/unreported/stats |
| graph.jsonl | 每行一个对象（row ∈ node/edge/merge/nonmerge/conflict/unreported/stats） |
| queries.json | `format=provenance-kg-queries/1`，每条含 params/ok/summary/result |
| verify_report.json | ok/errors/warnings/coverage（含逐来源覆盖度与未覆盖段落清单） |
| ledger.json | 溯源台账：步骤、输入 SHA-256、警告、合同键处理、诚实 partial 标记 |
| preview.dot / preview.svg | 可读预览（DOT 文本 + 纯代码生成 SVG，无第三方依赖） |
