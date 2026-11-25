# 各源查询方言差异与字段表

`scripts/query_build.py` 把同一份概念块（块内同义词 OR、块间 AND）序列化为三个源的方言。
下表是序列化依据；离线评测中查询只用于对快照做可审计的模拟匹配，不发真实请求。

## 方言对照

| 能力 | Crossref REST | Europe PMC REST | arXiv API |
|---|---|---|---|
| 查询参数 | `query.bibliographic` | `query` | `search_query` |
| 布尔 AND/OR/NOT | 无（空格分隔词串，按相关度打分） | 完整支持 | 支持 `AND / OR / ANDNOT` |
| 短语 | 不支持引号短语 | `"..."` 锁定词序 | `"..."` 锁定词序 |
| 字段限定 | 无字段语法（另有 `query.title` 等独立参数） | `TITLE:"..."`、`TITLE_ABS:"..."`、`ABSTRACT:"..."`、`AUTH:"..."` 等 | `ti:`、`abs:`、`au:`、`all:` |
| 日期窗口 | `filter=from-pub-date:YYYY-MM-DD,until-pub-date:YYYY-MM-DD` | `FIRST_PDATE:[YYYY-MM-DD TO YYYY-MM-DD]` | `submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]` |
| 通配符 | 不支持 | 词尾 `*`（如 `neural*`） | 不支持 |
| 大小写 | 不敏感 | 不敏感 | 不敏感 |

## 本 Skill 的序列化模板

设概念块为 `[(object: a1,a2), (method: b1,b2), (scenario: c1)]`，窗口 `[S, E]`：

- **crossref**
  `query.bibliographic = "a1 a2 b1 b2 c1"`（空格连接全部 term），
  `filter = "from-pub-date:S,until-pub-date:E"`。
  附 note：概念块的 AND/OR 结构无法在服务端表达，需客户端后置过滤；
  多词 term 短语语义丢失（QL001）。
- **europepmc**
  `(TITLE_ABS:"a1" OR TITLE_ABS:"a2") AND (TITLE_ABS:"b1" OR TITLE_ABS:"b2") AND (TITLE_ABS:"c1") AND FIRST_PDATE:[S TO E]`
- **arxiv**
  `(all:"a1" OR all:"a2") AND (all:"b1" OR all:"b2") AND (all:"c1") AND submittedDate:[S0000 TO E2359]`
  （`S/E` 去掉连字符；`all:` 如需限定摘要可换 `abs:`。）

## 快照结构（材料定位）

评测材料为组织方固化的各源 API 响应快照，本 Skill 按文件名识别
（`*crossref*.json` / `*europepmc*.json` / `*arxiv*.json`），并按如下最小字段集归一化：

| 归一化字段 | crossref 快照 | europepmc 快照 | arxiv 快照 |
|---|---|---|---|
| 标识符 | `doi` | `pmid` / `doi` | `arxiv_id` |
| 标题 | `title` | `title` | `title` |
| 摘要 | `abstract` | `abstractText` | `summary` |
| 日期 | `published` | `firstPublicationDate` | `published` |

材料路径优先取 `case.json` 的 `materials_dir`（相对 case.json 所在目录）；
缺失时用 `find` 兜底：
`find /input /app -maxdepth 5 \( -name '*snapshot*.json' -o -name 'reference_graph.json' \) 2>/dev/null`。
