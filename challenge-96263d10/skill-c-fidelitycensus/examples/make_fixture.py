#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_fixture.py -- 合成示例输入（合成示例，非真实案件）。

生成三个最小 DOCX（stdlib 手写 OOXML）：
  source.docx       源稿：标题 + 3 段正文（含数字 0.85、[1] 引用）+ 1 张表 + 1 条脚注
  adapted.docx      适配产物：内容相同，仅 0.85 -> 0.86（任务要求的声明改动）
  adapted_bad.docx  事故产物：除声明改动外，还静默删了一句话并改掉一个数字
"""
import os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")

CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>
</Relationships>"""
FOOTNOTES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>
<w:footnote w:id="1"><w:p><w:r><w:t>基金项目：合成示例基金 12345。</w:t></w:r></w:p></w:footnote>
</w:footnotes>"""

WNS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

def para(text, footnote=False):
    fn = '<w:r><w:footnoteReference w:id="1"/></w:r>' if footnote else ""
    return "<w:p><w:r><w:t xml:space=\"preserve\">%s</w:t></w:r>%s</w:p>" % (text, fn)

TABLE = ("<w:tbl><w:tr><w:tc><w:p><w:r><w:t>组别</w:t></w:r></w:p></w:tc>"
         "<w:tc><w:p><w:r><w:t>产率</w:t></w:r></w:p></w:tc></w:tr>"
         "<w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>"
         "<w:tc><w:p><w:r><w:t>92.4%</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")

def document(paragraphs, table=True):
    body = "".join(paragraphs) + (TABLE if table else "")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            "<w:document %s><w:body>%s"
            '<w:sectPr><w:pgSz w:w="11907" w:h="16840"/></w:sectPr>'
            "</w:body></w:document>") % (WNS, body)

SRC_PARAS = [
    para("合成稿件标题：催化剂性能研究"),
    para("实验在 300 K 下进行，测得转化率为 0.85，与文献 [1] 报道一致。", footnote=True),
    para("对照组在相同条件下重复 3 次，标准偏差小于 2%。"),
    para("综上，该催化剂表现出稳定的活性。"),
]
ADAPTED_PARAS = list(SRC_PARAS)
ADAPTED_PARAS[1] = para("实验在 300 K 下进行，测得转化率为 0.86，与文献 [1] 报道一致。", footnote=True)
BAD_PARAS = list(ADAPTED_PARAS)
BAD_PARAS[2] = para("对照组在相同条件下重复 5 次，标准偏差小于 2%。")  # 未声明：3->5
del BAD_PARAS[3]  # 未声明：静默删除末段

def write_docx(path, paras, table=True):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/footnotes.xml", FOOTNOTES)
        z.writestr("word/document.xml", document(paras, table))

def main():
    os.makedirs(WORK, exist_ok=True)
    write_docx(os.path.join(WORK, "source.docx"), SRC_PARAS)
    write_docx(os.path.join(WORK, "adapted.docx"), ADAPTED_PARAS)
    write_docx(os.path.join(WORK, "adapted_bad.docx"), BAD_PARAS)
    print("synthetic fixtures ->", WORK)

if __name__ == "__main__":
    main()
