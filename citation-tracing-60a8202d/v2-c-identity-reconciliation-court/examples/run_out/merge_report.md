# 身份合并台账（merge report）— case synthetic-identity-001

- 状态：ok；实体数：6；候选数：4；边数：6
- 合并组数：2；存疑对：0；同名不同文对：1

## 合并组明细

### E0001（成员 2，代表 r00001）
- 标记：version_chain
- r00001  ← `examples/corpus/crossref_export.json` @ `$.message.items[0]`（版本：journal）
- r00007  ← `examples/corpus/openalex_dump.json` @ `$.results[0]`（版本：preprint）
- 打分 r00001~r00007: 0.87 → merge
- 冲突字段（已保留，不丢弃）：{"title": {"r00001": "Graph Snowball Sampling for Citation Tracing", "r00007": "Graph snowball sampling for citation tracing: a synthetic study"}, "venue": {"r00001": "Journal of Synthetic Bibliometrics", "r00007": "arXiv (Cornell University)"}, "year": {"r00001": 2021, "r00007": 2020}}

### E0002（成员 1，代表 r00002）
- r00002  ← `examples/corpus/crossref_export.json` @ `$.message.items[1]`（版本：journal）

### E0003（成员 2，代表 r00003）
- 标记：version_chain, same_work_different_title
- r00003  ← `examples/corpus/crossref_export.json` @ `$.message.items[2]`（版本：journal）
- r00005  ← `examples/corpus/europepmc_hits.json` @ `$.resultList.result[1]`（版本：conference）
- 打分 r00003~r00005: 1.0 → merge
- 冲突字段（已保留，不丢弃）：{"title": {"r00003": "Robust Identity Matching Across Scholarly Indexes", "r00005": "Identity matching for scholarly records: an extended robust approach"}, "venue": {"r00003": "Journal of Synthetic Bibliometrics", "r00005": "Proceedings of the Synthetic Workshop on Records"}}

### E0004（成员 1，代表 r00004）
- r00004  ← `examples/corpus/europepmc_hits.json` @ `$.resultList.result[0]`（版本：journal）

### E0005（成员 1，代表 r00006）
- 标记：incomplete_record
- r00006  ← `examples/corpus/europepmc_hits.json` @ `$.resultList.result[2]`（版本：journal）

### E0006（成员 1，代表 r00008）
- r00008  ← `examples/corpus/openalex_dump.json` @ `$.results[1]`（版本：journal）

## 同名不同文（distinct_same_title）
- r00002 ≠ r00004：《A Survey of Graph Sampling》；标题高度相似，但作者/DOI 完全不重叠，判定为同名不同文（distinct_same_title）

## 同文不同名（same_work_different_title）
- r00003 = r00005（DOI 10.0000/synth.m1）；双标题保留：['Robust Identity Matching Across Scholarly Indexes', 'Identity matching for scholarly records: an extended robust approach']

## 不确定性 / 缺失说明
- stub 引用目标：10.0000/synth.b1（引用目标不在语料中，保留为 stub（未补造元数据））
- 残缺记录（缺 DOI/年份等关键字段）保持为独立实体: E0005，未参与自动合并
