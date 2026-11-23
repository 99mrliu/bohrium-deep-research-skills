---
name: figure-audit-loop
description: 以"主张表↔图面"机器可检审计为核心的闭环绘图工作流：先从论文/数据中提取带来源定位的主张表（claims.json），绘图后经 SVG 回解析、像素探针、图例-数据一致性、导出质量等多重独立审计，违例驱动有界修复循环（≤3 轮，全程记录 fix_journal），未解决项如实写入 result.json exceptions。适用于生物机制图与通路图绘制、数据图表生成、以及已有图件的保源编辑任务。
---

# 生物机制图与通路图 —— 审计主导的闭环 QA 工作流

本技能的核心不是"怎么画图"，而是**怎么证明图画对了**：先提取机器可检的主张表，
再由独立审计电池回读产物、比对主张、探测像素、核对导出质量，违例驱动有界修复，
未解决项诚实入账。绘图本身可用任何方式（附 `scripts/mini_svg_builder.py` 作为
最小便利实现）。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、材料（论文 PDF 用 `pdftotext` 转文本、
  数据文件、可能存在的 `artifacts/figure-workorder.json`）。先 `ls -R /input /app`，
  读真实文件，**一切内容必须源自实际输入**；示例仅见 `assets/claims.example.json`
  （标注 synthetic）。
- 工作目录 `/app/work`；交付物 `/app/output`。
- **必须写 `/app/output/result.json`**，字段：
  `case_id`、`status`（success|partial|failed，诚实）、`editable_source`、
  `export_artifact`、`content_map`（元素→来源定位）、`compliance_checks`、
  `exceptions`。契约细节见 `references/output-contract.md`。
- 预算 ~64 请求 / 900s：**先写部分 result.json（status=partial）保底**，再迭代改进。
- 环境工具：pdf-text-tool、pdf-render-tool、ocr-tool、latex-compiler（本技能不使用
  LaTeX/mxGraph）、office-renderer、browser-automation、font-discovery、
  scientific-python。外部命令行工具（pdftotext/pdftoppm/pdffonts/tesseract）用
  `shutil.which` 自动探测：**缺失则该检查记 skipped-with-note，绝不崩溃、绝不伪报通过**。

## 闭环协议（阶段 0–6）

### 阶段 0：读输入
`ls -R /input /app`；读 case.json / task.md / workorder；PDF → `pdftotext` 文本；
数据文件直接读。确定 case 类型：(1) 论文→机制图；(2) 数据→图表；(3) 保源编辑。

### 阶段 1：提取主张表 claims.json
按 `assets/claims.schema.json` 建模，写入 `/app/work/claims.json`：
- `entities[]`：id / label / type（gene|protein|complex|small_molecule|cell_type|other）
  / compartment / **source（来源定位：页码、图号、句子、数据文件行列）** / 可选 encodings 数值；
- `edges[]`：id / from / to / kind（activates|inhibits|binds|phosphorylates|
  ubiquitinates|transports|recruits|modifies）/ evidence（confirmed|uncertain）/ source。
  **方向或效应无据 → `uncertain`（虚线），不得编造确定性**；
- `encodings[]`：channel（fill|size|width）/ field / scale / source；
- `legend[]`、可选 `expected_labels[]`、`color_checks[]`；
- 编辑类 case 额外写 `edit_expectations{changed_elements, unchanged_sample}`。

### 阶段 2：绘图（任意方式）
可用 `scripts/mini_svg_builder.py --claims claims.json --out figure.svg`（分带区室
布局：激活箭头、抑制 T 杠、uncertain 虚线、P/Ub 徽章、由 encodings 生成图例色块），
也可手写 SVG / matplotlib+svg / 其他工具。**唯一硬性要求：产物遵守
`references/svg-conventions.md`**（`entity:<id>` / `edge:<id>` / `data-edge-kind` /
`data-from`/`data-to` / `legend-swatch:<item>` 等），否则审计器无法回读。

### 阶段 3：导出 PNG/PDF
任何导出器均可；便利脚本 `scripts/export_with_mpl.py`（matplotlib，PNG 300dpi 带
元数据，PDF 内嵌字体）。PNG 需 ≥150dpi；PDF 字体需嵌入、文本不可轮廓化。

### 阶段 4：审计电池（一键全跑）
```
python3 scripts/audit_run.py --claims /app/work/claims.json \
    --svg /app/output/figure.svg --png /app/output/figure.png \
    --pdf /app/output/figure.pdf \
    [--before-svg /input/materials/before.svg] \
    --out /app/work/audit
```
依次运行：SVG 回解析（figure_graph.json）→ 语义差异（claims↔图：实体缺失/多余、
边端点与方向、边类型、图例项、标签在场性）→ PNG 像素探针（非空、尺寸、背景、
color_checks 采样比对、tesseract 可选 OCR）→ 导出质量（存在性、DPI、PDF 页数/
内嵌字体/文本层、SVG 良构性与可编辑性）→ 编辑前后对拍（编辑类）。
产出 `/app/work/audit/audit_report.json`，含
`summary{errors,warnings,skipped}` 与逐条 `violations`（带 claims 来源定位）；
有 error 时退出码 1。审计项与通过标准详见 `references/audit-rubric.md`。

### 阶段 5：修复循环（≤3 轮）
读 audit_report.json → 写修复 ops（JSON 列表）→
```
python3 scripts/fix_loop.py --svg figure.svg --claims claims.json \
    --ops ops.json --workdir /app/work/fix [--png .. --pdf .. --before-svg ..]
```
支持 ops：`rename-label` / `set-edge-kind` / `set-edge-endpoints` /
`swap-edge-direction` / `set-edge-evidence` / `add-legend-item` /
`remove-legend-item` / `set-fill`。每个 op 带存在性检查；每轮自动重跑全套审计并
追加 `fix_journal.json`；≤3 轮或 0 error 即停；**残留违例绝不隐藏**。

### 阶段 6：写 result.json
```
python3 scripts/build_result.py --case-id <id> --status <...> \
    --editable-source /app/output/figure.svg --editable-source /app/work/claims.json \
    --export-artifact /app/output/figure.png --export-artifact /app/output/figure.pdf \
    --content-map content_map.json --compliance compliance.json \
    --exceptions exceptions.json --out /app/output/result.json
```
`content_map` 覆盖每个实体/边/编码/图例项的来源定位；`compliance_checks` 逐条照抄
审计结论（**skipped 如实写 skipped**）；`exceptions` 收全部未解决项。
exceptions 非空时 status 会被自动降为 partial。

## 异常处理原则

- 审计器/工具自身失败 → 记 `skipped`（附原因），**绝不当成通过**；
- 方向/效应在材料中无依据 → `evidence: uncertain`，图面虚线，并在 exceptions 说明；
- 修复 3 轮仍有 error → `status: partial`，残留违例逐条进 exceptions；
- 声明的产物文件在磁盘上不存在 → build_result.py 强制 partial 并记录；
- 任何"看起来对但没验证"的内容，要么验证，要么进 exceptions。

## 图面科学规则

- **基因斜体、蛋白正体**；复合体、小分子、细胞类型用不同底色区分（图例说明）。
- 边语义：activates=实心箭头；inhibits=T 杠（红）；binds=无箭头直线；
  phosphorylates=箭头+`P` 徽章；ubiquitinates=箭头+`Ub` 徽章；transports/recruits/
  modifies=箭头。证据不足一律虚线。
- 跨膜蛋白放 `membrane` 带；区室用分带矩形表示并标注名称；跨区室边允许跨越带边界。
- 所有数值（表达量、log2FC 等）必须可溯源到数据文件的具体列/行，写进
  content_map；图例色标与节点填充必须一致（color_checks 像素级核验）。

## 最小调用示例（合成数据，仅演示）

```bash
# 端到端：claims -> SVG -> PNG/PDF -> 审计 -> （必要时）修复 -> result.json
python3 scripts/mini_svg_builder.py --claims assets/claims.example.json --out work/figure.svg
python3 scripts/export_with_mpl.py --claims assets/claims.example.json \
    --png work/figure.png --pdf work/figure.pdf
python3 scripts/audit_run.py --claims assets/claims.example.json \
    --svg work/figure.svg --png work/figure.png --pdf work/figure.pdf --out work/audit
echo $?   # 0 = 无 error
```
完整逐步示例（含故意破坏→审计抓出→ops 修复→复验清零）见
`examples/minimal_example.md`。

## 文件清单

- `assets/claims.schema.json` — claims.json 的 JSON Schema
- `assets/claims.example.json` — 合成玩具示例（标注 synthetic）
- `assets/result.template.json` — result.json 模板
- `scripts/svg_conventions.py` — 约定常量 + 共享解析助手（纯 stdlib）
- `scripts/mini_svg_builder.py` — 便利绘图器（非本技能重点）
- `scripts/export_with_mpl.py` — 便利导出器（matplotlib，可选）
- `scripts/audit_svg_parse.py` / `audit_semantic_diff.py` / `audit_pixels.py` /
  `audit_exports.py` / `audit_edit_diff.py` — 审计器
- `scripts/audit_run.py` — 一键跑全套审计
- `scripts/fix_loop.py` — 有界修复循环
- `scripts/build_result.py` — result.json 组装与校验
- `references/svg-conventions.md` / `audit-rubric.md` / `output-contract.md`
- `examples/minimal_example.md` — 合成端到端示例
