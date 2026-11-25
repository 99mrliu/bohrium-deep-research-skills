# 查询语法与执行语义（foundry.py 的判定依据）

查询族锻造的目标：**从研究问题（RQ）机械地派生一组可复算的查询**，每个命中都
带位置证据，第三方不看模型、只凭本文档即可复核任何一次执行。

## 1. 查询的三个族

| 族 | qid 前缀 | op | 语义 | 命中条件 |
|-|-|-|-|-|
| phrase | QP | phrase | 短语查询（多词/连字符术语，含变体） | 任一表层形式在记录文本中出现 |
| term | QT | term | 单词/二元组查询（拉丁词、CJK 整词与二元组） | 同上 |
| and2 | QA | and | 核心术语两两合取（≤6 个核心词 → ≤15 条） | 两个成员术语**各自**（含变体）均命中 |

核心术语选取规则：短语优先、其次按长度降序的拉丁词，取前 6 个；选取结果写入
`query-families.json.query_budget.core_terms`，可复核。

## 2. 匹配规则（确定性）

- 文本范围：记录的 `title`、`abstract`、`venue` 三字段，统一小写后匹配。
- 拉丁词/短语：词边界正则 `(?<![0-9a-z])…(?![0-9a-z])`——`ice` 不会误中
  `efficiency`，`sodium-ion` 与 `sodium ion` 是两个独立表层形式（靠变体互通）。
- CJK 整词与二元组：子串匹配（中文无词边界，子串即命中）。
- 大小写不敏感；不联网、不调用任何外部检索服务。

## 3. 命中证据格式（hits.jsonl 每行一条 查询×记录 命中）

```json
{"qid": "QP1", "family": "phrase", "rid": "R001",
 "matched": [{"term": "coulombic efficiency", "surface": "coulombic efficiency",
              "field": "title", "offset": 41, "snippet": "…上下文±20字符…"}]}
```

- `surface`：实际命中的表层形式（术语本身或某个变体）；
- `field`/`offset`/`snippet`：命中位置证据，可按原文字符偏移复核；
- and2 查询的 `matched` 含两个成员术语各自的证据。

## 4. 筛查条款（轻量，重器在查询族而非条款）

按优先级依次判定，第一条命中即定 disposition：

1. 夹具重复（`synthetic_duplicate`/`duplicate_of`/`fixture` 等标记）→
   `exclude: fixture_duplicate_registered`（原样登记，不进候选）；
2. 年份窗（RQ 中 ≥2 个年份 → [min,max]）外 → `exclude: year_out_of_window`；
3. 文献类型 ∈ {review, perspective, editorial, news} → `exclude: doctype_excluded`；
4. 命中任一 phrase/and2 查询，或 ≥2 个不同 term 查询 → `include`；
5. 恰好 1 个 term 查询命中 → `uncertain: weak_single_term_hit`；
6. 零命中 → `exclude: no_query_hits`。

`conflict_opinion` 夹具不改变 disposition，只追加理由码并写入 uncertainty——
**登记争议，不做学术裁决**。

## 5. 预算与截断纪律

- `--max-queries`（默认 40）限制查询总数；超出时按 phrase → and2 → term 顺序
  保留、尾部截断，截断数写入 `query-families.json.query_budget.truncated`。
- 截断**不是错误**：它把发散风险变成一条可检查的计数。若关键查询被截断，
  调大上限重跑即可（确定性保证同输入同输出）。
