# SQLite 类型亲和（type affinity）审计

## 为什么重要

SQLite 是动态类型：列的"类型"只是**亲和性提示**，任何列可以存任何类型的值。
导出管线（pandas `to_sql`、某些 ETL 工具）常把数值列写成 TEXT——下游若直接
`AVG(height_cm)` 会得到按文本排序的聚合或静默错误。审计必须在统计之前识别这种口径。

## affinity 判定规则（官方 §3.1，按声明类型子串匹配）

| 声明类型包含 | affinity |
|---|---|
| `INT` | INTEGER |
| `CHAR` / `CLOB` / `TEXT` | TEXT |
| `BLOB` 或空 | BLOB |
| `REAL` / `FLOA` / `DOUB` | REAL |
| 其他（`NUMERIC`、`DECIMAL`、`DATE`…） | NUMERIC |

## 审计动作（source_audit.py 实现）

1. `SELECT name, sql FROM sqlite_master WHERE type='table'`：列出全部用户表与建表语句。
2. `PRAGMA table_info(<table>)`：取每列声明类型 → 按上表映射 affinity。
3. **numeric-in-text 陷阱**：affinity=TEXT 且 ≥95% 非缺失值可解析为 float
   （缺失 token 不计入分母）→ 标记 `numeric_in_text=True`，写 warning。
   比对与统计解析按数值处理，但结论标注 `consistent_with_type_coercion`，
   并在 result.json 的 `uncertainty` 中保留"若原口径是字符编码需人工确认"。
4. 反向陷阱：affinity=REAL/INTEGER 但混入文本值 → 这些值在逐值比对时按字符串比，
   不一致会体现在 mismatch 计数中。

## 值规范化（跨源比对口径）

- `NULL` → `""`（与 CSV 缺失 token 等价）；
- float 且为整数值 → 整数字符串（`28.0` ↔ CSV `"28"` 判一致）；
- 其余 float → `repr` 最短表示；
- TEXT → 原样。

## 实操清单

- 接到 .db 先做 `PRAGMA table_info`；把建表 SQL 抄进审计结果。
- 第一个用户表（按表名字典序）是默认主表；多表时全部列表入档，主表选择写入审计。
- 不要用 `typeof()` 逐值猜类型代替 affinity 审计——两者回答的问题不同：
  affinity 是"列的口径"，typeof 是"这个值实际落了什么类型"，审计两者都要看（本 Skill 以列口径为主）。
