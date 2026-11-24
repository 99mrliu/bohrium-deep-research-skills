# 合成示例：从真实分歧到收敛的完整留痕

> **数据声明**：本目录全部内容（`lab_table.csv`、`rules.json`、`expected/` 下的所有
> 产物）均为**人工编造的合成数据**，不来自任何真实实验、真实样品或真实文献。rules
> 中的 `source` 字段（`synthetic:...`）仅为演示出处写法，指向不存在的假想文档。

## 数据陷阱设计（lab_table.csv，10 行）

| 陷阱 | 行（src_row） | 说明 |
| --- | --- | --- |
| 哨兵 `-999` | 4（GLUCOSE 重复行） | 录入缺失 → `entry_missing`，不插补 |
| 哨兵 `ND` | 5（recovery_pct）、10（concentration） | 低于检出限 → `below_detection_limit` |
| 空单元格 | 6（concentration） | 未检测 → `not_detected` |
| 真值 0 | 7（Sulfate 浓度 0） | 标记 `true_zero`，保留数值 0 |
| 单位混用 | 5、9（`μg/mL` vs `mg/L`） | 1 μg/mL = 1 mg/L，映射表 factor 1.0，只换算 `convert_units: true` 的 concentration |
| 大小写/空格近似重复 | 1 vs 4（Glucose / GLUCOSE） | 归一化同键；完整度 2 vs 1（含 -999），无平局，保留行 1 |
| **平局陷阱** | 2 vs 3（Caffeine / ` caffeine `） | 归一化同键且完整度**相同**（2 vs 2）——平局规则的试金石 |
| 越界值 | 8（99999 > 5000）、9（135% > 120%） | 保留原值 + `out_of_bounds_high` |

## round 1：先故意跑出真实分歧

`expected/round1/rules_round1.json` 故意**省略 `dedup.tie`**（平局规则留白）。
两引擎文档化的默认值相反（A 取首现、B 取末现），于是在 caffeine 平局对上合理
地选择了不同行：

- engine_row（A）保留 src_row=2（`Caffeine`, 12.5）；
- engine_col（B）保留 src_row=3（` caffeine `, 13.0）。

`expected/round1/` 留痕（均为当时真实运行产物）：

- `rules_round1.json` —— 缺平局规则的规约；
- `out_row/cleaned.csv`、`out_col/cleaned.csv` —— 两引擎各自结果（第 2 数据行不同）；
- `reconciliation_queue.csv` —— 8 条分歧：cleaned.csv 第 2 行的 src_row /
  analyte_raw / concentration / recovery_pct 四格，加上 ledger 中 caffeine 与
  glucose 去重记录里 `tie=first_occurrence`（A 默认）与 `tie=last_occurrence`
  （B 默认）字样的差异；每条都带两引擎各自台账给出的理由；
- `twin_pass_verdict.json` —— `verdict: FAIL`（diff_runs 退出码 6）。

判定（按 references/redundancy_method.md 分类学）：**规约歧义**，不是引擎缺陷——
两引擎各自自洽，分歧根源是规约没写平局规则。处置：修规约，不修引擎。

## final：修规约后收敛

`rules.json`（最终规约）补上 `"tie": "first_occurrence"`。双跑 + 对账 + 幂等：

- `expected/final/out_row/`、`expected/final/out_col/` —— 两引擎的 cleaned.csv /
  ledger.csv / summary.json **逐字节一致**（可用 `diff -r` 复核）；
- cleaned.csv 中 caffeine 保留行为 src_row=2（12.5），符合平局规则取首现；
  行 3 与行 4 均在 ledger 中记录 `dedup_drop`；
- `twin_pass_verdict.json` —— reconciliation PASS（0 分歧）+ idempotence PASS
  （重跑引擎 A 字节一致），`verdict: PASS`（退出码 0）；
- `reconciliation_queue.csv` —— 仅表头，无分歧记录。

## 复现

```bash
cd examples
# round 1（期望退出码 6）
python3 ../scripts/engine_row.py --rules expected/round1/rules_round1.json --csv lab_table.csv --outdir /tmp/r1_row
python3 ../scripts/engine_col.py --rules expected/round1/rules_round1.json --csv lab_table.csv --outdir /tmp/r1_col
python3 ../scripts/diff_runs.py --a /tmp/r1_row --b /tmp/r1_col --outdir /tmp/r1_diff; echo $?
diff /tmp/r1_diff/reconciliation_queue.csv expected/round1/reconciliation_queue.csv && echo "queue 复现一致"
# final（期望退出码 0）
python3 ../scripts/engine_row.py --rules rules.json --csv lab_table.csv --outdir /tmp/f_row
python3 ../scripts/engine_col.py --rules rules.json --csv lab_table.csv --outdir /tmp/f_col
python3 ../scripts/diff_runs.py --a /tmp/f_row --b /tmp/f_col --outdir /tmp/f_diff \
  --idempotence --engine ../scripts/engine_row.py --rules rules.json --csv lab_table.csv; echo $?
diff -r /tmp/f_row expected/final/out_row && diff -r /tmp/f_col expected/final/out_col && echo "final 复现一致"
```

## 构建本示例时发现并修复的引擎缺陷（如实记录）

双实现冗余在构建期就抓到了两个真实缺陷，修复后本目录全部产物（含 round1 留痕）
均用修复后的引擎重新生成：

1. **完整度得分把哨兵值算作“完整”**（两引擎同犯）：初版只测“可解析为有限数”，
   `-999` 是合法浮点数，导致 GLUCOSE 重复对（行 1 完整 vs 行 4 含 -999）被误判
   2:2 平局，引擎 B 依其默认错误地保留了含 -999 的行。修复：哨兵命中的单元格
   不计入完整度。
2. **单位换算作用于全部测量列**（两引擎同犯）：初版对 `recovery_pct`（无量纲
   百分比）也记录 unit_convert。修复：规约增加测量级 `convert_units` 开关，
   仅 `true` 的列参与换算。
