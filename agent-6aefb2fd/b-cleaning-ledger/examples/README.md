# 最小调用示例（合成示例 / SYNTHETIC EXAMPLE）

> 本示例使用程序生成的玩具数据（30+3 行 2 列，与任何正式案例无关），仅用于说明
> 接口与流程；其输出**不是**正式案例结果。

## 运行

```
python3 examples/make_example.py /tmp/cl-example
```

## 示例做了什么

1. 生成 `raw_toy.csv`：30 行基础数据 + 3 条完全重复行；x 列 1 个缺失（3.3% ≤5%
   阈值）、1 个极端值 999.0；y 列 1 个缺失。
2. `clean_ledger.py`：R2 删除 3 条重复；R4 填补 2 格（x 中位数、y 众数）；R5 标记
   999.0 但保留该行；台账恒等式 33−30=3 配平。
3. `ledger_check.py`：独立重算与台账一致，通过。
4. 把台账中 R2 的删除数篡改为 2 后再跑复核 → 退出码 5，stderr 指出 R2 不符；
   恢复台账后复核重新通过。

## 预期打印（节选）

```
CLEAN_LEDGER_STATUS: ok rows 33->30 removed=3 imputed_cells=2 outlier_flags=1 balanced=True
CHECK OK: 33->30 行，删除 3 重复，填补 2 格，999.0 被标记且未删除，台账配平
LEDGER_CHECK_STATUS: ok independent recompute matches ledger for 'toy'
LEDGER_CHECK_FAIL: R2 登记删除 2，独立重算为 3
CHECK OK: 篡改台账被独立复核抓获（退出码 5）
SYNTHETIC EXAMPLE PASSED -> /tmp/cl-example
```
