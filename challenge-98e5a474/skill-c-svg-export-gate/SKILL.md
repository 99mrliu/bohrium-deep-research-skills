---
name: svg-export-gate
description: 分层 SVG 源文件纪律 + 保源编辑 + 期刊导出合规门禁。当任务要求交付"可继续编辑"的科研图稿源文件（示意图/机制图/流程图/图表）、对既有图做局部修改（改标签/换色/移动/删除元素）且不重画整图，或要求按期刊参数导出（PDF/EPS/PNG/TIFF，尺寸、分辨率、字体、线宽、色彩）并给出合规检查时使用。核心方法：SVG 是唯一事实源，但必须满足分层约定（Inkscape 可识别图层、元素稳定 id、文字保持可选中、禁止位图冒充矢量）；编辑通过外科式字符串手术只动目标元素、其余字节不动并留 diff 日志；导出前 lint 源文件、导出后逐项核验导出件（像素尺寸/DPI/文件头/字体），全部检查留报告。不适用：从论文文本抽取实体关系的语义判断（先用抽取类工具形成内容，再用本 Skill 组织源文件与导出）；位图照片的修图美化。
---

# svg-export-gate：分层源文件 + 外科式编辑 + 导出合规

## 解决什么问题

"输出只有位图、文字不可选、图层不可拆、改一个标签整图重画、导出件分辨率/
字体/线宽不合期刊要求"是交付环节的集中失败。本 Skill 把可编辑性与导出合规
变成可机器检查的门禁：

```
SVG 源文件（唯一事实源，须过 svg_lint）
   │  apply_edit.py（外科式编辑：只改目标 id，其余字节保持，留 diff）
   ▼
lint 通过的分层源文件 ──export_gate.py──► PDF/PNG/TIFF/EPS 导出件
   │                                        │ 逐项核验：尺寸/DPI/文件头/字体
   ▼                                        ▼
lint_report.json                    export_compliance.json（pass/fail）
```

与"清单驱动"或"数据绑定"路线解耦：内容对错由上游保证，本 Skill 保证文件
工程层面的可编辑、可维护、可投稿。

## 运行环境契约（平台固定案例）

1. 输入在 `/input/`：`case.json`（含 `case_id`、`output_contract`、材料清单）、
   `task.md`、材料本体（可能含待编辑的既有图 SVG/PDF/PNG）。**先读真实文件**。
2. 中间产物放 `/app/work/`，最终交付放 `/app/output/`。
3. `/app/output/result.json` 必须包含 `case_id` 与 `output_contract` 的
   **全部原始字段**，另附 `status`、`sources`、`uncertainty`、`change_log`。
4. 交付物必须含：分层可编辑源文件（SVG）+ 各目标格式导出件 + 真实渲染的
   PNG/PDF 预览 + lint/合规报告。导出后端缺失时如实降级并写明。
5. 预算约 64 次模型请求 / 900 秒：lint、编辑、导出全走脚本；先存部分结果。

## 工作流（严格按序）

### 步骤 0：建目录、读任务、探测工具

```bash
mkdir -p /app/work /app/output
cat /input/case.json /input/task.md
which inkscape rsvg-convert cairosvg chromium pdftoppm pdffonts 2>/dev/null
```

### 步骤 1：获得/整理分层源文件

- 新建图：按 `resources/layer_conventions.md` 组织 SVG——图层用
  `<g inkscape:groupmode="layer" inkscape:label="...">`（background /
  groups / relations / entities / labels / legend 按需），每个可编辑元素
  带唯一稳定 id，文字一律 `<text>`（禁止转曲、禁止截图贴字）。
- 编辑既有图：若输入是 SVG 直接 lint；若是 PDF 用 `pdftocairo -svg` 或
  inkscape 转 SVG 后 lint（转换损耗记入 uncertainty）；若是纯位图，在
  result.json 声明无法无损编辑，给出重绘建议，不得把位图包进 SVG 冒充矢量。

### 步骤 2：源文件 lint

```bash
python3 /skills/weekly-skill/scripts/svg_lint.py \
  --svg /app/work/figure.svg --out /app/output/lint_report.json
```

检查：图层结构、id 唯一性、文字是否可选中（无大段路径化文字）、是否混入
未声明的 `<image>`、viewBox 与物理尺寸、最小字号/线宽。**fail 项先修复再
继续。**

### 步骤 3：保源编辑（仅当任务要求修改既有图）

把修改写成操作单 `/app/work/edits.json`（只引用 lint 确认存在的 id）：

```json
{"edits": [
  {"op": "retext",   "id": "ent-egfr", "text": "HER2"},
  {"op": "set_attr", "id": "rel-r3",   "attr": "stroke", "value": "#B03030"},
  {"op": "move",     "id": "legend",   "dx": 0, "dy": -20},
  {"op": "delete",   "id": "ann-old"}
]}
```

```bash
python3 /skills/weekly-skill/scripts/apply_edit.py \
  --svg /app/work/figure.svg --edits /app/work/edits.json \
  --out /app/output/figure_edited.svg --log /app/output/edit_log.json
```

脚本对原始 XML 做字符串级手术：只触碰目标元素的标签区间，其余字节逐位
保持；edit_log.json 记录每处 before/after 片段；编辑后自动复 lint。
**禁止整文件重写（pretty-print 重排）——那会破坏"只改了一处"的可核验性。**

### 步骤 4：合规导出

```bash
python3 /skills/weekly-skill/scripts/export_gate.py \
  --svg /app/output/figure_edited.svg --profile generic_1col \
  --outdir /app/output --basename figure \
  --report /app/output/export_compliance.json
```

按 `resources/export_profiles.json` 的 profile（物理尺寸 mm、DPI、格式
清单、最小字号/线宽）导出 PNG/PDF(/TIFF/EPS 视后端)，并逐项核验：PNG 像素
尺寸与 pHYs DPI、PDF 文件头与（有 pdffonts 时）字体嵌入、EPS 边界盒。
未达标项 fail 并写明实测值；后端缺失记 `degraded`。

### 步骤 5：预览与 result.json

导出件本身即预览（PNG/PDF 可直接打开检查）；result.json 逐键对齐
`output_contract`，`sources` 写明源文件、编辑单、profile；`change_log`
合并编辑日志；`uncertainty` 写明转换损耗、导出降级、字体替换。

## 异常处理

| 情况 | 处置 |
|-|-|
| 输入位图无法矢量编辑 | 声明限制，给重绘建议，不伪造矢量 |
| 编辑单引用不存在的 id | apply_edit 报错并列出可用 id；不静默跳过 |
| 字体缺失 | lint 列出实际字体清单；导出报告记录替换情况 |
| 某格式导出失败 | 该格式记 degraded + 原因，其余格式继续；不谎报 pass |
| lint fail 无法修复 | 交付当前最优源文件，result.json 记 partial + 限制 |
| pdffonts 不可用 | 字体嵌入项记 unknown 而非 pass |

## 资源清单

- `scripts/svg_lint.py`：源文件结构与可编辑性检查（纯标准库）。
- `scripts/apply_edit.py`：外科式保源编辑 + diff 日志（纯标准库）。
- `scripts/export_gate.py`：多后端合规导出 + 导出件逐项核验（纯标准库，
  后端缺失如实降级）。
- `resources/layer_conventions.md`：分层/id/文字/配色组织约定。
- `resources/export_profiles.json`：期刊导出参数预设（尺寸/DPI/格式）。
- `examples/minimal_example.md`：**示意**编辑单与输出说明（非正式案例结果）。

## 边界与维护

外科编辑支持 retext/set_attr/move/delete 四种操作：retext 目标是叶子文字
元素或**只含一个 `<text>` 的 `<g>`**（如实体节点）；set_attr/move 可作用于
任意非保护元素（`<g>` 上的可继承属性会传给子元素）；delete 拒绝整层
（layer）删除，需逐元素列出；`<svg>/<defs>/<marker>/<metadata>` 受保护。
不解析 CSS 类样式（样式须内联）；EPS 导出依赖 inkscape/rsvg-convert，缺失
时降级。版本：v1.0（2026-11）。
