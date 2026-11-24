# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用程序生成的玩具数据（3 列 12 行，与任何正式案例无关），仅用于说明
> 接口与完整流程；其输出**不是**正式案例结果，不得充当正式答案。

## 运行

```
python3 examples/make_example.py /tmp/sr-example
```

## 示例做了什么

1. 在 `/tmp/sr-example/input/` 生成 `toy_snapshot.csv` 与 `toy.sqlite`（表 toy），
   植入一处单元格差异（beta 列第 7 行 17.5 vs 18.5）；双源均含一行完全重复；
   写入玩具 `case.json`（case_id=synthetic-toy-001，契约字段与正式案例同构）。
2. 运行 `source_audit.py`：对账裁为 `content_divergent`，差异定位到 beta 列第 7 行；
   主源裁决为 `toy_snapshot.csv`（双源重复行各 −1 后，快照 +2 仍高于数据库 +1）。
3. 运行 `result_ledger.py`：`init` 立即写 partial；只填一个字段后 `seal --status success`
   被**拒绝**（退出码 3，契约字段不全）；`note` 追加不确定性后以 `partial` 诚实封口，
   `sources` 自动取自审计哈希。

## 预期打印（节选）

```
SOURCE_AUDIT_STATUS: ok tables=2 pairs=1 divergent_pairs=1 primary=toy_snapshot.csv
CHECK OK: 差异定位 beta 列第 7 行；主源裁决 toy_snapshot.csv（快照 +2 对数据库 +1，重复行各 −1）
RESULT_LEDGER: init partial fields=6
SEAL_REFUSE: 契约字段为空: ['statistics', 'figures', 'report', 'quality_evidence', 'exceptions']
CHECK OK: 契约字段不全时 seal 拒绝 success（退出码 3）
CHECK OK: partial 诚实封口，sources 来自审计哈希
SYNTHETIC EXAMPLE PASSED -> /tmp/sr-example
```
