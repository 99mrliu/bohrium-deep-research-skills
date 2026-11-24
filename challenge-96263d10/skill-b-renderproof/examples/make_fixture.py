#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_fixture.py -- 手写一个最小 PDF 作为合成示例输入（合成示例，非真实案件）。

仅用标准库拼出合法单页 A4 PDF：Helvetica 12pt（base-14，不内嵌——
用于演示字体内嵌检查给出诚实 FAIL），三行文字位于 2.54cm 左边距处。
另写 spec.json：页面/边距期望按 A4 单栏给，fonts.embedded_all 期望 true
（第一轮裁决必然 FAIL，第二轮把期望改成 false 演示 PASS——体现"裁决跟着
规格走，而不是跟着愿望走"）。
"""
import json, os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")

CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
DOCX_BODY = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t xml:space="preserve">Synthetic docx for the render chain demo. A4, margins 3.17/2.54 cm.</w:t></w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">Second paragraph so the text body has measurable extent.</w:t></w:r></w:p>
<w:sectPr><w:pgSz w:w="11907" w:h="16840"/>
<w:pgMar w:top="1797" w:right="1440" w:bottom="1797" w:left="1440" w:header="851" w:footer="992" w:gutter="0"/>
<w:cols w:space="425"/></w:sectPr>
</w:body>
</w:document>"""

def build_docx(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", DOCX_BODY)

def build_pdf(path):
    content = (
        "BT /F1 12 Tf 72 770 Td (Synthetic example page for render-proof demo.) Tj ET\n"
        "BT /F1 12 Tf 72 750 Td (Left margin anchor at 72 pt equals 2.54 cm.) Tj ET\n"
        "BT /F1 12 Tf 72 730 Td (Helvetica base14 font is NOT embedded on purpose.) Tj ET\n"
    ).encode("latin-1")
    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref_pos))
    with open(path, "wb") as f:
        f.write(out)

def main():
    os.makedirs(WORK, exist_ok=True)
    build_pdf(os.path.join(WORK, "sample.pdf"))
    spec = {"page.size.width_cm": 21.0, "page.size.height_cm": 29.7,
            "page.margin.left_cm": 2.54, "page.margin.top_cm": 2.4,
            "page.columns": 1, "fonts.embedded_all": True}
    with open(os.path.join(WORK, "spec.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    spec2 = dict(spec)
    spec2["fonts.embedded_all"] = False
    with open(os.path.join(WORK, "spec_round2.json"), "w", encoding="utf-8") as f:
        json.dump(spec2, f, ensure_ascii=False, indent=2)
    build_docx(os.path.join(WORK, "sample.docx"))
    spec3 = {"page.size.width_cm": 21.0, "page.size.height_cm": 29.7,
             "page.margin.left_cm": 2.54, "page.margin.top_cm": 3.17,
             "page.columns": 1}
    with open(os.path.join(WORK, "spec_docx.json"), "w", encoding="utf-8") as f:
        json.dump(spec3, f, ensure_ascii=False, indent=2)
    print("synthetic fixtures ->", WORK)

if __name__ == "__main__":
    main()
