# 字段映射表 — Crossref（works API / 单条 work 详情）

> 归一字段全集（FIELDS）见文末；缺失三级语义判定伪代码见
> `references/gap_taxonomy.md` §0（本表与 `map_fields.py` 一一对应）。
> 记录定位：列表响应 `message.items[i]`；详情响应 `message`（单条 work）。

## 映射表

| 归一字段 | 源字段路径 | 提取 / 清洗规则 | 语义注释 |
|---|---|---|---|
| identifiers.doi | `message.items[i].DOI` | 去 `https://doi.org/`、`http://dx.doi.org/`、`doi:` 前缀后**小写化**；DOI 是大小写不敏感标识符，跨库聚类必须先归一 | Crossref 侧 DOI 权威 |
| identifiers.pmid | — | **静态 not_provided** | Crossref schema 不提供 PMID |
| identifiers.pmcid | — | **静态 not_provided** | Crossref schema 不提供 PMCID |
| title | `message.items[i].title[0]` | 取列表首元素，压缩空白 | 列表为空 → unknown |
| authors | `message.items[i].author[*]` | `{family, given}` 原样提取，统一为 `[{family, given}]`；缺 family 的条目告警留痕 | 与 EuropePMC 的 `authorString` 解析结果同构 |
| container | `message.items[i].container-title[0]` | 取列表首元素 | 即期刊/会议名 |
| year | `...issued.date-parts[0][0]` | 取 issued 年 | **语义注意**：`issued` 是 Crossref 记录的“发布日期”（可能由 print/online 合成），不等价于 print 或 online；`journal-issue` 下另有出版年字段，本 bundle 统一取 issued 年 |
| volume | `...volume` | 字符串原样 | — |
| issue | `...issue` | 字符串原样 | — |
| pages | `...page` | 字符串原样（Crossref 用单数 `page`） | — |
| type | `...type` | 原样（如 `journal-article`） | 与 EuropePMC `pubTypeList` 词表不同，跨库比较仅作参考 |
| abstract | `...abstract` | **剥离 HTML 标签 + `html.unescape` 反转义** | Crossref 仅部分成员元数据含 abstract；某响应载荷若任何 item 均无此键，该载荷内全部记录判 **not_provided**（载荷级动态判定） |
| pub_date | `published-print.date-parts[0]` → `published-online.date-parts[0]` → `issued.date-parts[0]` | date-parts `[y,m,d]` 格式化为 `y`、`y-m`、`y-m-d`（缺省位省略） | **三者语义不等价**：print=纸刊日期、online=在线发表日期、issued=合成发布日期；按 print 优先取值，print 与 online 并存且不一致时**告警留痕** |
| cited_by | `...is-referenced-by-count` | 转 int | Crossref 被引计数口径，与 EuropePMC `citedByCount` 不等价 |
| references | `...reference[]`（优先）→ `...reference-count` | 有数组取 `len(数组)`，否则取标量 | 计数口径，不逐条存引用内容 |
| license | `...license[*].URL` | 收集 URL 列表 | 载荷级动态判定；整载荷无 `license` 键 → not_provided |
| status | `relation` / `update-to` / `assertion` | 三处键值文本匹配 `retract\|withdraw`（含 `update-to.type`、`assertion.label`）→ 标记值拼接；有承载字段但无标记 → `active_no_marker`；三者均无 → 载荷级动态判定 | 撤回/更正标记识别依据 |

## 静态 not_provided 清单

`identifiers.pmid`、`identifiers.pmcid`（schema 层确定不提供）。

## 动态 not_provided（载荷级判定）

除静态清单外，Crossref 的 `abstract`、`license`、`status` 等“可选提供”字段按
**响应载荷**动态判定：若同一 `.json` 载荷内所有 item 均无该键，则该载荷内每条
记录的该字段记 `not_provided`；若载荷内部分 item 有、部分无，则有的记 present /
unknown，没有的记 `missing`。
