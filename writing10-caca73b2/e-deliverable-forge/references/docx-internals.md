# 最小 docx 结构说明与自验清单

.docx 本质是 ZIP 容器(OPC 包)。build_docx.py 生成的最小可用包包含 5 个成员:

## 1. 成员职责

| 成员 | 职责 |
| --- | --- |
| `[Content_Types].xml` | 声明包内各部件的 MIME 类型;必须为 document.xml 与 styles.xml 各有一条 Override,否则 Word 拒绝打开 |
| `_rels/.rels` | 包级关系表,必须有一条 `officeDocument` 关系指向 `word/document.xml` |
| `word/_rels/document.xml.rels` | 文档级关系表,至少声明 styles 关系指向 `styles.xml` |
| `word/document.xml` | 正文:`w:document > w:body > (w:p | w:tbl)* + w:sectPr`;段落用 `w:pStyle` 引用样式,表格必须带 `w:tblBorders` 才有可见框线;**表格后必须跟一个空 w:p**,否则相邻表格会粘连 |
| `word/styles.xml` | 样式定义:Normal、Heading1-3、Caption、ListParagraph;样式驱动是可编辑性的前提 |

命名空间:`http://schemas.openxmlformats.org/wordprocessingml/2006/main`(前缀 w);关系命名空间:`http://schemas.openxmlformats.org/package/2006/relationships`。

## 2. 自验清单(build_docx.py 已实现)

1. `zipfile.is_zipfile` 为真;
2. `ZipFile.testzip()` 返回 None(无 CRC 损坏成员);
3. 必备成员齐全:[Content_Types].xml、_rels/.rels、word/document.xml、word/styles.xml;
4. `xml.etree.ElementTree` 能解析 word/document.xml(Well-formed);
5. `w:p` 计数 > 0(文档非空);统计 `w:tbl` 数量并与源稿表格数核对;
6. 打印字节数与 sha256,写入 build_manifest.json 供复核。

## 3. 常见损坏原因

- **XML 未转义**:正文中的 `&`、`<`、`>`、引号直接写入 w:t,导致 document.xml 不可解析(本脚本统一经 `html.escape(s, quote=True)` 处理);
- **缺 Content_Types Override**:zip 完好但 Word 报"无法打开,内容有问题";
- **关系 ID 冲突或悬空**:rels 中 Target 不存在;
- **表格无结尾段落**:文档以 w:tbl 结尾缺少 w:p,部分解析器报错;
- **编码声明不符**:XML 声明 UTF-8 但写入字节为其他编码;
- **样式引用未定义**:w:pStyle 指向 styles.xml 中不存在的 styleId(多数查看器能容忍,但应避免)。

## 4. 降级策略

docx 构建或自验任一环节失败时(build_docx.py 退出码 2):

1. 原样写出 `manuscript.md`(内容与定稿逐字节一致);
2. 写出 `manuscript.html`(同内容的简易 HTML 渲染,可直接浏览);
3. build_manifest.json 记 `status: fallback` 与失败原因;
4. 调用方在 result.json 中置 `status: partial`,并在 uncertainty 中说明 docx 未交付的原因;
5. 交叉引用审计与 SVG 预览不依赖 docx,可照常完成并交付。
