# 合成示例说明

**本目录全部数据为人工编造的合成数据，不对应正式案例，也不对应任何真实试验。**

## 文件

- `trial_table.csv`：合成临床试验风格汇总表（组别 × 指标：n、male_n、male_pct、
  responders、response_pct、age_mean、dose_mg_sum、dose_mg_mean），含小计行与合计行。
- `data_dictionary.md`：配套合成数据字典（字段含义、单位、物理界、QC 规则）。
- `constraints.json`：据字典填写的约束文件，每条带 source 定位。
- `expected/`：三个脚本的真实运行产物（未手工修饰）。

## 注入的 2 处故障

1. **合计行 n 格**：90 被改为 96（`R4C1`）。
   该格同时破坏列合计等式、两条合计行百分比等式与 mean=sum/n 等式，且它是这些
   等式中唯一的主要可疑格 ⇒ **唯一可解**，由 col_sum 反解恢复为 90。
2. **A 组与 B 组 responders 同时被改**：21→27、18→13（`R0C4`、`R1C4`）。
   列合计与小计等式各含 2 个主要可疑格 ⇒ **不可唯一解**，保留原值并写入
   digest.md 的未恢复清单。

## 复现命令

```bash
python3 ../scripts/table_scan.py trial_table.csv --out-dir /tmp/oa
python3 ../scripts/consistency_check.py /tmp/oa/structure.json constraints.json --out-dir /tmp/oa
python3 ../scripts/restore_unique.py trial_table.csv /tmp/oa/structure.json \
  /tmp/oa/equations.jsonl /tmp/oa/suspect_map.csv constraints.json --out-dir /tmp/oa
```

预期结果：命中集 = {R4C1, R0C4, R1C4}（恰好是注入的故障格）；restoration_ledger.csv
只含 R4C1 一行（96→90）；恢复后复评仍有 4 条违反等式（全部指向两个 responders
格），如实保留。
