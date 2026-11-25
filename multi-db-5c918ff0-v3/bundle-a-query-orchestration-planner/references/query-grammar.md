# 中性 facet 块 → 逐库查询串文法

> 本文件定义 `facets.json`(模型产物)到各库查询串的翻译文法与实例。
> 实现见 `scripts/query_planner.py` 的 `build_*_plan` 函数;两者必须同步维护。

## 1. facets.json 模式(模型唯一判断产物)

```json
{
  "case_id": "synthetic-query-orch-001",
  "research_question": "……",
  "facets": [
    {"id": "F1", "role": "population",   "label": "……", "terms": ["t1", "t2"]},
    {"id": "F2", "role": "intervention", "label": "……", "terms": ["t3", "t4"]},
    {"id": "F3", "role": "outcome",      "label": "……", "terms": ["t5", "t6"]}
  ],
  "time_window": {"from": "2015-01-01", "to": "2026-12-31"},
  "publication_types": ["journal-article"],
  "language_scope": ["en"]
}
```

约束:`facets` 非空;`terms` 至少一项;`role` 建议取
`population / intervention / comparator / outcome / context`(PICO 式),
但脚本不强制枚举——未知 role 仅影响覆盖角色标注,不影响编译。
**脚本绝不自行编造 facets**;文件缺失时 plan 以退出码 2 诚实降级。

## 2. 文法规则

记 facet i 的词集合为 `Ti = {t_i1, …, t_ik}`,时间窗 `[from, to]`。

### 2.1 Crossref

```
query.bibliographic = concat_ws(" ", ∪ Ti)          # 全部词平铺,空格连接
filter              = "from-pub-date:{from},until-pub-date:{to},type:{ptypes…}"
rows=100, offset=0, sort=relevance
select              = DOI,title,author,published,container-title,type
```

### 2.2 Europe PMC

```
Q = AND_i ( OR_j TITLE_ABS:"t_ij" )                 # 块内 OR,块间 AND
Q = Q AND PUB_YEAR:[year(from) TO year(to)]         # 有时间窗时追加
author facet(role=context 且 label 含"作者")可改译为 AUTH:"…"
pageSize=100, cursorMark=*, format=json, sort 缺省 relevance
```

### 2.3 Publisher(generic)

不生成查询串,仅登记:
`{"keywords": [∪ Ti], "time_window": {from, to}, "note": "站点语法另行适配"}`

## 3. 完整实例(合成主题:ZK-7 / 水稻根向地性)

输入 facets:

- F1 population: `["Oryza sativa", "rice root"]`
- F2 intervention: `["ZK-7", "synthetic auxin analog", "dose response"]`
- F3 outcome: `["root gravitropism", "gravitropic curvature"]`
- time_window: 2015-01-01 → 2026-12-31

**Crossref 计划**

```
query.bibliographic = "Oryza sativa rice root ZK-7 synthetic auxin analog dose response root gravitropism gravitropic curvature"
filter = "from-pub-date:2015-01-01,until-pub-date:2026-12-31,type:journal-article"
rows=100&offset=0&sort=relevance
```

**Europe PMC 计划**

```
query = (TITLE_ABS:"Oryza sativa" OR TITLE_ABS:"rice root")
        AND (TITLE_ABS:"ZK-7" OR TITLE_ABS:"synthetic auxin analog" OR TITLE_ABS:"dose response")
        AND (TITLE_ABS:"root gravitropism" OR TITLE_ABS:"gravitropic curvature")
        AND PUB_YEAR:[2015 TO 2026]
pageSize=100&cursorMark=*&format=json
```

**Publisher 计划**

```json
{"keywords": ["Oryza sativa","rice root","ZK-7","synthetic auxin analog","dose response",
              "root gravitropism","gravitropic curvature"],
 "time_window": {"from": "2015-01-01", "to": "2026-12-31"},
 "note": "站点语法另行适配"}
```

## 4. 退化与边界

- facet 的 `terms` 为空 ⇒ 该 facet 跳过编译并在计划中注明;
- 无 `time_window` ⇒ Crossref 不加日期 filter,EuropePMC 不加 PUB_YEAR 子句;
- 未知库(能力表无条目)⇒ `planned=false` + 说明,不编译;
- 任何编译失败都不允许静默:必须落入 `query_plan.json` 的显式字段,
  由 reconcile 继承并计入覆盖声明。
