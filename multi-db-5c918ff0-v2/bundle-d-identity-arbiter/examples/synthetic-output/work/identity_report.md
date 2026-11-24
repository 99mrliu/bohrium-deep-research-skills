# Identity Dedup Report — synthetic-identity-arbiter-001

## 数据源分类 (sources)

| file | classification | records |
|---|---|---|
| crossref_works.json | crossref | 3 |
| europepmc_results.json | europepmc | 3 |
| import_state.json | import_state | 0 |
| publisher_articles.json | publisher_array | 3 |
| reference_graph.json | reference_graph | 0 |

## 分层匹配统计 (tier counts)

- 输入记录: 9；显式别名对: 1；裁决文件: no
- T1 identifier-exact 对: 2
- T2 bibliographic-exact 对: 1
- T3 fuzzy candidate 对: 1
- 无匹配对: 32
- 规范记录数: 6

## 待仲裁队列 (arbitration pending)

- `rec-0006` ~ `rec-0009`: title_sim=0.7500, surname_overlap=1.0000, year_diff=1 — **pending, NOT merged**

## 字段冲突摘要 (conflicts)

| canonical members | field | chosen db | rule |
|---|---|---|---|
| rec-0001/rec-0007 | abstract | publisher | source_priority:publisher>crossref>europepmc |
| rec-0001/rec-0007 | pages | publisher | source_priority:publisher>crossref>europepmc |
| rec-0001/rec-0007 | url | publisher | source_priority:publisher>crossref>europepmc |
| rec-0002/rec-0005 | authors | crossref | source_priority:publisher>crossref>europepmc |
| rec-0002/rec-0005 | journal | crossref | source_priority:publisher>crossref>europepmc |
| rec-0004/rec-0008 | abstract | publisher | source_priority:publisher>crossref>europepmc |
| rec-0004/rec-0008 | authors | publisher | source_priority:publisher>crossref>europepmc |
