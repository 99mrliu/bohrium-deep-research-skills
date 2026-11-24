# Forge Report — 产物锻造验证报告

- 生成时间（UTC）：2026-11-24T11:03:39Z
- 生成工具：docx_forge.py（纯 Python3 标准库，author=skill-agent）

## 1. DOCX 验证（round-trip proof）

### deliverable.docx

- 大小：2846 bytes
- sha256：`bc34ec576a6cb6a1cbdc0ad856b2f033c49096b141f3143eb088b757b53d04db`
- zip 完整性：通过
- document.xml 良构：通过
- 段落数（w:p）：23
- 表格数（w:tbl）：1
- 修订 w:ins / w:del：0 / 0
- round-trip 保留率：1.0000（阈值 0.99，通过；参考 token 72 / 反抽 token 72）

### deliverable_tracked.docx

- 大小：2994 bytes
- sha256：`d62cd981fbb0bd6eca509db27be3e6d1f6763870b67de350011952ff492f9b56`
- zip 完整性：通过
- document.xml 良构：通过
- 段落数（w:p）：23
- 表格数（w:tbl）：1
- 修订 w:ins / w:del：2 / 2
- round-trip 保留率：1.0000（阈值 0.99，通过；参考 token 74 / 反抽 token 74）

## 2. 修订留痕

- edit_plan 修改条数：3
- 命中：2；未命中：1

- ✅ #1 `50 摄氏度` → `60 摄氏度`（与 case.json 中示例事实B 的温度口径对齐（合成示例）。）
- ✅ #2 `但差异未做统计检验` → `且该差异未经统计检验，不得外推为因果结论`（避免把趋势描述写成因果（合成示例）。）
- ❌ #3 未命中：`反应釜编号为 RK-07`（未命中：原文片段不存在）——如实记录，未做近似替换

## 3. 预览渲染（真实渲染，未伪造）

- preview_status：`rendered_pdf_png`
- 命中渲染器：textutil+cupsfilter
- 工具探测：{"soffice": null, "libreoffice": null, "pandoc": null, "textutil": "/usr/bin/textutil", "cupsfilter": "/usr/sbin/cupsfilter", "qlmanage": "/usr/bin/qlmanage", "pdftoppm": "/Users/liuhengshen/Library/Application Support/com.bohrium.runtime/darwin-aarch64/poppler-2560d3705d5614d7/dependencies/poppler/bin/pdftoppm"}
- 说明：纯文本版式 PDF（textutil 抽取 + cupsfilter 渲染），排版与 DOCX 不同，仅供内容预览
- PDF：examples/output/preview.pdf
- PNG：examples/output/preview-1.png

## 4. 产物清单

| 文件 | 字节数 | sha256 |
|---|---|---|
| examples/output/deliverable.docx | 2846 | `bc34ec576a6cb6a1…` |
| examples/output/deliverable_tracked.docx | 2994 | `d62cd981fbb0bd6e…` |
| examples/output/review_record.csv | 567 | `976ea04c2b9c21ce…` |
| examples/output/preview.pdf | 37607 | `0bc1e8ab04d8642a…` |
| examples/output/preview-1.png | 101933 | `99afc4e77cdacf46…` |
