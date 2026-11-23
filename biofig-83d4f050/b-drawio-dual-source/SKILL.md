---
name: drawio-dual-source
description: 以 draw.io (mxGraph) 为第一可编辑源、同步生成分层可手编 SVG 的双源机制图/通路图/图表工作流。图面先建成几何模型（geometry.json），同一组图元同时发射 .drawio（swimlane 区室、样式化 mxCell、T 形抑制端）与分层 SVG，并经 matplotlib 后端导出真实 PNG/PDF。编辑走 cell 级结构化操作（edit_cells.py：set-label/set-color/move-cell/set-edge-kind/add-edge/remove-cell），自动版本备份 + before/after 编辑日志，再从 mxfile 回读几何重导出。适用于生物机制图、信号通路图、真实数据图表（CSV/TSV/JSON→drawio+SVG+PNG+PDF）与已有图的保源编辑三类任务；任何绘图、改图、通路图、机制图请求均应触发。
---

# drawio-dual-source：双源机制图 / 通路图 / 图表工作流

核心思想：图 = 几何模型（`geometry.json`）。一份模型，两路可编辑源
（`.drawio` 与分层 `.svg`）同源发射，PNG/PDF 只是同一组图元的渲染结果；
编辑永远落在 `.drawio` 的 mxCell 上，再回读成几何、重新发射，全程留痕
（版本备份 + cell 级编辑日志）。不使用 LaTeX。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、材料（论文 PDF 用 `pdftotext`
  提取、数据 CSV/TSV/JSON、可能有 `artifacts/figure-workorder.json`）。
  **第一步永远先 `ls -R /input /app`，逐个读真实文件，绝不凭文件名猜测。**
- 工作目录 `/app/work`；交付物全部放 `/app/output`。
- 必须写 `/app/output/result.json`，字段：`case_id`、`status`
  （success|partial|failed，须诚实，partial 要在 exceptions 点名限制）、
  `editable_source`、`export_artifact`、`content_map`（元素→来源定位，如
  `"paper.pdf p.4 Fig.2"`、`"data.csv:log2FC"`）、`compliance_checks`、
  `exceptions`。模板见 `assets/result.template.json`，组装与校验用
  `scripts/build_result.py`，契约全文见 `references/output-contract.md`。
- 预算约 64 次模型请求 / 900 秒：**第一套完整产物一生成立即先写一版
  result.json**（可为 partial），随后再迭代改进覆盖。
- 环境可能提供 pdf-text-tool、pdf-render-tool、ocr-tool、latex-compiler、
  office-renderer、browser-automation、font-discovery、scientific-python；
  使用前用 `shutil.which` 探测，缺失时如实降级并记入 exceptions。

## 工作流程

### 阶段 0 — 读输入
`ls -R /input /app` → 读 case.json/task.md → `pdftotext` 提取论文正文
（缺 pdftotext 时试 `python3 -c "import pypdf"` 或 pdf-text-tool，仍缺则
exceptions 记 partial）→ 用 csv/json 模块读数据文件 → 若有
`artifacts/figure-workorder.json`，先读它确定编辑目标文件与要求。

### 阶段 1 — 提取 claims
从材料中提取：实体（基因/蛋白/小分子/复合物/受体）、边（激活/抑制/结合/
磷酸化/泛素化/转运）、区室（细胞外/膜/胞质/核）、数据编码（如 log2FC→
填充色）。**每条 claim 必须带来源定位**（页码+图号 / 数据文件:列名），
写进 `sources` 或实体/边的 `source` 字段；方向或关系没有直接证据的边：
`"evidence": "uncertain"`（虚线 + `?`）并在 exceptions 说明。

### 阶段 2 — 写 geometry.json
按 `scripts/geometry.py` 头部注释的模型格式写 `/app/work/geometry.json`
（参照 `assets/example-geometry.json` 的结构，但内容必须全部来自真实输入）。

### 阶段 3 — 发射与导出
```bash
python3 scripts/geometry.py  --geometry work/geometry.json --out work/geometry.laid.json
python3 scripts/mxgraph_write.py --geometry work/geometry.laid.json \
    --out output/figure.drawio --sidecar geometry.laid.json
python3 scripts/svg_write.py --geometry work/geometry.laid.json --out output/figure.svg
python3 scripts/mpl_export.py --geometry work/geometry.laid.json \
    --out-dir output --basename figure
```
图表类 case 改走 `scripts/build_chart.py`（见下"图表模式"）。

### 阶段 4 — 校验
```bash
python3 scripts/verify_exports.py --geometry work/geometry.laid.json \
    --drawio output/figure.drawio --svg output/figure.svg \
    --png output/figure.png --pdf output/figure.pdf \
    --color-checks work/color-checks.json --out work/verify.json
```
校验项：drawio/SVG 可被 xml.etree 解析；geometry 里每个
`entity:/edge:/compartment:` id 都在 drawio 与 SVG 中；标签文本齐全；
图例条目与实际用到的编码一致；PNG 非空、尺寸正确、PIL 像素探针核对
节点填充色/图例色票（`--color-checks` JSON：`[{"entity":"akt","expect":"#ff8800"}]`
或显式 `{"pixel":[x,y]}`，颜色取自 geometry 的实际填充）；PDF 非平凡大小。
全部结果（含 fail）照实抄进 result.json 的 compliance_checks。

### 编辑模式（第三类 case：保源编辑）
```bash
python3 scripts/edit_cells.py --drawio output/figure.drawio \
    --ops work/ops.json --edit-record work/edit-record.json \
    --reexport --geometry-out work/geometry.edited.json
# 用回读的几何重新发射 SVG/PNG/PDF
python3 scripts/svg_write.py --geometry work/geometry.edited.json --out output/figure_edited.svg
python3 scripts/mpl_export.py --geometry work/geometry.edited.json --out-dir output --basename figure_edited
python3 scripts/verify_exports.py --geometry work/geometry.edited.json ...
```
ops JSON 支持：`set-label`、`set-color`、`move-cell(dx,dy)`、
`set-edge-kind`、`add-edge(from,to,kind)`、`remove-cell`。脚本先把原文件备份到
`versions/<name>.vN.drawio`，逐 op 做存在性检查（失败如实记录不中断），把
before/after XML 片段 + UTC 时间戳追加进编辑日志；`--reexport` 调用
mxgraph_parse.py 从编辑后的 mxfile 回读几何（不支持的 cell 如实列入
`_skipped`）。评估方在 diagrams.net 里手工改过的图也用 mxgraph_parse.py
回读——GUI 保存可能剥离 data-* 属性，此时按样式推断边型，无法确定的记
uncertain + exceptions（详见 references/drawio-mapping.md 往返规则）。

### 图表模式（第二类 case：真实数据图表）
```bash
python3 scripts/build_chart.py --data /input/data.csv --kind bar \
    --x gene --y log2FC --title "…" --out-dir output --basename chart_expr \
    --content-map-out work/chart-content-map.json
```
从 CSV/TSV/JSON 读真实数据（`#` 开头为注释行；非数值即报错，**绝不编造
数值**）；轴标签/单位取自表头；柱/点/线作为同一组图元发射 drawio + 分层
SVG，PNG(300dpi)/PDF(Type 42 字体) 由 matplotlib 直接从数据绘制；
`--content-map-out` 输出每个标记→数据单元的映射片段，并入 result.json。

## 图面科学规则

- **基因斜体、蛋白正体**（gene 用 fontStyle=2；图名/图注中的基因名同理）。
- 边语义必须区分：激活→实心箭头；抑制→**T 形端**（mxGraph `endArrow=bar`，
  matplotlib 画轴+垂直帽）；结合→空心箭头；磷酸化→箭头+标签 `P`；
  泛素化→箭头+标签 `Ub`；转运→虚线箭头；证据不足→虚线+`?` 且
  `evidence=uncertain`。
- 跨膜受体画成横跨膜泳道带的高矩形；区室用 swimlane 泳道，顺序
  细胞外→膜→胞质→核自上而下（布局细节见 references/layout-rules.md）。
- **方向必须有据**：每条有向边都要在 content_map 里给出文献/数据定位；
  只有相互作用没有方向证据的用 binding 或 uncertain，不猜方向。
- 数据编码（如 log2FC 蓝-白-红发散色）只改填充色，图例由实际用到的
  编码自动生成（legend layer），图例-数据一致性由 verify_exports 检查。

## 异常处理

| 异常 | 处理 |
|---|---|
| matplotlib 缺失 | mpl_export.py 输出失败 JSON、退出码 2；只交付 drawio+SVG，status=partial，exceptions 注明 |
| PIL 缺失 | 像素探针/尺寸检查记 skip，不记 fail |
| XML 解析失败（编辑目标损坏） | verify 对应检查记 fail；编辑前备份仍在 versions/，status=partial 并说明 |
| 方向/关系证据缺失 | 该边 evidence=uncertain（虚线+?），exceptions 逐条列出 |
| pdftotext / CJK 字体缺失 | 降级路径见阶段 0；无 CJK 字体时 matplotlib 警告写入摘要并记 exceptions |
| 外部工具缺失 | `shutil.which` 探测，缺失即走 stdlib 路径并记 exceptions |

## 最小调用示例

`examples/minimal_example.md` 给出基于合成资产（assets 均标注 synthetic）
的完整命令序列：geometry→drawio+SVG→PNG/PDF→verify→3 个编辑 op（set-label /
set-color / add-edge）→备份与日志→回读重导出→图表四件套→result.json。
