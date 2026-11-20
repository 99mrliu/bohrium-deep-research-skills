# 字段映射表 — 出版商（publisher，格式不确定来源）

> 出版商来源的 schema **事先未知**：可能是 JSON（`items`/`records`/`results`
> 数组或裸 dict）、HTML 落盘的 `citation_*` 元数据片段、JSONL 或 CSV。
> 统一原则（SHARED_CONTRACT §2）：先嗅探归类，再按**启发式键名候选表**提取，
> 提取失败降级 unknown 并逐文件留痕，绝不硬编码“必然是某格式”。
> 归一字段全集与三级缺失语义伪代码见 `references/gap_taxonomy.md` §0。

## 启发式键名候选表（map_fields.py 的 KEY_CANDIDATES）

每字段按候选键顺序在记录内做**大小写不敏感**首命中查找；全部未命中 → 该记录
此字段交由载荷级动态判定（missing / not_provided）。

| 归一字段 | 键名候选（小写，按优先级） |
|---|---|
| identifiers.doi | `doi`, `article_doi`, `doi.org` |
| identifiers.pmid | `pmid`, `pubmed_id`, `pubmed` |
| identifiers.pmcid | `pmcid`, `pmc_id` |
| title | `title`, `article_title`, `articletitle`, `name` |
| authors | `authors`, `author`, `creators`, `byline`, `authorstring` |
| container | `journal`, `journal_title`, `journaltitle`, `container`, `container_title`, `container-title`, `publication`, `source` |
| year | `year`, `publication_year`, `pub_year`, `published_year` |
| volume | `volume`, `vol` |
| issue | `issue`, `number` |
| pages | `pages`, `page`, `pagination` |
| type | `type`, `article_type`, `content_type`, `genre`, `pubtype` |
| abstract | `abstract`, `summary`, `description` |
| pub_date | `publication_date`, `pub_date`, `pubdate`, `date`, `published`, `online_date` |
| cited_by | `cited_by`, `citedby`, `citation_count`, `times_cited`, `citedbycount` |
| references | `references`（数组取 len）, `reference_count`, `refs`, `reference` |
| license | `license`, `licence`, `copyright` |
| status | `status`, `retracted`, `withdrawal`, `article_status` |

## HTML 元数据片段（`citation_*` meta 标签）

`<meta name="citation_*" content="...">` 正则提取（兼容 content 在前/在后两种
属性序）。`citation_doi`→doi、`citation_title`→title、`citation_author`（多值）→
authors、`citation_journal_title`→container、`citation_volume`/`citation_issue`→
volume/issue、`citation_firstpage`+`citation_lastpage` 拼 `起始-结束`→pages、
`citation_publication_date`/`citation_online_date`→pub_date、
`citation_abstract`→abstract、`citation_article_type`→type。无 `citation_*`
标签的 HTML → 该文件记 unparsed_file（状态台账），不产出记录。

## 清洗规则

- DOI：去前缀 + 小写化（出版商常以 `10.xxxx/UPPER` 形式给出，小写化是与
  Crossref/EuropePMC 聚类的必要条件）。
- authors 值三态兼容：字符串（`"Family, Given; Family, Initials"`，按 `;`
  或 ` and ` 切分后复用 EuropePMC 同名解析规则）、字符串列表、dict 列表
  （取 `family/given` 或 `last/first` 等别名）；不可拆分的单 token 作者整体记
  family 并告警留痕。
- abstract 剥离 HTML 标签；year 取首个 4 位年份；cited_by 转 int。
- 撤回标记：`status`/`retracted`/`withdrawal` 键值或题名前缀
  （前 20 字符含 `retract|withdraw`）命中即标记。

## 静态 not_provided 清单

无。出版商全部字段均为载荷级动态判定——这是“格式不确定来源”的诚实处置：
本 bundle 不断言出版商 schema 是否提供某字段，只按**实际载荷**判定。
