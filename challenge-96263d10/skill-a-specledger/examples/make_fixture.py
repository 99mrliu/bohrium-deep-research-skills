#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_fixture.py -- 生成本示例的合成输入（合成示例，非真实案件）。

产物（写入 examples/work/，不入包）：
  template.docx  -- 合成模板：A4、上下 3.17cm 左右 2.54cm、单栏、
                    Normal=Liberation Serif 10.5pt、Heading1=16pt 加粗、1.5 倍行距
  rules.txt      -- 合成投稿须知：含与模板冲突的行距规定（用于演示冲突裁决）
  output_ok.docx -- 合成"已适配输出"（几何与模板一致，spec_check 应全 PASS/UNKNOWN）

仅用 Python 3 标准库手写最小 OOXML 包。
"""
import os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")

CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""

DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>引言</w:t></w:r></w:p>
<w:p><w:r><w:t>这是合成示例正文段落，仅用于演示规格抽取与核对。</w:t></w:r></w:p>
<w:sectPr>
<w:pgSz w:w="11907" w:h="16840"/>
<w:pgMar w:top="1797" w:right="1440" w:bottom="1797" w:left="1440" w:header="851" w:footer="992" w:gutter="0"/>
<w:cols w:space="425"/>
</w:sectPr>
</w:body>
</w:document>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
<w:name w:val="Normal"/>
<w:pPr><w:spacing w:after="160" w:line="360" w:lineRule="auto"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Liberation Serif" w:eastAsia="SimSun"/><w:sz w:val="21"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="Heading1">
<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:b/><w:rFonts w:ascii="Liberation Serif" w:eastAsia="SimHei"/><w:sz w:val="32"/></w:rPr>
</w:style>
</w:styles>"""

DOC_FIXED = DOC.replace('w:line="360"', 'w:line="300"')  # 1.25 倍行距（按须知修正后）

RULES = """XX 期刊投稿须知（合成示例文本，非真实期刊规定）
1. 页面 A4，上、下页边距 3.17 cm，左、右页边距 2.54 cm。
2. 正文五号字（10.5 pt），行距 1.25 倍；一级标题三号加粗。
3. 单栏排版。图题注置于图下方，表题注置于表上方。
4. 参考文献著录执行 GB/T 7714。
"""

def write_docx(path, document_xml, styles_xml):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", styles_xml)

def main():
    os.makedirs(WORK, exist_ok=True)
    write_docx(os.path.join(WORK, "template.docx"), DOC, STYLES)
    write_docx(os.path.join(WORK, "output_ok.docx"), DOC, STYLES)
    write_docx(os.path.join(WORK, "output_fixed.docx"), DOC_FIXED,
               STYLES.replace('w:line="360"', 'w:line="300"'))
    with open(os.path.join(WORK, "rules.txt"), "w", encoding="utf-8") as f:
        f.write(RULES)
    print("synthetic fixtures ->", WORK)

if __name__ == "__main__":
    main()
