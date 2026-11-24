# 渲染实测方法论（render-proof）

核心主张：**XML 里的格式声明只是意图，页面上的几何才是事实。**
`w:pgMar` 写 3.17cm 不等于版心真的落在 3.17cm——样式覆盖、直接格式、
分节符、页眉侵入都会让声明与渲染结果背离。验收格式适配的终局证据
只能是渲染后的页面。

## 证据链

```
可编辑产物 (docx) --render.py--> PDF + PNG --pdf_measure.py--> measurements.json
spec.json (任何来源) ---------------+--> render_verdict.py --> verdicts + render_ledger.md
```

1. **render.py**：LibreOffice headless 转换。渲染器缺失时退出码 3 且只写
   render_status.json——必须在 result.json 的 limits 声明"无渲染证据"，
   不得把 XML 检查冒充渲染验证。
2. **pdf_measure.py**：三层证据，逐层降级：
   - `/MediaBox` 字节扫描 → 页面尺寸/页数（永远可用，stdlib）；
   - `/BaseFont` + `/FontFile[23]` 扫描 → 字体清单与内嵌启发式（永远可用）；
   - `pdftotext -bbox-layout` → 逐词字形框 → 版心边距/栏间隙（poppler 缺失时
     整体记 UNMEASURED，相关检查项不猜）。
3. **render_verdict.py**：规格 × 实测逐项裁决。边距类取逐页 min/max 区间，
   全部落容差内才 PASS。

## 判定要点与已知边界

- **字形框 ≠ 声明边距**：pdftotext 给的是字形外接框，含 ascent/descent，
  首行上沿会比声明的上边距小几磅；边距容差默认 ±0.2cm，不要用 ±0.01 装精确。
- **栏检测**要求栏缝两侧各 ≥3 个词，避免把单栏 ragged-right 空带误判成双栏；
  三栏以上、跨栏图表会误判——这类版式把 columns 项交 UNMEASURED 人工看 PNG。
- **字体内嵌是启发式**：/FontFile 流计数 ≥ 去重字体数即判 embedded_all。
  base-14 字体（Helvetica/Times 等）允许不内嵌，学术模板常用的
  Liberation Serif（组织方 revision3 指定）不在 base-14 之列，
  投稿要求内嵌时必须能在清单里看到它且带 FontFile 流。
- **UNMEASURED 不传染**：几何不可用时页面尺寸与字体检查照常出结论，
  只有依赖词框的项记 UNMEASURED 并进入 result.json 的 manual_confirm。

## 工具矩阵

| 工具 | 用途 | 缺失时 |
|---|---|---|
| soffice/libreoffice（含 SOFFICE 环境变量、常见安装位探测） | docx→pdf | render 退出 3，limits 声明 |
| pdftoppm（PDFTOPPM 环境变量） | pdf→png 预览 | 只交 PDF（status=pdf_only） |
| pdftotext（PDFTOTEXT 环境变量） | 词框几何 | 几何项 UNMEASURED |
| python3 stdlib | MediaBox/字体扫描 | 无降级，始终可用 |
