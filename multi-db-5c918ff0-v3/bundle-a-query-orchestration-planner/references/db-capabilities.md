# 数据库能力参考表(离线规划用)

> **声明**:本文件是查询编排的**参考笔记**,来源于公开 API 文档的整理
> (Crossref REST API、Europe PMC RESTful Web Service)。评测环境**无网络**,
> 本文件与脚本内嵌常量仅用于"规划"——即决定*如果*发起查询应使用什么语法、
> 分页与配额——**绝不用于发起实时调用**。`scripts/query_planner.py` 中的
> `DB_CAPABILITIES` 常量即转录自本表;plan 阶段会记录本文件 sha256 以便溯源。

## 1. Crossref REST API(/works)

| 维度 | 事实 |
|---|---|
| 查询字段 | `query.bibliographic`(书目全文式检索)、`query.author`、`query.title`、`query.container-title`、裸 `query` |
| 过滤 | `filter=from-pub-date:YYYY-MM-DD,until-pub-date:YYYY-MM-DD,type:journal-article,has-full-text:true,from-index-date:...`(逗号分隔为 AND) |
| 分页 | `offset` + `rows`,`rows` 上限 **1000**;深分页建议 `cursor=*`(响应回传 `next-cursor`) |
| 排序 | `sort=relevance|published|updated|deposited`,配 `order=asc|desc` |
| 字段裁剪 | `select=DOI,title,author,published,...` |
| 查询回响 | `message.query` 回响本次实际执行的查询参数(可用于对账) |
| 截断判定 | `message.total-results > len(message.items)` ⇒ 单页截断 |
| 配额礼节 | 礼貌池需 `mailto`;尊重 `Retry-After`;建议超时 30s,指数退避至多 3 次 |
| 优势/短板 | 跨学科书目元数据覆盖面最广;**无摘要/全文**,outcome 类证据需下游核对 |

## 2. Europe PMC REST API(search)

| 维度 | 事实 |
|---|---|
| 查询语法 | 字段化:`TITLE:"..."`、`TITLE_ABS:"..."`、`ABSTRACT:"..."`、`AUTH:"..."`、`PUB_YEAR:[2015 TO 2026]`、`JOURNAL:"..."`、`DOI:"..."`;布尔 `AND / OR / NOT`(必须大写) |
| 分页 | `cursorMark`(`*` 起翻,响应回传 `nextCursorMark`,不变即翻完)+ `pageSize`,上限 **1000** |
| 排序 | `sort=` 缺省 relevance;可选 `CITED desc`、`P_PDATE_D desc`、`FIRST_PDATE_D desc` |
| 查询回响 | `request.queryString`(部分端点/版本不回响,对账时按 `not_echoed` 处理) |
| 截断判定 | `hitCount > len(resultList.result)` ⇒ 单页截断 |
| 配额 | 建议超时 30s,指数退避至多 3 次 |
| 优势/短板 | 生物医学摘要与受控词检索强;**学科偏向生物医学**,农学/植物学等 population 概念块覆盖偏弱(编排时必须显式声明) |

## 3. 出版方站点/导出(generic profile)

| 维度 | 事实 |
|---|---|
| 查询语法 | 站点关键词框,语法**不保证公开**;计划只登记中性关键词块与时间窗 |
| 分页 | 依站点翻页或导出文件而定;规划时仅登记意图,不假设页大小 |
| 查询回响 | 通常**不回响**,对账按 `not_echoed` |
| 截断判定 | 导出文件**无法可靠判定**,需人工核对站点计数 |
| 配额 | 保守:超时 60s,至多 1 次重试 |
| 优势/短板 | 自有全文与优先出版(ahead-of-print);格式站点各异(JSON/JSONL/CSV 均需嗅探) |

## 4. 中性 facet 块 → 各库语法翻译规则

1. **概念块内 OR、块间 AND**:同一 facet 的同义词用 OR 合并,facet 之间用 AND。
2. **Crossref**:无语义字段,所有词平铺进 `query.bibliographic`(空格连接);
   时间窗与文献类型进 `filter`,不进查询串。
3. **Europe PMC**:每 facet 译为 `(TITLE_ABS:"t1" OR TITLE_ABS:"t2" ...)`;
   作者 facet 用 `AUTH:"..."`;时间窗译为 `PUB_YEAR:[yyyy TO yyyy]` 追加在尾部。
4. **Publisher**:不翻译语法,仅输出关键词数组 + 时间窗 + 注意事项。

## 5. 回响与截断的对账口径

- `matched`:计划意图词集合与回响词集合的重合度 ≥ 0.6(脚本口径);
- `mismatched`:回响存在但重合度 < 0.6——说明材料并非本计划的真实响应,
  必须在 coverage_declaration 中告警;
- `not_echoed`:响应未携带查询回响(Crossref 少见、EuropePMC 视端点、
  publisher 常态)——**不是错误**,但对账置信度降级,需在 uncertainty 声明。
