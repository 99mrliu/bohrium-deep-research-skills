# 覆盖度台账契约（coverage.json contract）

`coverage_ledger.py` 由 `canon.jsonl`（配合可选的 `ingest_report.json`）生成 `coverage.json`。
本文件定义其 schema、闭合法则、右删失规则与排除日志分类。门禁 `gate_check.py`
会**重新计算**闭环方程并交叉核对，不信任文件内的 `closure_ok` 标志。

## Schema

| 字段 | 类型 | 定义 |
|---|---|---|
| `per_year_counts` | object `{year: n}` | 保留记录逐年计数；min..max 之间缺年补 0 |
| `per_source_file_counts` | object `{path: n}` | 按来源文件的保留记录计数 |
| `records_with_year` | int | 有年份的保留记录数 |
| `records_without_year` | int | 无年份的保留记录数 |
| `year_missing_rate` | float | `records_without_year / kept`（kept=0 时为 0.0） |
| `right_censoring` | object | 右删失评估（见下） |
| `exclusion_log` | array | 筛选排除日志，初始 `[]`，逐条追加 `{id, reason, note}` |
| `closure` | object | 计数闭环块（见下） |

## 闭合法则

```
closure.records_total == closure.kept + closure.duplicates + closure.excluded
```

- `records_total`：摄入的原始记录总数（取自 ingest_report）；
- `kept`：canon.jsonl 行数（去重后保留）；
- `duplicates`：去重移除数（取自 ingest_report，须与 duplicates.json 的 pairs 数一致）；
- `excluded`：筛选阶段排除数 = `len(exclusion_log)`。

任何分析动作改变了 kept 或 excluded，都必须同步更新台账并重跑门禁；
闭环不成立（exit 1）时禁止进入趋势分析。该法则是"覆盖可审计"的机器化表达：
每一条原始记录的去向（保留/去重/排除）都有账可查，不存在凭空消失或凭空多出的记录。

## 右删失规则

文献数据库对最近一年的收录几乎总是不完整的（出版延迟、索引滞后）。规则：

```
final = max(per_year_counts 中的年份)
prev  = 年份 final-3, final-2, final-1 的计数（缺年按 0 计）
若 median(prev) > 0 且 count(final) < 0.4 × median(prev)
    → assessment = "suspected_partial"，final 计入 suspected_partial_years
若 median(prev) == 0
    → assessment = "insufficient_history"
否则 → assessment = "ok"
```

`suspected_partial` 时：趋势结论不得依赖末年斜率；研究空白声明须降级并在
uncertainty 中声明覆盖盲区。

## 排除原因分类（exclusion_log.reason taxonomy）

| reason | 含义 |
|---|---|
| `out_of_scope` | 主题超出 task.md 界定范围 |
| `date_out_of_window` | 年份在任务时间窗口之外 |
| `wrong_doc_type` | 非目标文献类型（如社论、新闻、专利） |
| `language_excluded` | 任务限定的语言之外 |
| `fulltext_unavailable` | 仅有题录且任务要求全文证据 |
| `duplicate_residual` | 引擎漏网的重复（人工复核发现；同时应回报引擎改进点） |
| `low_quality` | 明显低质/机器生成垃圾记录，note 中须给依据 |
| `other` | 其他，note 必填具体理由 |

每条排除记录格式：`{"id": "<canon id>", "reason": "<上表取值>", "note": "<一句话依据>"}`。
排除日志是研究空白（第 6 步）与覆盖声明的直接证据来源，不得省略 note。
