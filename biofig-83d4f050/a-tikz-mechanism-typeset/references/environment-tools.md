# 环境工具探测表与回退链

环境 `environment/resources.yaml` 声明的工具：**pdf-text-tool, pdf-render-tool,
ocr-tool, latex-compiler, office-renderer, browser-automation, font-discovery,
scientific-python**。使用前必须验证可用性（命令行工具用 `shutil.which`；
Python 库用 try-import）。本技能的脚本已内置探测与诚实降级，下表是完整清单。

## 命令行工具

| 工具 | 用途 | 探测 | 缺失时回退链 | 全缺时行为 |
|---|---|---|---|---|
| latexmk | 编译 .tex（首选，自动多遍） | `shutil.which("latexmk")` | pdflatex → xelatex | `compile_tex.py` exit 3，JSON `{success:false,error:"no latex engine"}`；技能层：status=partial，.tex 仍为 editable_source，记 exceptions |
| pdflatex | 编译 .tex | 同上 | xelatex | 同上 |
| xelatex | 编译 .tex（中文标签备选） | 同上 | — | 同上 |
| pdftoppm | PDF→PNG（首选，`-r DPI`） | `shutil.which("pdftoppm")` | pdftocairo | PNG 缺失：`export_previews.py` status=partial，PDF 仍是矢量交付物 |
| pdftocairo | PDF→PNG / PDF→SVG（`-svg`） | 同上 | PNG：pdftoppm；SVG：pdf2svg → dvisvgm | 同上；SVG 缺失仅降级，不算失败 |
| pdf2svg | PDF→SVG | 同上 | dvisvgm | SVG 跳过 + exceptions 说明 |
| dvisvgm | PDF→SVG（`--pdf`） | 同上 | — | 同上 |
| pdftotext | 标签回读 / 论文 PDF 抽取 | `shutil.which("pdftotext")` | 环境 pdf-text-tool | 校验项 skipped + exceptions；论文抽取受阻时尝试 ocr-tool |
| pdffonts | 字体嵌入校验 | `shutil.which("pdffonts")` | font-discovery（环境） | 校验项 skipped + exceptions，**不得谎报 pass** |

## Python 库（全部可选，try-import + 优雅降级）

| 库 | 用途 | 缺失时 |
|---|---|---|
| PIL | PNG 像素探针、尺寸/DPI 元数据、色块比对 | 相关校验 skipped + exceptions |
| numpy | 数据表数值核对辅助 | 用纯 stdlib（csv/statistics） |
| matplotlib | 辅助预览/测试图生成 | 不使用 |

脚本只依赖 Python 3 标准库即可运行；PIL/numpy/matplotlib 一律 try-import。

## 环境声明工具 → 本技能对应

- **pdf-text-tool**：论文 PDF 文字抽取（优先 pdftotext 命令行，二者任一即可）。
- **pdf-render-tool**：PDF 渲染预览（对应 pdftoppm/pdftocairo）。
- **ocr-tool**：扫描版 PDF 无文字层时的最后手段；OCR 结果必须在 exceptions 标注置信度风险。
- **latex-compiler**：对应 latexmk/pdflatex/xelatex。
- **office-renderer**：仅当案例材料含 docx/xlsx 时用于转读；本技能主线不依赖。
- **browser-automation**：一般不用于本技能主线；如案例要求在线素材核对可用，须记录。
- **font-discovery**：pdffonts 缺失时的字体信息回退。
- **scientific-python**：PIL/numpy/matplotlib 所在环境。

## 诚实性原则

每次探测结果（用了哪个引擎/导出器、哪些工具缺失）都要落到
`compliance_checks` 与 `exceptions` 中；缺失工具的校验项标 `skipped`
并说明"未验证"，绝不默认通过。
