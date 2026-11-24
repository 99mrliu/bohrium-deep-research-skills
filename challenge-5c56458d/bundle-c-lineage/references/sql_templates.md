# 可溯源查询模板（SQL templates）

以下模板与 `scripts/run_query.py` / `scripts/lineage_export.py` 配套。
占位符用 `<...>` 标出；所有语句只读。

## T1 行数对账（join 前后）

```sql
SELECT COUNT(*) AS n_left FROM <left_table>;
SELECT COUNT(*) AS n_joined
FROM <left_table> l JOIN <right_table> r ON l.<k> = r.<k>;
-- n_joined > n_left 即发生扇出膨胀：先聚合右表到连接粒度再连接。
```

## T2 分组聚合（等价的 lineage_export spec）

```sql
SELECT <group_col>, COUNT(*) AS n, AVG(<measure>) AS mean_<measure>
FROM <table>
WHERE <filter>
GROUP BY <group_col>
ORDER BY <group_col>;
-- 等价 spec: {"table":"<table>","key":"<id>","group_by":["<group_col>"],
--   "aggregates":[{"func":"COUNT","column":"*","as":"n"},
--                 {"func":"AVG","column":"<measure>","as":"mean_<measure>"}],
--   "where":"<filter>"}
```

## T3 缺失/重复审计（先于统计）

```sql
SELECT COUNT(*) AS total,
       SUM(CASE WHEN <col> IS NULL THEN 1 ELSE 0 END) AS null_<col>
FROM <table>;
SELECT <key>, COUNT(*) c FROM <table> GROUP BY <key> HAVING c > 1;
```

## T4 类别计数（编码字段唯一合法的聚合）

```sql
SELECT <coded_col>, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM <table>), 2) AS pct
FROM <table> GROUP BY <coded_col> ORDER BY n DESC;
```

## T5 空结果定位（逐条件放宽）

```sql
SELECT COUNT(*) FROM <table>;                                  -- 全量
SELECT COUNT(*) FROM <table> WHERE <cond1>;                    -- 仅条件1
SELECT COUNT(*) FROM <table> WHERE <cond1> AND <cond2>;        -- 逐步加回
-- 报告每个步骤的行数，定位导致空结果的条件；不得删除条件"修复"。
```
