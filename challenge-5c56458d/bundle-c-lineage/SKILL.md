---
name: row-lineage-exporter
description: Export query results from a scientific SQLite snapshot with row-level lineage so every reported number can be independently recomputed. Use when a case requires verifiable aggregates — grouped statistics with the contributing source-row keys attached, typed CSV export, verbatim SQL retention, and an independent recompute audit that catches wrong join keys, fan-out and silent filter drift. 结果抽取与行级溯源：聚合数字可回查原始行、可独立复算。
---

# Row Lineage Exporter：结果抽取与行级溯源

本 Skill 的重心是**交付的每个数字都能回查到原始行**。题目点名的失败模式"交付的表格无法回查到原始查询"在这里被结构性消除：聚合结果附带贡献行键清单，复算脚本绕过 GROUP BY 独立重算并比对，错连接键、行数膨胀、过滤漂移都会在 MISMATCH 中现形。

## 运行约定（先读）

先读 `/input/case.json` 与 `/input/task.md`。`/app/output/result.json` 必须含原始 `case_id` 与 `output_contract` 全部字段；**先写 `status: "partial"` 兜底版本再逐步改进**（预算约 900 s / 64 次请求）。工作目录 `/app/work`。数据库一律只读。技能目录解析：`/skills/weekly-skill` → `$WEEKLY_SKILL` → 本文件所在目录。

## 工作流

1. **契约兜底**：partial result.json。
2. **缺失/重复预审计**：按 `references/sql_templates.md` T3 用 `scripts/run_query.py` 跑总行数、逐列 NULL 数、重复键清单，写入 analysis_notes；重复记录与缺失的处置（保留/剔除及理由）必须先声明再统计。
3. **溯源化聚合**：把题目的统计需求写成 query spec JSON（见 `references/lineage_contract.md`），运行 `python <skill>/scripts/lineage_export.py --db <库> --spec spec.json --tag q1 --outdir /app/work`，得到 CSV + lineage.jsonl + run.json（含逐字 SQL）。每个分组聚合一个 tag。
4. **非聚合查询**：直接用 `python <skill>/scripts/run_query.py --db <库> --sql q.sql --tag t --outdir /app/work`，SQL 原文、库 sha256、行数、列类型随 CSV 一起留痕。
5. **独立复算**：对每个 lineage tag 运行 `python <skill>/scripts/recompute.py --db <库> --tag q1 --outdir /app/work`。**只有 PASS 的数字才允许进入 result.json**；MISMATCH 时回查 spec/SQL，禁止手改 CSV 对齐。
6. **交付**：result.json（complete）+ 全部 tag 三件套 + recompute 报告 + analysis_notes.md（口径、缺失/重复处置、异常清单、未覆盖部分）。

## 异常处理

| 情况 | 处置 |
|-|-|
| 表无唯一标识列 | 声明后用 `rowid` 作 key，并在 run.json 与 notes 中注明。 |
| 单分组超过 5000 行 | lineage 退化为 digest；recompute 标注 skipped，报告中声明该组复算未覆盖。 |
| recompute MISMATCH | 停止交付该数字；检查连接键/过滤条件/NULL 处理，修正 spec 后重跑；把"错误→原因→修复"写入 notes。 |
| 空结果集 | 按模板 T5 逐条件放宽定位原因并报告；不删条件"修复"。 |
| 连接后行数膨胀 | 按模板 T1 对账；先把多侧表聚合到连接粒度再连接；膨胀原因写 notes。 |

## 附带脚本与资源

- `scripts/run_query.py` — 只读 SELECT 执行器：SQL 原文 + 库 sha256 + 行数 + 列类型 + CSV 留痕；非 SELECT 拒绝执行。
- `scripts/lineage_export.py` — spec 驱动的分组聚合导出三件套（CSV/lineage/run）。标识符经 schema 校验，函数白名单。
- `scripts/recompute.py` — 独立复算审计：逐 key 取原始行、纯 Python 重算、PASS/MISMATCH 报告。
- `references/lineage_contract.md` — 溯源格式契约 v1（spec、三件套、复算纪律）。
- `references/sql_templates.md` — 行数对账、缺失/重复审计、类别计数、空结果定位模板。

## 最小调用示例（合成示例，非正式案例结果）

合成输入：脚本自建 `lab.db`（表 `measurements`：sample_id、group_id、metric，含一条 NULL metric 与一条重复 sample_id），spec 按 group_id 求 COUNT 与 AVG(metric)。执行：

```
python <skill>/scripts/lineage_export.py --db lab.db --spec spec.json --tag q1 --outdir work
python <skill>/scripts/recompute.py --db lab.db --tag q1 --outdir work
```

示意输出（示例，非正式结果）：`q1.csv` 给出各组 n 与均值；`q1.lineage.jsonl` 每组附贡献 sample_id 列表；`q1.recompute.json` 报告 PASS（或定位到具体分组的差异）。完整可跑脚本见 `examples/run_example.sh`。

## 边界与限制

面向单表分组聚合与≤百万行表；跨表分析先用模板 T1 控制膨胀后把连接结果落到 /app/work 的派生库再做溯源聚合；超大分组（>5000 行/组）溯源降级为 digest 并显式声明；本 Skill 保证"数字可回查"，不替代字段语义判断。
