# db_capability_notes — 三来源库一般性能力描述（查询语法差异）

> **声明**：以下内容为**一般性能力描述**，整理自各库的公开文档常识，用于解释
> “同一研究问题为何必须按库构造不同查询、台账为何应按库分别登记”。
> **未经实时验证**，具体语法与限制以各库官方文档与响应实际内容为准；
> 本 bundle 全程离线，绝不声称执行过任何真实联网查询。

## 1. Crossref（works API）

- 查询面：`query.bibliographic`（综合题录）、`query.title`、`query.author`、
  `query.container-title` 等分面参数；`filter` 支持
  `from-pub-date,until-pub-date,type,has-abstract` 等键值过滤；不支持完整布尔
  嵌套（各分面间为 AND 语义，分面内部为 OR 语义）。
- 分页：`rows`（每页条数）+ `offset`（游标式偏移）；深翻页宜用 `cursor`
  （`cursor=*` 起始，响应回传 `next-cursor`）。
- 响应：`message.total-results`（命中总数）、`message.items-per-page`、
  `message.query`（回显请求）、`message.items[]`。
- 台账关注点：命中总数与已取页数×每页条数是否吻合（截断检测）、
  `start-index` 游标连续性。

## 2. EuropePMC（RESTful search）

- 查询面：字段检索语法，如 `TITLE:"..."`、`AUTH:"Surname I"`、`DOI:"..."`、
  `ABSTRACT:"..."`、`JOURNAL:"..."`；支持 `AND/OR/NOT` 布尔组合与通配
  （`*`）；支持 `(FIRST_PDATE:[2010 TO 2020])` 区间过滤。
- 分页：`pageSize`（默认 25）+ `cursorMark`（`*` 起始，响应回传下一游标）；
  `hitCount` 为命中总数；`request` 块回显查询参数。
- 作者形态：`authorString` 为 `"Surname Initials; Surname Initials"` 串，
  与 Crossref 的 `author[].family/given` 结构不同——合并时必须回溯各自原文。
- 台账关注点：字段语法是否按库适配（与 Crossref 的 `query.bibliographic`
  风格差异显著）、`cursorMark` 翻页完整性。

## 3. 出版商接口（publisher）

- **格式最不确定**：可能是 JSON（`items`/`records` 数组或单条 dict）、HTML
  落盘的元数据片段、纯题录列表/JSONL/CSV。本 bundle 对其一律先嗅探再提取，
  解析失败降级 `unknown` 并留痕。
- 查询参数常不可见（接口封装或日志缺失）——这正是台账中 `query_unrecorded`
  最常见的来源；不得臆造。
- 检索方言差异大（各出版商私有语法），与 Crossref/EuropePMC 的查询串
  逐库 diff 是编排审计的核心动作。

## 4. 编排含义

- 三库查询串若逐字相同，多半意味着“机械复制了一条查询”，与各自方言能力
  不符；`query_log.py` 用序列相似度 + 词项差异做逐库两两 diff 并给出结论。
- 命中总数（Crossref `total-results` / EuropePMC `hitCount`）是截断检测的
  锚点：`Σ items_returned < total_hits` 且未见后续页游标 → `suspected_truncation`。
- 限流/配额痕迹（HTTP 429、`X-RateLimit-*`、`Retry-After`、`quota` 字样）
  在材料中出现即分类 `observed`，未见只能记 `not_recorded`（不能反推“无限流”）。
