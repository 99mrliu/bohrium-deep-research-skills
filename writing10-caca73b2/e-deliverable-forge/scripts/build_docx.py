#!/usr/bin/env python3
"""build_docx.py — 仅用 Python 标准库(zipfile + 手写 XML)生成可编辑 .docx。

支持稿件 markdown 子集:
  * # / ## / ### 标题(映射 Heading1/2/3 样式, 可编辑、可导航);
  * 正文段落, 行内 **粗体** 与 *斜体*;
  * 管道表格(| a | b |), 带边框;
  * 图/表题注行(图1. ... / Table 2. ...), 居中加粗段落(Caption 样式);
  * "- " 无序列表(项目符号段落)。

生成后自验: 重新打开 zip, 用 xml.etree 解析 word/document.xml,
统计段落与表格数, 断言段落数 > 0, 打印自验摘要。
同时输出 build_manifest.json(产物清单 + sha256 + 字节数)。

任一步骤失败: 写出 manuscript.md + manuscript.html 降级产物并以退出码 2 结束,
由调用方在 result.json 的 limits/uncertainty 中记录。

用法:
    python3 build_docx.py --input manuscript.md --out manuscript.docx \
        --manifest build_manifest.json [--fallback-dir DIR]

退出码: 0 = 成功且自验通过; 2 = 构建或自验失败(已写降级产物)。
仅使用 Python 标准库, 兼容 Python >= 3.9; 不依赖 pandoc / python-docx / LibreOffice。
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CAPTION_RE = re.compile(
    r"^\s*(图|表|Figure|Fig\.?|Table)\s*\d+\s*[.．:：]\s*\S.*$"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")

# ---------------------------------------------------------------------------
# markdown 子集解析
# ---------------------------------------------------------------------------

def parse_markdown(text):
    """返回块列表: dict(type, ...)，type ∈ heading/paragraph/caption/table/bullet。"""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = HEADING_RE.match(line)
        if m:
            level = min(len(m.group(1)), 3)
            blocks.append({"type": "heading", "level": level, "text": m.group(2).strip()})
            i += 1
            continue
        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            # 去掉分隔行(|---|---|)
            rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c or "---") for c in r)]
            if rows:
                blocks.append({"type": "table", "rows": rows})
            continue
        if CAPTION_RE.match(line):
            blocks.append({"type": "caption", "text": line.strip()})
            i += 1
            continue
        m = BULLET_RE.match(line)
        if m:
            blocks.append({"type": "bullet", "text": m.group(1).strip()})
            i += 1
            continue
        # 普通段落: 合并连续非空行
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not (
            HEADING_RE.match(lines[i])
            or CAPTION_RE.match(lines[i])
            or BULLET_RE.match(lines[i])
            or lines[i].lstrip().startswith("|")
        ):
            para.append(lines[i].strip())
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(para)})
    return blocks


INLINE_RE = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*)")


def parse_inline(text):
    """拆分为 run 列表: dict(text, bold, italic)。"""
    runs = []
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            runs.append({"text": part[2:-2], "bold": True, "italic": False})
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            runs.append({"text": part[1:-1], "bold": False, "italic": True})
        else:
            runs.append({"text": part, "bold": False, "italic": False})
    return runs

# ---------------------------------------------------------------------------
# OOXML 生成
# ---------------------------------------------------------------------------

def esc(s):
    return html.escape(s, quote=True)


def run_xml(run, force_bold=False):
    props = ""
    bold = run["bold"] or force_bold
    if bold or run["italic"]:
        props = "<w:rPr>%s%s</w:rPr>" % (
            "<w:b/>" if bold else "",
            "<w:i/>" if run["italic"] else "",
        )
    return '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (props, esc(run["text"]))


def paragraph_xml(text, style=None, align=None, force_bold=False):
    ppr = ""
    inner = ""
    if style:
        inner += '<w:pStyle w:val="%s"/>' % style
    if align:
        inner += '<w:jc w:val="%s"/>' % align
    if inner:
        ppr = "<w:pPr>%s</w:pPr>" % inner
    runs = "".join(run_xml(r, force_bold=force_bold) for r in parse_inline(text))
    return "<w:p>%s%s</w:p>" % (ppr, runs)


def table_xml(rows):
    borders = (
        "<w:tblBorders>"
        + "".join(
            '<w:%s w:val="single" w:sz="4" w:space="0" w:color="auto"/>' % edge
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        + "</w:tblBorders>"
    )
    xml = [
        "<w:tbl><w:tblPr>"
        '<w:tblW w:w="0" w:type="auto"/>%s</w:tblPr>' % borders
    ]
    for r_idx, row in enumerate(rows):
        xml.append("<w:tr>")
        for cell in row:
            xml.append(
                "<w:tc><w:tcPr>"
                '<w:tcW w:w="0" w:type="auto"/>'
                "</w:tcPr>%s</w:tc>"
                % paragraph_xml(cell, force_bold=(r_idx == 0))
            )
        xml.append("</w:tr>")
    xml.append("</w:tbl>")
    return "".join(xml)


def document_xml(blocks):
    body = []
    for b in blocks:
        if b["type"] == "heading":
            body.append(paragraph_xml(b["text"], style="Heading%d" % b["level"]))
        elif b["type"] == "caption":
            body.append(paragraph_xml(b["text"], style="Caption", align="center", force_bold=True))
        elif b["type"] == "bullet":
            body.append(paragraph_xml("• " + b["text"], style="ListParagraph"))
        elif b["type"] == "table":
            body.append(table_xml(b["rows"]))
            body.append("<w:p/>")  # 表格后必须有段落, 避免相邻表格粘连
        else:
            body.append(paragraph_xml(b["text"]))
    sect = (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="%s"><w:body>%s%s</w:body></w:document>'
        % (W_NS, "".join(body), sect)
    )


STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    "<w:name w:val=\"Normal\"/><w:qFormat/></w:style>"
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/>'
    "<w:rPr><w:b/><w:sz w:val=\"32\"/></w:rPr></w:style>"
    '<w:style w:type="paragraph" w:styleId="Heading2">'
    '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/>'
    "<w:rPr><w:b/><w:sz w:val=\"28\"/></w:rPr></w:style>"
    '<w:style w:type="paragraph" w:styleId="Heading3">'
    '<w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/>'
    "<w:rPr><w:b/><w:sz w:val=\"24\"/></w:rPr></w:style>"
    '<w:style w:type="paragraph" w:styleId="Caption">'
    '<w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:qFormat/>'
    "<w:rPr><w:b/><w:sz w:val=\"21\"/></w:rPr></w:style>"
    '<w:style w:type="paragraph" w:styleId="ListParagraph">'
    '<w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:ind w:left="420"/></w:pPr></w:style>'
    "</w:styles>"
)

CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)

RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)

DOC_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)

# ---------------------------------------------------------------------------
# 构建 / 自验 / 降级
# ---------------------------------------------------------------------------

def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_docx(blocks, out_path):
    """写出 docx; zip 条目使用固定时间戳以保证同输入必得同字节(确定性)。"""
    doc = document_xml(blocks)
    fixed_dt = (1980, 1, 1, 0, 0, 0)
    members = [
        ("[Content_Types].xml", CONTENT_TYPES_XML),
        ("_rels/.rels", RELS_XML),
        ("word/_rels/document.xml.rels", DOC_RELS_XML),
        ("word/document.xml", doc),
        ("word/styles.xml", STYLES_XML),
    ]
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members:
            info = zipfile.ZipInfo(filename=name, date_time=fixed_dt)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload)


def verify_docx(path):
    """返回 (ok, summary_lines)。"""
    lines = []
    if not zipfile.is_zipfile(path):
        return False, ["not a valid zip archive"]
    with zipfile.ZipFile(path, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            return False, ["corrupt member: %s" % bad]
        names = set(zf.namelist())
        required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"}
        missing = required - names
        if missing:
            return False, ["missing parts: %s" % ", ".join(sorted(missing))]
        doc_bytes = zf.read("word/document.xml")
    root = ET.fromstring(doc_bytes)
    paras = root.findall(".//{%s}p" % W_NS)
    tables = root.findall(".//{%s}tbl" % W_NS)
    if len(paras) == 0:
        return False, ["document.xml parsed but contains 0 paragraphs"]
    size = os.path.getsize(path)
    digest = sha256_of(path)
    lines.append("self-verification summary:")
    lines.append("  zip integrity: OK (testzip passed)")
    lines.append("  required parts: [Content_Types].xml, _rels/.rels, word/document.xml, word/styles.xml")
    lines.append("  document.xml: parsed by xml.etree, %d paragraph(s), %d table(s)" % (len(paras), len(tables)))
    lines.append("  size: %d bytes" % size)
    lines.append("  sha256: %s" % digest)
    return True, lines


def write_fallback(md_text, fallback_dir):
    """写出 manuscript.md 与 manuscript.html 降级产物, 返回路径列表。"""
    os.makedirs(fallback_dir, exist_ok=True)
    md_path = os.path.join(fallback_dir, "manuscript.md")
    html_path = os.path.join(fallback_dir, "manuscript.html")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_text)
    blocks = parse_markdown(md_text)
    parts = ["<!DOCTYPE html><html><head><meta charset=\"utf-8\">",
             "<title>manuscript (fallback)</title></head><body>"]
    for b in blocks:
        if b["type"] == "heading":
            parts.append("<h%d>%s</h%d>" % (b["level"], esc(b["text"]), b["level"]))
        elif b["type"] == "caption":
            parts.append('<p style="text-align:center"><strong>%s</strong></p>' % esc(b["text"]))
        elif b["type"] == "table":
            parts.append('<table border="1">')
            for row in b["rows"]:
                parts.append("<tr>" + "".join("<td>%s</td>" % esc(c) for c in row) + "</tr>")
            parts.append("</table>")
        elif b["type"] == "bullet":
            parts.append("<ul><li>%s</li></ul>" % esc(b["text"]))
        else:
            parts.append("<p>%s</p>" % esc(b["text"]))
    parts.append("</body></html>")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return [md_path, html_path]


def write_manifest(manifest_path, files, extra=None):
    entries = []
    for path in files:
        entries.append(
            {
                "path": os.path.abspath(path),
                "bytes": os.path.getsize(path),
                "sha256": sha256_of(path),
            }
        )
    payload = {"artifacts": entries}
    if extra:
        payload.update(extra)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="仅用标准库将稿件 markdown 构建为可编辑 .docx, 并自验。"
    )
    parser.add_argument("--input", required=True, help="稿件 markdown 路径")
    parser.add_argument("--out", required=True, help="输出 .docx 路径")
    parser.add_argument("--manifest", required=True, help="build_manifest.json 输出路径")
    parser.add_argument(
        "--fallback-dir",
        default=None,
        help="降级产物目录(默认与 --out 同目录)",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            md_text = fh.read()
    except OSError as exc:
        sys.stderr.write("ERROR: cannot read %s: %s\n" % (args.input, exc))
        return 2

    fallback_dir = args.fallback_dir or os.path.dirname(os.path.abspath(args.out)) or "."

    try:
        blocks = parse_markdown(md_text)
        if not blocks:
            raise ValueError("no content blocks parsed from input")
        build_docx(blocks, args.out)
        ok, summary = verify_docx(args.out)
        if not ok:
            raise ValueError("self-verification failed: %s" % "; ".join(summary))
    except Exception as exc:  # noqa: BLE001 —— 任何失败都走降级路径
        sys.stderr.write("ERROR: docx build/verify failed: %s\n" % exc)
        paths = write_fallback(md_text, fallback_dir)
        write_manifest(
            args.manifest,
            paths,
            extra={"status": "fallback", "reason": str(exc)},
        )
        sys.stderr.write(
            "fallback written: %s; manifest: %s\n" % (", ".join(paths), args.manifest)
        )
        return 2

    write_manifest(
        args.manifest,
        [args.input, args.out],
        extra={"status": "ok"},
    )
    sys.stdout.write("docx built: %s\n" % args.out)
    for line in summary:
        sys.stdout.write(line + "\n")
    sys.stdout.write("manifest: %s\n" % args.manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
