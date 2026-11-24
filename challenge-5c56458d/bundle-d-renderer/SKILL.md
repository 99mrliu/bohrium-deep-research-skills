---
name: chart-forge-renderer
description: Render analysis results from scientific database cases into deterministic, audit-grade figures. Use when a case requires visualization — chart-type selection by explicit rules, headless reproducible PNG rendering with a machine-readable figure spec, and captions that carry n, units, source query and caveats. 下游渲染工程：图表选择规则、确定性渲染、可审计图注。
---

# Chart Forge Renderer：科研结果的确定性渲染工程

本 Skill 的重心是**下游可视化交付质量**。查询正确但图表误导（截断轴、错图型、无单位、无法复现）同样让结果进不了科研流程。这里图型由显式规则选出且命中规则留痕，渲染确定性可复现，图注由产物元数据自动生成——图、数、文三者不会脱节。

## 运行约定（先读）

先读 `/input/case.json` 与 `/input/task.md`。`/app/output/result.json` 必须含原始 `case_id` 与 `output_contract` 全部字段；**先写 `status: "partial"` 兜底再逐步改进**（预算约 900 s / 64 次请求）。工作目录 `/app/work`，最终图（PNG + figure.json + caption.md）进 `/app/output`。技能目录解析：`/skills/weekly-skill` → `$WEEKLY_SKILL` → 本文件所在目录。运行契约要求"可编辑/图示产物须附真实渲染预览"——PNG 即预览，figure.json 即可再生成源。

## 前置

图渲染的是**已经核实的结果表**（CSV，列含分组与数值）。上游数字应先通过各自的可信流程（查询留痕、复算）；本 Skill 不给未核实数字"化妆"——若输入 CSV 缺少来源元数据，图注中如实写"source not provided"。

## 工作流

1. **契约兜底**：partial result.json。
2. **图型选择**：`python <skill>/scripts/chart_select.py --csv result.csv --question "<任务问题>" --out work/chart_recommendation.json`。推荐含命中规则号（`references/chart_rules.md` R1–R6）；分析者可否决，但否决理由写进 notes。
3. **确定性渲染**：`python <skill>/scripts/render_chart.py --csv result.csv --type <图型> --x <列> --y <列> [--group <列>] --y-unit <单位> --title "..." --out work/fig1`。产出 `fig1.png`（预览）与 `fig1.figure.json`（可再生成规格）。matplotlib 缺失时脚本报错并如实降级为表格交付，不伪装出图。
4. **审计图注**：`python <skill>/scripts/figure_caption.py --figure work/fig1.figure.json [--run work/q1.run.json] [--caveat "..."] --out work/fig1.caption.md`。图注自动携带 n、单位、来源查询/库哈希、注意事项。
5. **自检**：逐图核对——轴标签含单位？条形图 y 轴从零？图注 n 与结果表行数一致？PNG 确实生成且非空（字节数在 figure.json 中）？
6. **交付**：result.json（complete，图清单含路径与图注要点）+ 全部 PNG/figure.json/caption.md + analysis_notes.md（图型取舍、被否决的推荐、未覆盖部分）。

## 异常处理

| 情况 | 处置 |
|-|-|
| matplotlib 不可用 | 明确报告；交付格式化表格替代，状态标 partial 并说明限制。 |
| 类别水平 >25 | 按 R6 改表格；不硬画不可读的图。 |
| 数据跨数量级 | 图注声明对数轴；或分面；不得静默取对数。 |
| 编码型字段被请求作 y 轴 | 拒绝；改类别计数图（计数才是编码字段的合法聚合）。 |
| 中文标签字体缺失 | 标签用英文/拼音并在图注给出中文对照；不出现豆腐块乱码图。 |

## 附带脚本与资源

- `scripts/chart_select.py` — CSV 画像 × 规则 → 图型推荐（含命中规则号，可否决）。纯标准库。
- `scripts/render_chart.py` — 确定性渲染器：bar/grouped_bar/histogram/scatter/line/box → PNG + figure.json。依赖 matplotlib（Agg）。
- `scripts/figure_caption.py` — 从 figure.json/run.json 生成审计图注。纯标准库。
- `references/chart_rules.md` — R1–R6 图型选择规则与例外。
- `references/style_guide.md` — 渲染硬规范（dpi、轴、单位、禁止项）。

## 最小调用示例（合成示例，非正式案例结果）

合成输入：脚本生成 `result.csv`（三组与均值，合成数），任务"compare groups"。执行：

```
python <skill>/scripts/chart_select.py --csv result.csv --question "compare groups" --out work/rec.json
python <skill>/scripts/render_chart.py --csv result.csv --type bar --x group_id --y mean_metric --y-unit MPa --title "Mean by group" --out work/fig1
python <skill>/scripts/figure_caption.py --figure work/fig1.figure.json --out work/fig1.caption.md
```

示意输出（示例，非正式结果）：推荐命中 R1（bar）；`fig1.png` 生成（字节数记录于 figure.json）；caption 含 n=3 组、单位 MPa、来源 CSV 与"可再生成"说明。完整可跑脚本见 `examples/run_example.sh`。

## 边界与限制

面向≤数千点的结果表（更大规模先聚合/抽样并声明）；图型集合限定六种规则化图型；不替代统计推断（误差棒等须由上游提供数值后才绘制并注明估计方法）。
