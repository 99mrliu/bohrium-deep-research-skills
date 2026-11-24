# 数据库能力阈值表（DB Capabilities Reference）

本表是 coverage-cartographer 做「检索编排审计」与「字段覆盖矩阵」时参照的
各库能力基线。脚本 `scripts/coverage_cartographer.py` 内嵌了本表的机器可执行
等价规则；本文件为人类可读的权威说明。离线场景下本表描述的是各库
**响应信封结构** 与 **查询/分页能力**，用于审计而非发起请求。

## 1. Crossref（REST API 离线响应）

- 信封：`{"status": "ok", "message": {"total-results": N, "items": [...]}}`
- 查询参数：
  - `query.bibliographic`：自由文本书目查询（非字段化布尔语法）；
  - `query.author` / `query.title` / `query.container-title`：分字段查询；
  - `filter=`：`from-pub-date`、`type` 等过滤器。
- 分页/限量：
  - `rows`：每页条数（常规上限 1000）；
  - `cursor=*` 深翻页游标；`offset` 浅翻页（超过约 10000 不可靠）。
- 审计要点：
  - `message.total-results` 与 `len(message.items)` 不一致且无 cursor 证据
    → `hitcount_mismatch`（分页风险：剩余命中不可见）；
  - Crossref 记录通常 **不提供** `pmid` / `pmcid`；`abstract` 仅部分出版商
    寄存；`reference`（参考文献列表）仅对开放引文存在——这些字段在覆盖矩阵中
    常为 0，应如实记为 `field_systematic_gap`，不得假设其存在。

## 2. Europe PMC（REST API 离线响应）

- 信封：`{"hitCount": N, "request": {"query": ...}, "resultList": {"result": [...]}}`
- 查询语言（自有语法，与 Crossref 不同）：
  - 布尔：`AND` / `OR` / `NOT`；
  - 字段标签：`TITLE:`、`AUTH:`、`PUB_YEAR:`、`DOI:`、`JOURNAL:` 等；
  - 支持精确短语引号与邻近算符。
- 分页/限量：
  - `pageSize`（上限 1000）、`page` 页码；
  - `cursorMark=*` 深翻页游标（配合 `nextCursorMark`）。
- 审计要点：
  - `hitCount` 与 `len(resultList.result)` 不一致且无 cursorMark/page 证据
    → `hitcount_mismatch`；
  - 搜索结果记录常缺 `volume` / `issue` / `pageInfo`（取决于源）；
    `abstractText` 对无摘要条目缺失；不提供参考文献列表——覆盖矩阵如实记 0；
  - 同一自由文本检索式若被逐字从 Crossref 复制过来，字段标签能力完全未利用
    → `mechanical_copy`。

## 3. Publisher 端点（出版商平台/离线导出）

- 信封：无统一 schema。常见为 **JSON 数组** 或 **JSONL**（每行一个记录），
  字段命名各异（`doi`/`DOI`、`pages`/`page`、`references`/`reference_list`）。
- 查询能力：各出版商（Elsevier、Springer Nature、Wiley 等）端点与语法互不
  相同，无跨库统一语法；离线场景下通常只有导出文件而无查询回显。
- 分页/限量：各自为政；离线导出无分页证据可考。
- 审计要点：
  - 结构嗅探按「JSON 数组 / JSONL + 记录状对象」识别，数据库归属按文件名
    标记（含 `publisher` 等字样），识别失败 → `unclassified_material`；
  - 与 Crossref / Europe PMC 记录以归一化 DOI 或（标题|年份|第一作者姓）
    复合键对齐；同一 DOI 元数据冲突（如印刷年 vs 在线年）→
    `identifier_conflict`，列待仲裁、不静默合并。

## 4. 语法差异矩阵（mechanical_copy 判定依据）

| | crossref | europepmc | publisher |
|---|---|---|---|
| **crossref** | — | 不同 | 不同 |
| **europepmc** | 不同 | — | 不同 |
| **publisher** | 不同 | 不同 | — |

三者两两语法不同：同一检索式字符串被逐字（verbatim）发送至 ≥2 个库时，
必然至少在一个库上未利用其字段检索能力，记 `mechanical_copy`（warning）。
正确做法：按库改写——Crossref 用 `query.bibliographic`（必要时加 filter），
Europe PMC 用字段标签布尔式，publisher 按各自端点文档改写。

## 5. 查询证据的认定

检索编排审计只认三类证据（缺失即 `query_evidence_missing`，不做假设）：

1. `case.json` 中的结构化字段（`queries` / `search_queries` / `query_log`）；
2. `task.md` 同一行内同时出现数据库名与带引号检索式；
3. 材料信封自带的查询回显（如 Europe PMC 的 `request.query`）。
