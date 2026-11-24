# Coverage Matrix(数据库 × 关键字段 覆盖矩阵)

- case_id: `synthetic-render-forge-001`
- 单元格 = 该来源库的记录中该字段非空的条数;`merged` 列 = 合并后规范记录该字段非空的条数。

<!-- matrix:begin -->
| field | crossref | europepmc | publisher | merged |
|---|---|---|---|---|
| doi | 3 | 2 | 2 | 4 |
| pmid | 0 | 3 | 1 | 3 |
| title | 3 | 3 | 2 | 4 |
| year | 3 | 3 | 2 | 4 |
| first_author | 3 | 3 | 2 | 4 |
| authors | 3 | 3 | 2 | 4 |
| journal | 3 | 3 | 2 | 4 |
| volume | 3 | 0 | 2 | 4 |
| issue | 3 | 0 | 2 | 4 |
| pages | 3 | 0 | 2 | 4 |
<!-- matrix:end -->

## 单一来源记录(single-source-only,需人工复核)

| record_id | doi | sole source |
|---|---|---|
| rec-0003 | 10.99988/synforge.2022.031 | crossref |

## 系统性缺失字段(某库 0 覆盖、但合并后存在)

- crossref: pmid
- europepmc: issue, pages, volume

## Review appendix

### Unresolved contract fields(未决契约字段)

- (无:全部契约字段均已按语义填充)

### Conflicts(跨来源字段冲突清单)

- rec-0001 `authors`: 2 variants (per-field source priority: publisher)
- rec-0001 `journal`: 2 variants (per-field source priority: publisher)
- rec-0002 `authors`: 2 variants (per-field source priority: crossref)
- rec-0004 `authors`: 2 variants (per-field source priority: publisher)
