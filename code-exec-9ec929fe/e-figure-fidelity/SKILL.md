---
name: figure-fidelity
description: 下游渲染工程重心：图表保真与渲染证据链。当科研数据分析任务（/input 的 case.json、task.md、CSV/SQLite → /app/output 的 result.json 与图）的图表必须"能放进论文且与原始数据对得上"时使用。figkit render 强制每张图配套 .data.csv（全部绘入点）与 .receipt.json（源表 sha256、列名、绘入/排除点数、值域、轴标签原文、PNG 哈希）；figkit lint 交付前机检：列名真实性、PNG 存在且未被替换、receipt 值域与源表实测一致、轴标签单位必须出自数据字典、轴标签必须含所绘列名；figkit check 核对 result.json 的 figures 字段每项有文件与证据。无 matplotlib 时诚实降级（SKIPPED 回执 + 数据 CSV），绝不交付不存在或内容不符的图。不适用：不需要图或仅需交互式可视化的任务。
---

# figure-fidelity：每张图都带可复核的证据链

## 重心：下游渲染

图表是静默错误的重灾区：轴标签单位与数据字典不符、图例错位、被排除的缺失点无人知晓、渲染库缺失时交付一张上次的旧图。本 Skill 把图变成**带证据的工件**：PNG + 数据 CSV + 回执 JSON 三件套，交付前机检门拦截不一致。

## 固定路径与运行契约

- 工具：`/skills/weekly-skill/scripts/figkit.py`（核心 lint/check 纯标准库；render 仅渲染步骤需要 matplotlib，缺失时自动降级）
- 输入：`/input/case.json`、`/input/task.md`、数据文件与数据字典；图交付到 `/app/output`
- result.json 必须含 `case_id`、output_contract 全部字段、`anomalies`、`provenance`；`figures` 字段的每个条目要么是有 receipt 的真实 PNG，要么是 `{"path": ..., "status": "SKIPPED_no_matplotlib", "data_csv": ...}` 的诚实降级记录
- 统计与清洗计算请用平台科学 Python 自行完成；本 Skill 只负责图与其证据链，不替你算数

## 执行协议

### 画图：render（每张图一次）

```bash
python3 /skills/weekly-skill/scripts/figkit.py render \
  --table /app/work/clean.csv --kind hist --x strength \
  --title "抗压强度分布" --xlabel "strength (MPa)" --bins 20 \
  --out /app/output/fig1.png
# kind ∈ hist | scatter(--y) | bar | line(--y)
```

强制规则：**轴标签必须带单位，单位必须抄自数据字典**（不是记忆中的单位）。receipt 记录绘入点数与排除缺失点数——排除点必须能在 anomalies 中对上。

### 交付前机检：lint

```bash
python3 /skills/weekly-skill/scripts/figkit.py lint \
  --receipts /app/output/*.receipt.json --dictionary /input/data_dictionary.json
```

机检项：receipt 声称的列真实存在于源表；PNG 存在、非空、哈希未被替换；receipt 值域与源表实测值域一致（防"图换了数据没换回执"）；轴标签中的单位能在数据字典中找到；轴标签包含所绘列名。任一违例 exit 1——修正后重跑，禁止删 receipt 蒙混。

### 收口：check

```bash
python3 /skills/weekly-skill/scripts/figkit.py check --result /app/output/result.json
```

核对 figures 字段每项：PNG 存在且配 receipt；SKIPPED 项配数据 CSV。然后才能把图路径写进 result.json 交付。

## 异常处理原则

- matplotlib 缺失：render 自动写 SKIPPED 回执与数据 CSV；result.json 如实登记，交付继续（partial 语义由你按契约字段整体判断）。
- 单位在字典中查不到：去字典原文找；字典确实无单位时在 anomalies 写明"单位未经字典确认，取自 task.md 描述"，并在轴标签保留 task.md 原文措辞。
- 排除缺失点比例异常高（>5%）：先回清洗环节查原因，不要把高缺失数据的图当正常图交付。
- 详见 `references/figure_checklist.md`（论文级图的完整自查清单）。

## 最小调用示例（合成示例，非正式案例结果）

```bash
cd /skills/weekly-skill/examples && bash run_example.sh
```

在合成的水泥强度数据上渲染直方图与散点图（含单位 lint）、演示单位写错时 lint 拦截、演示 `FIGKIT_NO_MPL=1` 的诚实降级，最后 check 核对 result.json。示例数据人工合成，不对应任何正式案例。
