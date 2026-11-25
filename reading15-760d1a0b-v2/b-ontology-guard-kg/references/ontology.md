# 封闭本体说明（bundle B: b-ontology-guard-kg）

> 机器可读版本见同目录 `ontology.json`。两者内容一一对应；脚本只读 `ontology.json`，
> 本文档面向模型与人工审阅者。**本本体是封闭的**：任何未在 `ontology.json` 中声明的
> 实体类型、关系类型、限定词（qualifier）键或极性值都会被校验脚本拒绝并进入隔离区。

## 1. 实体类型（9 种）与逐类型合并规则

| 类型 | 含义 | 合并规则（merge discipline） |
|---|---|---|
| `researcher` | 具名研究者/作者 | casefold 后的姓名键；跨篇合并必须显式 `merge` + 理由 |
| `material` | 化合物/材料类别 | casefold + 去空格/连字符；化学式↔全称须显式 merge（如 MAPbI3 ↔ methylammonium lead iodide） |
| `method` | 实验/计算方法 | casefold + 去空格/连字符 |
| `task` | 研究目标/应用任务 | casefold |
| `metric` | 可测量指标 | casefold；缩写↔全称须显式 merge（如 PCE ↔ power conversion efficiency） |
| `condition` | 测试/测量条件 | casefold；**参数不同的条件绝不合并** |
| `sample` | 具体物理样品/器件/层 | **跨篇绝不自动合并**；两篇中同名 sample 是 nonmerge 候选 |
| `dataset` | 具名数据集 | casefold |
| `claim` | 论文中的断言（含数值结论） | **绝不合并**；不同条件下的数值冲突保留为两个独立 claim 节点 |

关键纪律：
- 同名不同物（如两篇论文都出现 "TiO2" 但指不同样品/层）必须记录为显式 `nonmerge`。
- 跨篇数值冲突（如 PCE 21.1% @ 1-sun 初始 vs 18.7% @ 500 h 湿热后）必须保留为两个
  独立 claim，可用 `compares` 边连接并注明各自 condition，**不得**合并成一个结论，
  也不得标 `contradicts`（条件不同不构成矛盾）。

## 2. 关系类型（9 种）：domain / range / 极性 / 必需限定词

| 关系 | domain → range | 极性 | 必需限定词 | 语义要点 |
|---|---|---|---|---|
| `uses` | sample, method → material, method, dataset, sample | neutral | — | 主体使用/包含客体（器件可包含其层样品） |
| `compares` | claim → claim | neutral | `metric` | 两 claim 在某指标上被比较，无胜负 |
| `outperforms` | claim → claim | positive | `metric`, `condition` | 严格优于；方向敏感，必须有指标和条件 |
| `supports` | claim → claim | positive | — | 直接证据支持；综述转述不算，用 `reviews-cites` |
| `contradicts` | claim → claim | negative | —（建议 `metric`/`condition`） | 可比条件下的冲突 |
| `measures` | sample, method → metric | neutral | `condition` | 对样品/方法在某条件下测某指标；带数值时触发全局规则 |
| `reports` | claim → metric | neutral | `value`, `unit`, `condition` | 唯一强制携带数值的关系（数值型 claim） |
| `reviews-cites` | claim → claim | neutral | `context` | 一篇论文综述/引用另一篇的结论；必须注明引用语境，防止把转述当直接证据 |
| `aliases` | 同类型 → 同类型 | neutral | — | 别名/缩写/大小写变体；两端实体类型必须一致 |

## 3. 限定词（封闭词表）

`metric`(string), `condition`(string), `value`(number), `unit`(string), `context`(string),
`note`(string)。其他键一律报 `UNKNOWN_QUALIFIER`。内联公式/下标一律线性化为纯文本。

## 4. 全局规则

1. **NUMERIC_REQUIRES_METRIC_CONDITION**：任何携带数值 `value` 限定词的边，必须同时给出
   `metric`（或 metric 类型客体）与 `condition`。数值结论缺条件 = 违规。
2. **SAME_TYPE_REQUIRED**：`aliases` 边两端实体类型必须一致。
3. **CLOSED_VOCABULARY**：封闭词表之外的类型/关系/限定词全部拒绝。
4. **EVIDENCE_REQUIRED**：每个节点/边/merge/nonmerge/unreported 都必须带
   `{source_id, paragraph_id, quote}`，且 `quote` 必须是该段落原文的**精确子串**
   （由脚本机械校验；本数据包没有 PDF 页码，禁止编造页码）。

## 5. 类型化错误码（隔离原因）

`BAD_JSON_LINE, UNKNOWN_OP, BAD_SHAPE, DUPLICATE_ID, UNKNOWN_ENTITY_TYPE,
UNKNOWN_RELATION, DOMAIN_MISMATCH, RANGE_MISMATCH, SAME_TYPE_REQUIRED,
MISSING_QUALIFIER, UNKNOWN_QUALIFIER, QUALIFIER_TYPE_MISMATCH,
NUMERIC_REQUIRES_METRIC_CONDITION, POLARITY_MISMATCH, UNKNOWN_NODE_REF, SELF_EDGE,
EVIDENCE_MISSING, ADDRESS_NOT_FOUND, QUOTE_NOT_SUBSTRING, MERGE_TARGET_UNKNOWN,
REPAIR_BUDGET_EXHAUSTED`

`validation_report.json` 给出每个错误码的命中次数；被拒条目连同错误码写入
`quarantine.json`。

## 6. 有界修复策略（仅一轮）

1. 第 1 轮：校验模型草稿 → 违规条目入 `quarantine.json`。
2. 模型阅读隔离清单，写**一份**修复文件，只含被隔离条目的修正版本（沿用原 id）。
3. 第 2 轮：校验修复文件；通过的条目移出隔离区，仍违规的条目永久隔离（`final=true`）。
4. **没有第三轮**。再尝试修复会被 `REPAIR_BUDGET_EXHAUSTED` 拒绝。

## 7. 类型化查询

查询以类型化图模式执行，支持限定词过滤（见 `scripts/query.py` 与
`references/extraction_schema.md`）：邻域查询按实体类型/关系类型过滤；关系遍历只返回
该关系类型的边；矛盾检查只沿 `contradicts`/`compares` 边并报告条件差异。每个查询结果
都列出"未决/未知"关系，空结果是诚实答案而非错误。
