---
name: data-legend-bind
description: 数据绑定式科研图表生成与图例一致性校验。当任务给出真实来源数据（CSV/TSV/JSON 表格、论文补充数据、实验记录），要求绘制柱状图/折线图/散点图等数据图表，保证图例、配色、坐标、单位与数据逐项一致，并支持改动数据后一键重绘时使用。核心方法：先冻结数据快照（sha256 存证），再写一份把每个视觉通道（颜色/图例项/坐标轴/单位）绑定到具体数据列的 figure.spec.json，由确定性脚本渲染（matplotlib，SVG 文字可编辑），最后一致性校验脚本对账：图例项↔数据分类一一对应、配色数↔分类数相等、轴标签含单位、图中文字无清单外内容、数据哈希未漂移、重绘确定性。不适用：机制图/通路图等无数据表的概念示意图（用实体-关系类工具）；统计方法选择（本 Skill 只保证图与既有数据一致，不做统计推断）。
---

# data-legend-bind：数据绑定图表与图例一致性门禁

## 解决什么问题

"图例与数据表对不上、颜色映射与分类数目不一致、改一个数整张图重画"是数据图
最常见的硬伤。根因是图是"看着数据画的"，图面元素与数据之间没有可机器核对的
绑定关系。本 Skill 把绑定关系显式化：

```
来源数据 ──freeze──► 数据快照 + sha256 存证（防止绘图中途数据漂移）
   │
figure.spec.json（视觉通道 → 数据列 的绑定声明，Agent 编写）
   │  render_chart.py（确定性渲染，不含科学判断）
   ▼
figure.svg/.pdf/.png/.tiff + legend_map.json（分类→颜色→标记 映射表）
   │  check_consistency.py（一致性门禁）
   ▼
consistency_report.json（pass/fail + 逐项明细）
```

**数据更新后重绘 = 重跑 freeze + render + check**，三步命令，无需手工改图。

## 运行环境契约（平台固定案例）

1. 输入在 `/input/`：`case.json`（含 `case_id`、`output_contract`、材料清单）、
   `task.md`、材料本体。**先读真实文件**，列名、单位、分类以数据文件实际内容
   为准，不凭文件名猜测。
2. 中间产物放 `/app/work/`，最终交付放 `/app/output/`。
3. `/app/output/result.json` 必须包含 `case_id` 与 `output_contract` 声明的
   **全部原始字段**，另附 `status`、`sources`、`uncertainty`、`change_log`。
4. 交付物必须含：可编辑源文件（SVG，`svg.fonttype='none'` 文字可编辑）+
   导出件（PDF/PNG/TIFF）+ 真实渲染预览 + 一致性报告。
5. 预算约 64 次模型请求 / 900 秒：数据探查用脚本一次完成，渲染与校验全交给
   脚本；先存部分结果再改进。

## 工作流（严格按序）

### 步骤 0：建目录、读任务、探测数据

```bash
mkdir -p /app/work /app/output
cat /input/case.json /input/task.md
python3 -c "import pandas" 2>/dev/null || python3 -c "import csv; print('stdlib csv ok')"
head -5 /input/<数据文件>   # 实际查看列名、分隔符、单位写法
```

### 步骤 1：冻结数据快照

```bash
python3 /skills/weekly-skill/scripts/freeze_data.py \
  --inputs /input/<数据文件>... --outdir /app/output/data_snapshot
```

复制来源数据并写 `data_provenance.json`（原路径、sha256、字节数）。之后一切
渲染只读快照，不读 `/input` 原件——保证图与所依据的数据版本可复核。

### 步骤 2：编写绑定声明 figure.spec.json

按 `resources/figure_spec.md` 编写 `/app/work/figure.spec.json`：图型
（bar/grouped_bar/stacked_bar/line/scatter）、x/y 绑定的数据列与单位、
分类列（决定图例项与配色数）、调色板、标题、来源快照哈希。
**图例标签只能来自数据分类列的实际取值**；数值列名必须真实存在。
期刊参数（尺寸/字号/线宽）从 `resources/journal_presets.json` 选 profile。

### 步骤 3：确定性渲染

```bash
python3 /skills/weekly-skill/scripts/render_chart.py \
  --spec /app/work/figure.spec.json --snapshot /app/output/data_snapshot \
  --outdir /app/output --basename figure --profile generic_1col
```

输出 `figure.svg`（文字可编辑）/`.pdf`/`.png`(300dpi)/`.tiff`（有 Pillow 时）
+ `legend_map.json`（分类→颜色→标记的实际映射）+ `render_log.json`。

### 步骤 4：一致性门禁

```bash
python3 /skills/weekly-skill/scripts/check_consistency.py \
  --spec /app/work/figure.spec.json --snapshot /app/output/data_snapshot \
  --legend-map /app/output/legend_map.json --svg /app/output/figure.svg \
  --out /app/output/consistency_report.json
```

校验项：spec 引用的列在快照中真实存在；图例项集合与数据分类列取值**严格
相等**（不缺、不多、顺序一致）；配色数 == 分类数；坐标轴标签含声明的单位；
SVG 中文字不含 spec 之外的内容（反幻觉）；快照 sha256 与 spec.source 一致
（数据未漂移）；重渲染两次 SVG 一致（确定性）。**fail 必须修正后重跑，不得
带病交付。**

### 步骤 5：编辑与数据更新

- 改图（换配色、改标题、调图型）：改 spec，重跑步骤 3–4，写入 change_log。
- 数据更新：替换快照数据（重跑 freeze），重跑步骤 3–4；consistency_report
  中的 `data_sha256` 变化即版本证据。所有改动追加 `/app/output/change_log.json`。

### 步骤 6：写 result.json

逐键对齐 `output_contract`；`sources` 写明数据文件、快照哈希、映射表路径；
`status` ∈ {complete, partial, failed}；`uncertainty` 写明单位存疑、分类
缺失值处理、导出降级等。

## 异常处理

| 情况 | 处置 |
|-|-|
| 数据文件缺失/无法解析 | result.json `status:"failed"` + 原因；不编造数值 |
| 分类列含缺失值 | 在 spec 声明 `dropna` 或 `na_label`，记入 uncertainty |
| 单位在数据中写不一致 | 以数据实际写法为准统一，记入 change_log 与 uncertainty |
| 图例项与分类对不上 | 以数据分类为唯一事实源修 spec；禁止手改图例凑数 |
| TIFF 导出缺 Pillow | 如实记录降级，交付 SVG/PDF/PNG |
| 数值列混入非数值 | 渲染脚本报错并列出问题行，Agent 决定剔除并记录 |

## 资源清单

- `scripts/freeze_data.py`：数据快照 + sha256 存证（纯标准库）。
- `scripts/render_chart.py`：spec→图表多格式渲染（需 matplotlib；
  TIFF 需 Pillow，缺失时自动降级并记录）。
- `scripts/check_consistency.py`：图例/配色/单位/文字/哈希/确定性门禁
  （纯标准库 + 重渲染比对）。
- `resources/figure_spec.md`：绑定声明的字段规范与示例。
- `resources/journal_presets.json`：期刊尺寸/字号/线宽预设
  （generic_1col/generic_2col/nature_1col/nature_2col）。
- `examples/minimal_example.md`：**示意**输入→spec→输出说明（非正式案例结果）。

## 边界与维护

单图分类数建议 ≤12（超出先合并或分面，并在 uncertainty 说明）；图型限
bar/grouped_bar/stacked_bar/line/scatter 五种；不做统计检验与误差棒估计
（误差棒列须由来源数据直接给出）。版本：v1.0（2026-11）。
