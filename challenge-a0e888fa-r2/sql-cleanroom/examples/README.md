# 合成示例：water_quality

**本目录全部数据均为人工编造的合成数据（synthetic, fabricated for
demonstration only），不来自任何真实实验或真实出版物，不得作为任何事实依据引用。**

## 内容

| 文件 | 说明 |
| --- | --- |
| `water_quality.csv` | 合成输入：已发表汇总表“转写件”，含注入故障——UTF-8 BOM；哨兵 `-999`、`ND`、空白单元格；`µg/mL` 与 `mg/L` 单位混写；`" w001 "` 大小写+空格近似重复行（与 W001 同键）；`Arsenic=250 µg/L` 越界值 |
| `rules/` | 四张规则 CSV（missing_tokens / unit_map / qc_bounds / key_fields），source 指向编造的数据字典与工单编号，仅作格式示范 |
| `steps.sql` | 清洗即查询脚本（模式见 `references/sql_patterns.md`） |
| `report_queries.sql` | 报告即聚合查询脚本（含强制 selfcheck） |
| `expected/` | 一次真实端到端运行的产物，供比对复现 |

## expected/ 产物清单

`load_report.json`、`query_log.json`、`cleaned.csv`、`change_log.csv`、
`issues.csv`、`quality_report.md`、`report_check.json`。

**注意：`case.db` 是 SQLite 二进制，不入包；由上述三个脚本依序重建。**

## 复现

```bash
SK=/skills/weekly-skill   # 或本 bundle 的本地路径
cd "$(mktemp -d)"
python3 "$SK/scripts/load_raw.py" --input "$SK/examples/water_quality.csv" \
  --db case.db --report load_report.json
python3 "$SK/scripts/run_steps.py" --db case.db --rules "$SK/examples/rules" \
  --steps "$SK/examples/steps.sql" --log query_log.json
python3 "$SK/scripts/export_report.py" --db case.db \
  --queries "$SK/examples/report_queries.sql" --outdir out
```

预期：三条命令退出码均为 0；`cleaned.csv` 中 Lead 已统一为 µg/L（0.0125 µg/mL
→ 12.5 µg/L），近似重复行只保留 line_no 最小者；`issues.csv` 含 Arsenic 越界行
与 duplicate_removed 登记；`quality_report.md` 数字与 `report_check.json` 的独立
重算逐项一致。逐文件比对方法见 `SKILL.md` 第 6 节。
