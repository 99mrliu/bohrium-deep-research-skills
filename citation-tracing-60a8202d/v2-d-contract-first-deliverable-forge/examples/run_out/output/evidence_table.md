# 证据表（evidence table）

- case_id: `synth-case-001`  status: `partial`
- 种子: Adaptive Graph Kernels for Retinal Vessel Segmentation（10.0000/synth.001，id=P4）
- 候选 4 条 / 扩展边 10 条

| # | 标题 | 年份 | 层 | stub | 关联依据 | locator |
|---|------|------|----|------|----------|---------|
| 1 | Deep Graph Kernels Improve Retinal Vessel Segmentation | 2023 | 1 |  | 正向引用 P4（前向追踪，citation 边由全语料反向索引恢复，direction_restored=true） | `citing.jsonl :: line 1` |
| 2 | Spectral Graph Kernel Methods: A Foundational Study | 2015 | 1 |  | 被 P4 列为参考文献（后向追踪，reference 边） | `crossref_batch.json :: $.message.items[0]` |
| 3 | RETINA-BENCH: A Benchmark Dataset for Retinal Imaging | 2012 | 1 |  | 被 P4 列为参考文献（后向追踪，reference 边） | `crossref_batch.json :: $.message.items[1]` |
| 4 | 10.0000/synth.999 |  | 1 | 是 | 被 P4 列为参考文献（后向追踪，reference 边） | `crossref_seed.json :: $.message` |

## 引用边

| source | target | kind | direction_restored | locator |
|--------|--------|------|--------------------|---------|
| P4 | P2 | reference | false | `crossref_seed.json :: $.message` |
| P4 | P3 | reference | false | `crossref_seed.json :: $.message` |
| P4 | S1 | reference | false | `crossref_seed.json :: $.message` |
| P4 | P1 | citation | true | `citing.jsonl :: line 1` |
| P2 | P3 | reference | false | `crossref_batch.json :: $.message.items[0]` |
| P2 | P4 | citation | true | `crossref_seed.json :: $.message` |
| P3 | P2 | citation | true | `crossref_batch.json :: $.message.items[0]` |
| P3 | P4 | citation | true | `crossref_seed.json :: $.message` |
| S1 | P4 | citation | true | `crossref_seed.json :: $.message` |
| P1 | P4 | reference | false | `citing.jsonl :: line 1` |

## uncertainty

- 身份合并 1 次（DOI/标题键），明细见 result.merge_log
- 1 个引用目标无法在语料中解析，已保留为 stub（仅原始指针与定位，未补造元数据）
