# OOXML / Markdown 子集支持范围与已知限制

docx_forge.py 用纯 Python3 标准库手写最小 OOXML 包。本文档列出支持范围与限制，
帮助你在成稿时只用"编译得动"的语法。

## 1. DOCX 包结构（5 个部件）

| 部件 | 作用 |
|---|---|
| `[Content_Types].xml` | 声明 rels/xml 默认类型与 document/styles 的 Override |
| `_rels/.rels` | 包级关系：指向 word/document.xml |
| `word/_rels/document.xml.rels` | 文档级关系：指向 styles.xml |
| `word/document.xml` | 正文（段落 / 表格 / 修订） |
| `word/styles.xml` | Normal、Heading1–3、ListParagraph、TableGrid 样式；docDefaults 中声明 Times New Roman + SimSun（正文）、Arial + 等线（标题） |

中文字体**只声明不内嵌**：打开文件的机器有 SimSun/等线即用之，没有则由 Word/WPS
自动替换字体，不影响打开与编辑。

## 2. Markdown 子集 → OOXML 映射

| Markdown | OOXML | 说明 |
|---|---|---|
| `# / ## / ###` | `w:pStyle` Heading1/2/3 | 仅支持到三级标题 |
| 普通段落 | `w:p`（Normal） | 连续非空行合并为一个段落（软换行 → 空格） |
| `- item` / `* item` | ListParagraph + 字面 `• ` 前缀 | **不是**真正的 numbering.xml 编号列表（见限制） |
| `\| 表格 \|` | `w:tbl` + TableGrid 样式（显式边框） | 第二行必须是分隔行（只含 `\| - : 空格`）；首行作表头加粗并设 `tblHeader` |
| `**bold**` | `w:rPr/w:b` | 可跨任意字符 |
| `*italic*` | `w:rPr/w:i` | 单星号不匹配含 `*` 或换行的内容；未闭合标记按字面文本保留 |

表格细节：列数以表头为准，不足补空单元格、超出截断；表格后自动补一个空段落
（OOXML 要求 `w:tbl` 后必须有 `w:p`，否则 Word 可能报修复）。

## 3. 修订留痕（tracked changes）

- 每条 edit：`find` 命中区间 → `<w:del w:id w:author="skill-agent" w:date><w:r><w:delText>原文</w:delText></w:r></w:del>`
  紧跟 `<w:ins ...><w:r><w:t>新文</w:t></w:r></w:ins>`。
- 命中区间跨多个 run（如部分加粗）时逐 run 切分，保留原有格式；插入文本沿用命中区第一个 run 的格式。
- 每条 edit 只应用于**第一处命中**（按文档顺序）；后续相同文本不再改动。
- 已形成的 del/ins 区域不参与后续 edit 的检索（避免修订嵌套修订）。

## 4. round-trip 验证口径

1. `zipfile.ZipFile.testzip()` + 4 个必要部件齐全；
2. `word/document.xml` 用 `xml.etree.ElementTree` 解析良构；
3. 反抽文本（所有 `w:t`，**不含** `w:delText`，即"接受全部修订"后的文本）与参考文本做
   token 级对比（`\w+|[^\w\s]` 切分，`difflib.SequenceMatcher.ratio()`），阈值 **0.99**。
   参考文本：干净版 = Markdown 纯文本（列表项含 `• ` 前缀，与 docx 口径一致）；
   修订版 = Markdown 纯文本应用全部命中 edit 后的期望文本。

## 5. 已知限制（有意取舍）

- **不支持**：图片、公式、代码块、有序列表（`1.`）、引用块（`>`）、嵌套列表、
  四级及以下标题、脚注、页眉页脚、目录、分栏。成稿阶段请避免这些语法；
  用了不会报错，但会被当普通文本编译，且会拉低 round-trip 保留率。
- 列表是字面 `• ` 前缀 + ListParagraph 缩进，不是自动编号；在 Word 中重新编号需手工转换。
- 斜体标记 `*` 不支持嵌套在加粗内部的复杂组合；`**bold**` 内部可以有 `*italic*`。
- `find` 片段若跨越 Markdown 行内标记边界（例如一半在 `**` 里一半在外）仍可命中
  （检索在拼接后的纯文本上进行），但插入文本只继承命中区第一个 run 的格式。
- 超长文档没有流式写盘优化（全部在内存拼 XML）；数万段落级仍可用，更大请先拆章编译。
- 生成的 DOCX 已通过 Word 生态工具（textutil/qlmanage/LibreOffice 系）真实打开验证；
  个别严格校验器可能提示缺少 numbering.xml/settings.xml 等可选部件——这些部件
  对本子集不是必需的。
