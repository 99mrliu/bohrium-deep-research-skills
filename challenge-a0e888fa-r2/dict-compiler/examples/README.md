# examples/ —— 合成最小示例

**声明：本目录全部内容（数据字典、工单、测量数据、裁决、预期产物）均为人工
编造的合成数据，不对应任何真实实验、样品或发表结果。**

## 文件

| 文件 | 说明 |
| --- | --- |
| `dictionary.md` | 数据字典：Markdown 表 + 条目混合（字段语义、单位、哨兵、物理界、检出限）。故意留下 2 处歧义：第 13 行检出限「见附录 B」；第 18 行范围写法 `0 ~ 2000 μS/cm`（无括号波浪号，编译器不支持）。 |
| `workorder.md` | 5 条工单（缺失分类 / 单位换算 / 去重 / QC 标记 / 检出限）。 |
| `measurements.csv` | 10 行注入故障数据：哨兵 -999/ND/NA/空白、越界值、重复主键（空白+小写）、低于检出限、非数值 `abc`。`remark_note` 为故意不覆盖字段。 |
| `resolutions.json` | 对 2 个歧义行的裁决：U001 reject（附录 B 未随案提供）；U002 adjust（按字典原义补全为闭区间 [0, 2000]）。 |
| `expected/` | 真实运行产物（非手写）：draft_rules.json、parse_report.md、rules.final.json、coverage_matrix.csv、cleaned.csv、ledger.csv、digest.md。 |

## 复现（在 bundle 根目录执行）

```bash
python3 scripts/compile_dictionary.py \
  --dictionary examples/dictionary.md \
  --workorder  examples/workorder.md \
  --out examples/expected            # 退出码 0；14 条规则 + 2 条未解析

python3 scripts/validate_rules.py \
  --draft       examples/expected/draft_rules.json \
  --resolutions examples/resolutions.json \
  --data        examples/measurements.csv \
  --out examples/expected            # 退出码 0；15 条最终规则 + 1 条缺口

python3 scripts/execute_rules.py \
  --rules examples/expected/rules.final.json \
  --data  examples/measurements.csv \
  --out examples/expected            # 退出码 0；10 行 → 9 行，台账 21 条
```

## 预期要点（目检清单）

- `draft_rules.json`：每条规则带 `source.file` / `source.line` / `source.text`，
  行号与 `dictionary.md` / `workorder.md` 实际行一致。
- `parse_report.md`：逐行登记；U001（第 13 行）、U002（第 18 行）列入未解析表。
- `coverage_matrix.csv`：`remark_note` 显示 `uncovered → 原样保留`；
  字典第 13 行 `rejected`；第 18 行 `resolved → R101`；5 条工单全部 `covered`。
- `cleaned.csv`：9 行（重复主键行被丢弃）；哨兵置空；原值列保留 +
  `concentration__ug_per_L` 换算列；6 个 `__qc` 标记列。
- `ledger.csv`：21 条逐格记录，每条含 `rule_id` 与 `source_file`/`source_line`。
- `digest.md`：数字从产物重算，含 cleaned.csv / ledger.csv 的 sha256 与
  缺口/诚实声明。
