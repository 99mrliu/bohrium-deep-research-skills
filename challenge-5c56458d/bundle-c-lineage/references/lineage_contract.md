# 行级溯源契约（lineage contract）v1

本契约规定"每个聚合数字都能回查到贡献它的原始行"的交付格式。

## 查询规格（query spec JSON）

```json
{
  "table": "源表名",
  "key": "源行标识列（唯一，可为 rowid 别名）",
  "group_by": ["分组列1", "..."],
  "aggregates": [{"func": "AVG|SUM|COUNT|MIN|MAX", "column": "列名或*", "as": "输出名"}],
  "where": "可选过滤条件（原文保留，属口径的一部分）"
}
```

标识符必须存在于真实 schema（脚本校验）；聚合函数白名单
COUNT/SUM/AVG/MIN/MAX；`COUNT(*)` 是唯一允许 `*` 的形式。

## 交付三件套（每个 tag 一组）

1. `<tag>.csv` — 结果集：分组列 + 聚合列，列名与 spec 的 `as` 一致。
2. `<tag>.lineage.jsonl` — 每行一个分组：
   `group`（分组键值）、`aggregates`（导出值）、`source_rows`（贡献行数）、
   `source_keys`（贡献行的 key 列表；超过 5000 行时退化为
   `source_keys_digest`，即排序后 key 列表的 sha256）。
3. `<tag>.run.json` — 运行记录：实际执行的 SQL 原文、key 抽取 SQL、
   spec 原文、耗时、分组数。

## 独立复算（audit）

`scripts/recompute.py` 不使用 GROUP BY：按 lineage 中的 `source_keys`
逐组取回原始行，用纯 Python 重算每个聚合，与 CSV 导出值比对
（相对容差 1e-9）。输出 `<tag>.recompute.json`：PASS / MISMATCH 及
逐项差异。digest-only 的大分组标注 `groups_skipped_digest_only`，复算
覆盖不到它们是已知限制，须在报告中声明。

## 纪律

- CSV 中的任何数字必须等于 recompute 的同组同聚合值；不一致即
  MISMATCH，禁止手工改 CSV 对齐——应回查 SQL/spec。
- 过滤条件（where）写进 spec 才算数；口头说明不构成口径。
- 无唯一标识列的表：先说明，用 `rowid` 作 key 并在 run.json 注明。
