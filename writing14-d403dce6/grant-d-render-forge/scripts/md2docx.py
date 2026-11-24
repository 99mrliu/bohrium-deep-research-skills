#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2docx.py — 仅用 Python 标准库把章节稿 Markdown 转成真正可打开的最小 .docx。

支持的 Markdown 子集：
  # / ## / ###     标题（映射 Heading1/2/3，中文字体黑体 SimHei）
  普通段落          正文（宋体 SimSun，east-asia 字体声明）
  - 列表项          ListParagraph 样式 + "• " 前缀
  | a | b |        表格（第二行须为 |---| 分隔行），表头加粗
  **加粗**          行内加粗 run

生成的 docx 包含四个必需部件：[Content_Types].xml、_rels/.rels、
word/document.xml、word/styles.xml（另附 word/_rels/document.xml.rels）。
写出后用 zipfile 复读校验：缺必需部件或 XML 不可解析即报错，退出码 1。

确定性：zip 条目时间戳固定为 1980-01-01，同一输入二次运行字节一致。

用法：
  python3 md2docx.py 输入.md 输出.docx
退出码：
  0 成功且校验通过；1 输入/写出/校验失败；2 参数错误（argparse）。
"""
import argparse
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

REQUIRED_PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/styles.xml",
)

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="%(W)s">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:eastAsia="SimSun" w:hAnsi="Times New Roman"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:rPr><w:rFonts w:ascii="Times New Roman" w:eastAsia="SimSun" w:hAnsi="Times New Roman"/><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:eastAsia="SimHei" w:hAnsi="Arial"/><w:b/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:eastAsia="SimHei" w:hAnsi="Arial"/><w:b/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:eastAsia="SimHei" w:hAnsi="Arial"/><w:b/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:ind w:left="720"/></w:pPr></w:style>
</w:styles>
""" % {"W": W}

SECT_PR = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
           'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')

BOLD_RE = re.compile(r"(\*\*.+?\*\*)")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
LIST_RE = re.compile(r"^[-*]\s+(.*)$")
TABLE_SEP_RE = re.compile(r"^\|?[\s:\-|]+\|?$")


def esc(text):
    return escape(text, {'"': "&quot;"})


def runs_xml(text):
    """把含 **加粗** 的行内文本转成若干 w:r run，XML 转义正确。"""
    out = []
    for part in BOLD_RE.split(text):
        if not part:
            continue
        if len(part) > 4 and part.startswith("**") and part.endswith("**"):
            out.append('<w:r><w:rPr><w:b/></w:rPr>'
                       '<w:t xml:space="preserve">%s</w:t></w:r>' % esc(part[2:-2]))
        else:
            out.append('<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % esc(part))
    return "".join(out) or "<w:r><w:t></w:t></w:r>"


def para_xml(text, style=None):
    ppr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    return "<w:p>%s%s</w:p>" % (ppr, runs_xml(text))


def split_row(line):
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def table_xml(row_lines):
    rows = [split_row(l) for l in row_lines]
    ncol = max(len(r) for r in rows)
    width = max(1200, 9000 // ncol)
    borders = "".join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                      % side for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
    out = ['<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>'
           '<w:tblBorders>%s</w:tblBorders></w:tblPr>' % borders]
    for ridx, row in enumerate(rows):
        out.append("<w:tr>")
        for cell in row + [""] * (ncol - len(row)):
            if ridx == 0:
                content = '<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>' % esc(cell)
            else:
                content = runs_xml(cell)
            out.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>'
                       '<w:p>%s</w:p></w:tc>' % (width, content))
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def markdown_to_body(md_text):
    """逐行解析 Markdown 子集，返回 document.xml 的 w:body 内部 XML。"""
    lines = md_text.splitlines()
    blocks = []
    i = 0
    para_buf = []

    def flush_para():
        if para_buf:
            blocks.append(para_xml(" ".join(para_buf).strip()))
            para_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        m = HEADING_RE.match(stripped)
        if m:
            flush_para()
            level = len(m.group(1))
            blocks.append(para_xml(m.group(2).strip(), "Heading%d" % level))
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) \
                and TABLE_SEP_RE.match(lines[i + 1].strip()) and "-" in lines[i + 1]:
            flush_para()
            tbl = [stripped]
            i += 2  # 跳过表头与分隔行
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            blocks.append(table_xml(tbl))
            continue
        m = LIST_RE.match(stripped)
        if m:
            flush_para()
            blocks.append(para_xml("• " + m.group(1).strip(), "ListParagraph"))
            i += 1
            continue
        para_buf.append(stripped)
        i += 1
    flush_para()
    return "".join(blocks)


def build_parts(md_text):
    document_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<w:document xmlns:w="%s"><w:body>%s%s</w:body></w:document>\n'
                    % (W, markdown_to_body(md_text), SECT_PR))
    return {
        "[Content_Types].xml": CONTENT_TYPES_XML,
        "_rels/.rels": RELS_XML,
        "word/_rels/document.xml.rels": DOC_RELS_XML,
        "word/document.xml": document_xml,
        "word/styles.xml": STYLES_XML,
    }


def write_docx(parts, out_path):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts.items():
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, text.encode("utf-8"))


def validate_docx(path):
    """复读校验：必需部件齐全且每个 XML 部件可解析。返回错误列表（空=通过）。"""
    errors = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for part in REQUIRED_PARTS:
                if part not in names:
                    errors.append("缺少必需部件: %s" % part)
            for name in sorted(names):
                data = zf.read(name)
                if name.endswith((".xml", ".rels")):
                    try:
                        ET.fromstring(data)
                    except ET.ParseError as exc:
                        errors.append("XML 不可解析 %s: %s" % (name, exc))
            if "word/document.xml" in names:
                root = ET.fromstring(zf.read("word/document.xml"))
                if root.tag != "{%s}document" % W:
                    errors.append("word/document.xml 根元素不是 w:document")
    except zipfile.BadZipFile as exc:
        errors.append("不是合法 zip/docx: %s" % exc)
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="仅用标准库把章节稿 Markdown 转成最小合法 .docx 并复读校验。")
    ap.add_argument("input", help="输入 Markdown 文件（UTF-8）")
    ap.add_argument("output", help="输出 .docx 路径")
    args = ap.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            md_text = fh.read()
    except OSError as exc:
        print("错误：无法读取输入文件 %s: %s" % (args.input, exc), file=sys.stderr)
        return 1

    parts = build_parts(md_text)
    try:
        write_docx(parts, args.output)
    except OSError as exc:
        print("错误：无法写出 %s: %s" % (args.output, exc), file=sys.stderr)
        return 1

    errors = validate_docx(args.output)
    if errors:
        for e in errors:
            print("校验失败：%s" % e, file=sys.stderr)
        return 1

    print("docx 生成并校验通过: %s" % args.output)
    with zipfile.ZipFile(args.output) as zf:
        for info in zf.infolist():
            print("  部件 %-36s %6d 字节" % (info.filename, info.file_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
