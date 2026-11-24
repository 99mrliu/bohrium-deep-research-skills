# 字段覆盖矩阵（Field Coverage Matrix）

单元格 = 该数据库实际提供该字段的记录条数；0 且该库有记录 = 系统性缺口（systematic_gap）。

| 字段 | crossref | europepmc | publisher |
|---|---|---|---|
| doi | 2 | 1 | 1 |
| pmid | 0 | 2 | 0 |
| pmcid | 0 | 1 | 0 |
| title | 2 | 2 | 1 |
| authors | 2 | 2 | 1 |
| journal | 2 | 2 | 1 |
| year | 2 | 2 | 1 |
| volume | 2 | 0 | 1 |
| issue | 2 | 0 | 1 |
| pages | 2 | 0 | 1 |
| abstract | 1 | 2 | 0 |
| reference_list | 1 | 0 | 1 |
| **记录总数** | 2 | 2 | 1 |

## 系统性字段缺口（0 次提供的 字段×库 组合）

- `pmid` × `crossref`：0 次提供
- `pmcid` × `crossref`：0 次提供
- `volume` × `europepmc`：0 次提供
- `issue` × `europepmc`：0 次提供
- `pages` × `europepmc`：0 次提供
- `reference_list` × `europepmc`：0 次提供
- `pmid` × `publisher`：0 次提供
- `pmcid` × `publisher`：0 次提供
- `abstract` × `publisher`：0 次提供

