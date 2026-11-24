# 最小示例（**合成示例数据**，非真实实验）

> 本示例全部数据由 `make_synthetic.py` 现场生成，仅用于演示与测试；`example_output/` 是真实跑出的文本产物。

## 输入（现场生成）

```bash
python3 examples/make_synthetic.py --out /tmp/veritas/input
```

生成 4 个文件：

| 文件 | 说明 | 预埋问题 |
|---|---|---|
| `plants.csv` | 30 行（含表头）：id,group,height_cm,notes | 2 行完全重复；3 个缺失 token（NA/空/-）；1 个 IQR 异常值（45.8） |
| `plants.db` | 同一份数据 29 行 | `height_cm` 以 **TEXT affinity** 存数值（numeric-in-text 陷阱） |
| `case.json` | output_contract 9 字段 | — |
| `task.md` | 合成示例任务（单位 cm） | — |

## 命令

```bash
SCRIPTS=/path/to/bundle-a-dataset-veritas-gate/scripts
python3 $SCRIPTS/pipeline_a.py run --input-dir /tmp/veritas/input \
    --work-dir /tmp/veritas/work --output-dir /tmp/veritas/output
python3 $SCRIPTS/source_audit.py run --input-dir /tmp/veritas/input --work-dir /tmp/veritas/work
python3 $SCRIPTS/ledger_gate.py check --input-dir /tmp/veritas/input --work-dir /tmp/veritas/work
```

## 示意输出（截取自 example_output/，真实生成）

`ledger_gate` 好例：

```
ledger_gate PASS — plants.csv
[PASS] 闭合律: rows_raw(29) == rows_kept(27) + rows_dropped(2)
[PASS] 规则重放: 原始 29 行 → 去重剔除 2 行，kept/dropped 集合与台账完全一致
[PASS] 产物哈希: cleaned_table.csv sha256=00104019aacb0240…，27 行逐行哈希全部一致
```

`result.json` 关键片段（9 字段齐全，status=ok，重复剔除 2 行，异常值标记 1 个）：

```json
{"status": "ok",
 "cleaning": {"rows_raw": 29, "rows_kept": 27, "rows_dropped": 2,
              "duplicates_removed": 2, "closure_holds": true,
              "outliers_flagged": {"height_cm": 1}},
 "hypothesis_test": {"height_cm": {"route": "GATE_2_MANN_WHITNEY", "p": "<0.0001 量级"}}}
```

`source_audit.json` 关键结论：`height_cm` affinity=TEXT 且 numeric_in_text=true；
跨源 verdict=`consistent_with_type_coercion`（值一致，类型强转后一致）。

## 埋雷演示（run_example.sh 自动断言）

1. 篡改 `cleaned_table.csv` 一个数值 → `ledger_gate` exit 1，命中 `CLEANED_HASH_MISMATCH`；
2. 篡改台账 `rows_kept` → exit 1，命中 `LEDGER_CLOSURE_MISMATCH`。

完整自测：`bash examples/run_example.sh`（11 项断言全过才 exit 0）。
