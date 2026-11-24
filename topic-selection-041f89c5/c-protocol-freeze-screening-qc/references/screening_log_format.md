# 筛选日志格式（screening_log.csv）与机审规则

## CSV 表头（逐字）

```
record_id,title,decision,criterion_ids,reason,decided_at,note
```

| 列 | 说明 |
|---|---|
| record_id | 候选记录唯一标识（与输入文献集可对应） |
| title | 题名，人读对照用 |
| decision | `include` / `exclude` / `hold` |
| criterion_ids | 分号分隔的标准编号，如 `E1;E2` 或 `I1` |
| reason | 一句话理由；exclude 必填 |
| decided_at | ISO 日期，如 `2026-11-24` |
| note | hold 必填：缺什么信息、计划如何处置 |

含逗号的字段用双引号包裹（标准 CSV 转义）。

## 机审规则（screening_audit.py）

| 规则 | 内容 | 级别 |
|---|---|---|
| R1 | decision 必须 ∈ {include, exclude, hold} | 违例 |
| R2 | exclude 必须引用 ≥1 个 E 类标准且 reason 非空 | 违例 |
| R3 | include 宜引用 ≥1 个 I 类标准 | 警告 |
| R4 | 引用的编号必须存在于协议 | 违例 |
| R5 | hold 必须填 note | 违例 |
| R6 | decided_at 不得早于协议冻结时间 | 违例 |
| R7 | 统计以逐行重算为准，输出 PRISMA 式计数 | 信息 |

## 纪律

- 日志是**决策发生时**写的，不是综述写完后补的；R6 专门抓协议前决策。
- 修复违例的方式是改正日志/协议并留痕，不是删行。
- hold 记录最终必须转为 include/exclude 或在综述中声明"因信息不足未纳入"，不许留在待定里消失。
