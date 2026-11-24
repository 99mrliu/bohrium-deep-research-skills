---
name: render-forge
description: 下游渲染工程取向的多步骤数据分析规程。图表不是随手画的截图而是契约产物：figure_forge.py 按"意图→唯一允许图型"渲染（组间分布必用箱线+散点叠加、排序必用零起点横条、相关必用带数值标注的 Spearman 热图），每张图带全谱系 manifest；report_forge.py 从统计 JSON 机器渲染报告骨架，并以 verify 强制正文每个 ≥3 位有效数字都能溯源到证据 JSON，无源数字阻断交付。适用于要求图表选型恰当、报告数字可回算、交付物经得起评审核对的科研表格分析案例。
---

# Render Forge —— 图与报告是契约产物，不是截图

核心主张：**分析链的最后一公里最常塌方：图型选错掩盖差异、报告数字与结果文件
两张皮。** 本 Skill 的重心是下游渲染工程：图由意图驱动、带谱系清单；报告统计小节
由机器渲染，全部数字经 verify 溯源。上游导入/清洗/统计按通用要求完成，但其产物
（cleaned 表、统计 JSON、清洗日志）是本阶段渲染与核验的唯一数据源。

## 运行契约（评测环境）

- 输入 `/input/case.json`（`case_id`、`output_contract.fields`）、`/input/task.md`。
- 工作于 `/app/work`，交付入 `/app/output`；`result.json` 含原样 `case_id` + 全部
  契约字段 + `status`/`sources`/`uncertainty`；先 partial 后增强。
- 预算约 8–12 次请求。

## 流程

**0. 读题 + 保底 partial。** 记录契约字段与任务专项。立即写 partial result.json
（case_id + 空契约字段 + status=partial）。

**1. 导入、清洗、统计（通用要求，为渲染供数）。**

- pandas 读 CSV/SQLite；双源核对一致性并声明主源；不一致写 uncertainty。
- 清洗：完全重复删（保留首条）记数；缺失 ≤5% 中位数/众数填补、>5% 保留声明；
  异常 1.5×IQR 只标记。行数变化写 `/app/work/cleaning_log.json`；cleaned 表存
  `/app/output/cleaned_data.csv`。
- 统计（前提先行：Shapiro+Levene → ANOVA/Kruskal-Wallis 等）写入
  `/app/output/statistics.json`，结构含每检验 {method, statistic, p_value,
  effect_size, premises}；连续目标补 Spearman 相关与标准化 OLS（含 R²、VIF）。
  **该 JSON 是下游渲染的唯一数字源，字段命名自定但数值必须完整。**

**2. 图表锻造（本重心）。** 写 `figspec.json`（每条 {id, intent, columns/group…}），
然后：

```
python3 /skills/weekly-skill/scripts/figure_forge.py \
    --table /app/output/cleaned_data.csv --spec /app/work/figspec.json \
    --out /app/output/figures
```

- 意图→图型映射与坐标诚实规则见 `references/render_contract.md` §1–2；
  组间案例至少一组 `group_compare`，多指标案例补 `correlation`，要求排序补
  `ranking`（labels/values 从 statistics.json 的效应量取，value_source 注明）。
- 把 `figures_manifest.json` 留在 figures/ 旁，作为 figures 契约字段的证据。

**3. 报告锻造（本重心）。**

```
python3 /skills/weekly-skill/scripts/report_forge.py scaffold \
    --stats /app/output/statistics.json --out /app/output/report.md --title "<案例标题>"
# 填写 §1 数据与清洗、§3 图表、§4 结论、§5 异常与不确定性
python3 /skills/weekly-skill/scripts/report_forge.py verify \
    --report /app/output/report.md \
    --sources /app/output/statistics.json /app/work/cleaning_log.json \
              /app/output/figures/figures_manifest.json
```

- scaffold 的统计表格数字由机器渲染，**不要手工转录改动**；填写其余小节时引用
  的任何 ≥3 位有效数字必须存在于 sources JSON 中（规则见 render_contract.md §4）。
- verify 退出码 6 = 无源数字：改回源值或补充证据 JSON；禁止删数字蒙混。

**4. result.json 收口。** 填全部契约字段：`figures` 用 manifest 中的 PNG 路径列表，
`quality_evidence` 含 figures_manifest.json、verify 的通过记录（把 verify 输出
追加存为 `/app/output/report_verify.txt`）、cleaning_log.json。`exceptions` 如实。
缺项保持空 + uncertainty + partial。

## 异常处置表

| 情形 | 处置 |
|-|-|
| 未知 intent | 查阅 render_contract.md §1；确属新意图，用 matplotlib 手工补图并在 manifest 登记（intent=custom，注明理由） |
| verify 报无源数字 | 定位数字 → 改回源值 / 把来源 JSON 加入 --sources；重跑到通过 |
| 表格列太多热图拥挤 | correlation 图按任务相关列子集绘制（≤13 列均可），spec 中注明列选择 |
| matplotlib 缺失 | 图为契约必需产物：尝试 pip 安装；失败则 partial 交付并在 uncertainty 声明 |
| 统计 JSON 结构自定 | scaffold 只认本 Skill 两种 mode；结构不符时手工写报告但 verify 仍必须通过 |

## 资源

- `scripts/figure_forge.py` — 意图驱动渲染 + 谱系 manifest（本重心）。
- `scripts/report_forge.py` — 报告骨架机器渲染 + 数字溯源 verify（本重心）。
- `references/render_contract.md` — 图型映射、坐标诚实、verify 容差与豁免规则。
- `examples/make_example.py` + `examples/README.md` — 合成示例（含篡改数字被
  verify 抓获的演示）。

## 边界与不适用

- 覆盖五种意图；地图、网络图、交互图超出范围。
- verify 保证"数字有源"不保证"语义用对"；语义由 scaffold 的机器渲染与撰写者负责。
- 非表格数据（图像、文本语料）不适用。
