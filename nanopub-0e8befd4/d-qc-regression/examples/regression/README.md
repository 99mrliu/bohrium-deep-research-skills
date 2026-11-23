# 反例回归题集（合成示例，非正式案例结果）

`fixtures.json` 含 12 个合成已知错误：改写引文、代词主语、关系越表、来源缺失、
精确重复、数值不符、模态抹除、证据过宽、复合打包、未决冲突、缺检索范围、
asserted 无引文。每个 fixture 声明 `expect_codes`，回归要求全部被捕获。

## 运行

```
python3 SKILL_DIR/scripts/run_regression.py \
  --fixtures fixtures.json --out /tmp/regression-report.json
```

预期 `passed=12, failed=0, gate=pass`，退出码 0。本机实跑产物见
`expected/regression-report.json`。修改 qc_gate.py 后必须重跑本题集；
新增错误类型先加 fixture（先红）再实现检测（变绿）。
