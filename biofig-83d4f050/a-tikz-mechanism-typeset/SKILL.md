---
name: tikz-mechanism-typeset
description: 将生物机制图/通路图材料（论文 PDF、数据表、编辑工单）转为排版级 TikZ/pgfplots 图源文件（人类可读的 .tex），用 LaTeX 引擎编译为 PDF 并导出 PNG/SVG，经 pdffonts/pdftotext/像素探针等程序化校验后交付。编辑场景采用结构化文本补丁（apply_tex_edit.py），每次修改自动版本备份并写编辑日志。当任务要求绘制或修改生物机制图、通路图、信号转导图，或要求从真实数据文件出图，且需要可编辑源文件与导出件时触发本技能。
---

# tikz-mechanism-typeset：LaTeX/TikZ 排版驱动的生物机制图与通路图

本技能的**可编辑源文件是 .tex**（机制图用 TikZ，数据图用 pgfplots），不是位图、不是 Python 生成的 SVG。
交付链：`材料 → 提取(claims.json) → 编写 .tex → 编译 PDF → 导出 PNG/SVG → 程序化校验 → result.json`。
所有产物必须在运行时从真实案例输入派生；`assets/example-*.tex` 仅为合成示例，严禁当作案例答案提交。

## 1. 运行契约（Runtime Contract）

- 输入：`/input/case.json`、`/input/task.md`；材料可能含论文 PDF、数据表（CSV/TSV/JSON）、`artifacts/figure-workorder.json`。
- **第一步永远是 `ls -R /input /app`**，然后逐个**读取真实文件内容**，绝不凭文件名猜测内容。PDF 是原始 PDF：用 `pdftotext`（或环境提供的 pdf-text-tool）自行抽取，没有预提取的答案层。
- 工作目录 `/app/work`；最终交付物放 `/app/output`。
- **必须**写出 `/app/output/result.json`，至少包含 output_contract 字段：
  `case_id, status, editable_source, export_artifact, content_map, compliance_checks, exceptions`
  （完整语义见 `references/output-contract.md`；模板见 `assets/result.template.json`）。
- `status` 必须诚实：`success | partial | failed`。`partial` 必须在 `limits` 字段写明缺什么、为什么。
- `content_map` 把图面关键元素（实体、边、图例条目、数值）映射到材料中的来源定位，例如 `"paper.pdf p.4 Fig.2"`、`"data.csv:log2FC row GeneD"`。
- `compliance_checks` 记录导出/校验结果（字体嵌入、DPI、标签回读、图例-数据一致性）。
- `exceptions` 记录歧义、缺失工具、未解决冲突。
- **预算**：约 64 次模型请求、900 秒、每响应 16384 token。**一旦第一份可编译的图存在，立刻写一版 partial 的 result.json，然后增量改进**——这是硬性要求，防止超时无交付。
- 三类案例都要覆盖：① 依据论文材料绘制机制/通路图；② 依据真实数据文件绘制图表；③ 对既有图做"保留源文件的编辑"（编辑工单）。

## 2. 工具探测（Tool Detection）

环境（`environment/resources.yaml`）声明了 pdf-text-tool、pdf-render-tool、ocr-tool、latex-compiler、office-renderer、browser-automation、font-discovery、scientific-python。**依赖任何工具前先验证其可用性**。
本技能脚本已内置 `shutil.which` 探测与诚实降级；探测表与回退链见 `references/environment-tools.md`。要点：

| 需求 | 首选 | 回退 | 全缺时 |
|---|---|---|---|
| 编译 .tex | latexmk | pdflatex → xelatex | 如实 partial：.tex 仍为可编辑交付物，记入 exceptions |
| PDF→PNG | pdftoppm | pdftocairo | partial，PDF 仍为矢量交付物 |
| PDF→SVG | pdftocairo -svg | pdf2svg → dvisvgm | 跳过 SVG 并在 exceptions 说明 |
| 字体嵌入校验 | pdffonts | 无 | skipped + 记 exceptions |
| 标签回读 | pdftotext | pdf-text-tool | skipped + 记 exceptions |
| 像素探针 | PIL | 无 | skipped + 记 exceptions |

## 3. 工作流程

### 阶段 0：读取输入
1. `ls -R /input /app`。
2. 读 `case.json`、`task.md`；判断案例类型（绘图 / 数据图 / 编辑工单）。
3. 论文 PDF：`pdftotext -layout paper.pdf /app/work/paper.txt`，然后阅读相关页（Figure、Results、legends）。
4. 数据文件：直接读 CSV/TSV/JSON 内容，确认列名与单位。
5. 编辑工单：读 `figure-workorder.json` 与被编辑图的源文件。

### 阶段 1：提取实体 / 关系 / 数据
把提取结果写进 `/app/work/claims.json`（机制图）或 spec 笔记（数据图），每条都带来源定位：
```json
{"entities":[{"id":"IL6R","type":"receptor","locator":"paper.pdf p.4 Fig.2"}],
 "edges":[{"from":"IL-6","to":"IL6R","relation":"binding","locator":"paper.pdf p.6 Results"}],
 "values":[{"figure_element":"bar B","source":"results.tsv:value,row group=B"}],
 "uncertain":[{"claim":"KinB acts upstream of TFc","reason":"材料未明确方向"}]}
```
- 词汇映射（中文机制词 → 边样式）：见 `references/tikz-grammar.md`（促进/激活→activate，抑制→inhibit，磷酸化→phosphorylate，泛素化→ubiquitinate，结合→bind，转运/入核→transport，募集→recruit）。
- **上下游方向必须有材料依据**；没有就用 `uncertain` 边样式（灰色虚线+?）并记入 exceptions。

### 阶段 2：编写 .tex
- 以 `assets/biopathway.tex` 为图元库：`\input{biopathway.tex}`（把库文件复制到 `/app/work` 与图同目录）。
- 机制图：先画区室带（extracellular/membrane/cytosol/nucleus，`on background layer`），跨膜受体用 `receptor` 样式并放在膜带中线上，再放置实体节点、按语义连边、最后加 legend。
- 数据图：把案例数据文件复制到 `/app/work`，用 `\addplot table[...] {data.csv}` 直接读真实数据；坐标轴标签与单位照抄数据文件；图例条目与数据列一一对应。
- 只用 tikz、pgfplots、xcolor；pgfplots 设 `\pgfplotsset{compat=1.17}`。

### 阶段 3：编译
```
python3 scripts/compile_tex.py --tex /app/work/figure.tex --workdir /app/work
```
- 输出 JSON：`{engine, success, errors[{line,message}], pdf_path}`。
- 无引擎 → exit 3 + 诚实报告，转"缺引擎"异常流程（见 §4）。
- 有错误 → 按 log 行号定位修复，**最多 3 次修复迭代**；仍失败则 partial 交付 .tex 并记录错误摘要。

### 阶段 4：导出 PNG/SVG
```
python3 scripts/export_previews.py --pdf /app/work/figure.pdf --out-dir /app/output --basename figure --dpi 300
```
- 自动探测 pdftoppm / pdftocairo / pdf2svg / dvisvgm；缺哪个如实报告哪个。
- 有 PIL 时回读 PNG 宽高与 DPI 元数据。

### 阶段 5：校验
```
python3 scripts/verify_tex_figure.py --pdf figure.pdf --png figure.png \
    --labels-file /app/work/labels.json [--legend-colors swatch.json]
```
- (a) pdffonts：所有字体必须嵌入（缺失则 skipped 并记 exceptions）。
- (b) pdftotext：期望标签逐一回读，缺失列出（labels.json 来自阶段 1 的实体/图例名）。
- (c) 像素探针：PNG 非空、探针网格 ≥2 种颜色（防空画布）。
- (d) 可选图例色块 vs 节点颜色一致性。
- 图例-数据一致：数据图的图例条目必须与数据文件列/系列逐一对应，把对比结论写进 compliance_checks 的 `legend_data_consistency`。

### 编辑模式（案例类型 ③）
用 `scripts/apply_tex_edit.py`，**绝不裸改原文件**：
```
python3 scripts/apply_tex_edit.py --tex figure.tex --ops ops.json --edit-record /app/work/edit-record.json
```
- ops 支持 `replace-label / replace-text / set-color / comment-out`，精确匹配，找不到就如实 failed。
- 修改前自动备份到 `versions/<basename>.vN.tex`（永不无备份覆盖）。
- 每次操作追加 `{timestamp, op, before_snippet, after_snippet, result}` 到 edit-record.json。
- 编辑后重跑阶段 3–5，把编辑日志路径写进 result.json 的 notes。

### 写 result.json
```
python3 scripts/build_result.py --case-id <id> --status <...> \
  --editable-source /app/output/figure.tex \
  --export-artifact /app/output/figure.pdf --export-artifact /app/output/figure.png \
  --content-map cm.json --compliance comp.json --exceptions exc.json \
  --out /app/output/result.json [--limits "..."]
```
脚本会校验合同字段并对空值告警。**第一份可编译图出现后立刻先写 partial result.json，再增量改进。**

## 4. 异常处理

- **缺 LaTeX 引擎**：如实 `status=partial`，`limits` 写明"无 latex 引擎：.tex 源已交付并通过语法自查，PDF/PNG/SVG 导出缺失"；把 .tex 复制到 `/app/output` 作为 editable_source；记 exceptions。
- **编译错误**：读 `compile_tex.py` 返回的 `errors[].line` 定位到 .tex 行修复；常见：未闭合的 `}`/环境、节点名重复、`\addplot table` 列名与数据文件不符。**最多 3 次修复迭代**，仍失败则 partial + exceptions 记录错误摘要。
- **缺导出器/校验器**：按 §2 表降级，全部记入 exceptions，绝不谎报。
- **材料歧义/冲突**（如两篇材料对方向说法矛盾）：按保守画法（uncertain 边）并记录冲突原文定位。

## 5. 图面科学规则（必须遵守）

1. **基因名斜体**（用 `\gene{...}` 或 `gene` 样式，自带 itshape），**蛋白名正体**（`protein` 样式）；磷酸化蛋白写 `p-STAT3` 形式（`\phos{...}`）。
2. **激活 → 开放三角箭头**（activate）；**抑制 → T 形横杠 ⊣**（inhibit）。不得混用。
3. **跨膜受体必须跨膜带放置**：`receptor` 样式节点中心对齐膜带中线，可用 `bilayer` pic 增强膜观感。
4. 区室自上而下：细胞外 → 膜 → 胞质 → 核；分泌配体在胞外带，转录因子入核用 `transport` 虚线箭头跨带。
5. **每条上下游方向必须有材料依据**；无依据 → `uncertain`（灰虚线+?）并在 exceptions 说明。
6. **数值必须来自数据文件**（`\addplot table` 直读，不手抄）；图注/标签文字必须能在材料中定位（content_map）。
7. 抑制、负反馈用红色系；激活用蓝色系；不确定用灰色——与 biopathway 调色板一致（色盲友好）。
8. 图必须有 legend（机制图例说明边语义；数据图例对应数据系列）。

## 6. 最小调用示例（示例 / synthetic，非真实案例结果）

完整端到端流程（含命令与预期输出）见 `examples/minimal_example.md`。
素材即 `assets/example-mechanism.tex`、`assets/example-chart.tex`、`assets/example-data.csv`——全部为合成玩具通路/数据，仅演示管线，**严禁**作为任何真实案例的交付内容。
