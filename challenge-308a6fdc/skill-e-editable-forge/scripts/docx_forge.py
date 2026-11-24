#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx_forge.py — Markdown → 真 DOCX 编译器（可编辑产物 + 修订留痕 + 验证 + 预览装配）

仅依赖 Python3 标准库（zipfile / xml.etree / xml.sax.saxutils / argparse / json /
hashlib / csv / shutil / subprocess / difflib / re / datetime / pathlib）。

五个子命令：
  build    Markdown 编译为 DOCX；带 --edit-plan 时生成 w:ins/w:del 真修订版 + 复核 CSV
  verify   对 DOCX 做 round-trip 自检（zip 完整性 / XML 良构 / 文本保留率），输出报告
  render   按降级链真实渲染预览：soffice → pandoc → textutil+cupsfilter → qlmanage → preview.html
  run      端到端：读 case.json + draft.md [+ edit_plan.json]，产出全部交付物并装配 result.json
  extract  调试用：从 DOCX 反抽纯文本打印到 stdout

红线：找不到渲染器时只生成 preview.html 并如实记录，绝不伪造 PDF/PNG。
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as _xml_escape

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REVISION_AUTHOR = "skill-agent"
RETENTION_THRESHOLD = 0.99  # round-trip 文本保留率红线

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

# styles.xml：Normal / Heading1-3 / ListParagraph / TableGrid。
# 中文字体仅做声明（SimSun / 等线），不内嵌字体文件。
STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
        <w:sz w:val="24"/><w:szCs w:val="24"/>
      </w:rPr>
    </w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="等线"/><w:b/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="等线"/><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="等线"/><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph">
    <w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:ind w:left="420"/></w:pPr>
  </w:style>
  <w:style w:type="table" w:styleId="TableGrid">
    <w:name w:val="Table Grid"/><w:basedOn w:val="TableNormal"/><w:uiPriority w:val="39"/>
    <w:tblPr>
      <w:tblBorders>
        <w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>
        <w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>
        <w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>
        <w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>
        <w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/>
        <w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/>
      </w:tblBorders>
    </w:tblPr>
  </w:style>
</w:styles>
"""

SECT_PR = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
           'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

# XML 1.0 合法字符：#x9 #xA #xD #x20-#xD7FF #xE000-#xFFFD #x10000-#x10FFFF
_ILLEGAL_XML_RE = re.compile(
    "[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)


def xesc(text):
    """XML 转义 + 剔除非法控制字符（先剔除再转义）。"""
    return _xml_escape(_ILLEGAL_XML_RE.sub("", text))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Markdown 子集解析
# ---------------------------------------------------------------------------

def parse_inline(text):
    """把一段行内文本解析为 run 列表 [(text, bold, italic), ...]。
    支持 **加粗** 与 *斜体*；未闭合的标记按字面文本保留。"""
    runs = []

    def push(t, b, i):
        if t:
            if runs and runs[-1][1] == b and runs[-1][2] == i:
                runs[-1] = (runs[-1][0] + t, b, i)
            else:
                runs.append((t, b, i))

    # 先按 ** 切分，再在未加粗段内按 * 切分
    pos = 0
    for m in re.finditer(r"\*\*(.+?)\*\*", text, flags=re.S):
        _parse_italic(text[pos:m.start()], False, push)
        _parse_italic(m.group(1), True, push)
        pos = m.end()
    _parse_italic(text[pos:], False, push)
    return runs or [("", False, False)]


def _parse_italic(segment, bold, push):
    pos = 0
    for m in re.finditer(r"\*([^*\n]+?)\*", segment):
        push(segment[pos:m.start()], bold, False)
        push(m.group(1), bold, True)
        pos = m.end()
    push(segment[pos:], bold, False)


def _is_table_sep(line):
    s = line.strip()
    return bool(s) and all(c in "-:| " for c in s) and "-" in s and "|" in s


def _split_table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse_markdown(md_text):
    """把 Markdown 子集解析为块列表。

    块类型：
      ("h1"|"h2"|"h3", runs)            标题
      ("p", runs)                       段落
      ("li", runs)                      无序列表项
      ("table", header_cells, rows)     表格（单元格内容为 runs）
    """
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            blocks.append((f"h{level}", parse_inline(m.group(2))))
            i += 1
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(("li", parse_inline(stripped[2:].strip())))
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            header = [parse_inline(c) for c in _split_table_row(stripped)]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [parse_inline(c) for c in _split_table_row(lines[i])]
                # 列数不齐时以表头为准补齐/截断，避免生成非法表格
                if len(cells) < len(header):
                    cells += [[("", False, False)]] * (len(header) - len(cells))
                rows.append(cells[: len(header)])
                i += 1
            blocks.append(("table", header, rows))
            continue
        # 普通段落：吸收后续非空行（软换行合并为一个段落）
        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (not nxt or re.match(r"^#{1,3}\s", nxt) or nxt.startswith(("- ", "* ", "|"))):
                break
            para.append(nxt)
            i += 1
        blocks.append(("p", parse_inline(" ".join(para))))
    return blocks


def md_plain_text(md_text):
    """从 Markdown 提取纯文本（供 round-trip 对比），与 docx 反抽口径一致：
    列表项含编译时加入的 "• " 前缀；表格按单元格逐段展开。"""
    parts = []
    for block in parse_markdown(md_text):
        if block[0] == "table":
            for cell in block[1]:
                parts.append("".join(t for t, _, _ in cell))
            for row in block[2]:
                for cell in row:
                    parts.append("".join(t for t, _, _ in cell))
        elif block[0] == "li":
            parts.append("• " + "".join(t for t, _, _ in block[1]))
        else:
            parts.append("".join(t for t, _, _ in block[1]))
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# OOXML 生成
# ---------------------------------------------------------------------------

_rev_id = [0]  # 修订 id 计数器


def _next_rev_id():
    _rev_id[0] += 1
    return _rev_id[0]


def _rpr(bold, italic):
    props = ""
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    return f"<w:rPr>{props}</w:rPr>" if props else ""


def _run_xml(text, bold=False, italic=False, deleted=False):
    tag = "w:delText" if deleted else "w:t"
    return (f"<w:r>{_rpr(bold, italic)}"
            f'<{tag} xml:space="preserve">{xesc(text)}</{tag}></w:r>')


def _items_xml(items, rev_date):
    """items: [('run'|'ins'|'del', text, bold, italic), ...] → OOXML 字符串。"""
    out = []
    for kind, text, bold, italic in items:
        if kind == "run":
            out.append(_run_xml(text, bold, italic))
        elif kind == "ins":
            out.append(f'<w:ins w:id="{_next_rev_id()}" w:author="{REVISION_AUTHOR}" '
                       f'w:date="{rev_date}">{_run_xml(text, bold, italic)}</w:ins>')
        elif kind == "del":
            out.append(f'<w:del w:id="{_next_rev_id()}" w:author="{REVISION_AUTHOR}" '
                       f'w:date="{rev_date}">{_run_xml(text, bold, italic, deleted=True)}</w:del>')
    return "".join(out)


def _paragraph_xml(style, items, rev_date):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{_items_xml(items, rev_date)}</w:p>"


def _cell_xml(items, rev_date):
    return ("<w:tc><w:tcPr><w:tcW w:w=\"0\" w:type=\"auto\"/></w:tcPr>"
            f"{_paragraph_xml(None, items, rev_date)}</w:tc>")


def _table_xml(header, rows, rev_date):
    ncol = max(1, len(header))
    grid = "".join('<w:gridCol w:w="2400"/>' for _ in range(ncol))
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
           '<w:tblW w:w="0" w:type="auto"/>'
           '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" '
           'w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr>'
           f"<w:tblGrid>{grid}</w:tblGrid>"]
    # 表头行（加粗）
    hdr_cells = []
    for cell in header:
        hdr_cells.append(_cell_xml([(k, t, True, i) for k, t, b, i in cell], rev_date))
    out.append('<w:tr><w:trPr><w:tblHeader/></w:trPr>' + "".join(hdr_cells) + "</w:tr>")
    for row in rows:
        out.append("<w:tr>" + "".join(_cell_xml(c, rev_date) for c in row) + "</w:tr>")
    out.append("</w:tbl>")
    # Word 要求表格后必须有段落
    out.append("<w:p/>")
    return "".join(out)


def _as_items(runs):
    """runs 可能尚未应用修订（3 元组）或已应用修订（4 元组 items），统一为 items。"""
    return [r if len(r) == 4 else ("run", *r) for r in runs]


def blocks_to_document_xml(blocks, rev_date):
    body = []
    for block in blocks:
        kind = block[0]
        if kind in ("h1", "h2", "h3"):
            style = {"h1": "Heading1", "h2": "Heading2", "h3": "Heading3"}[kind]
            body.append(_paragraph_xml(style, _as_items(block[1]), rev_date))
        elif kind == "p":
            body.append(_paragraph_xml(None, _as_items(block[1]), rev_date))
        elif kind == "li":
            items = [("run", "• ", False, False)] + _as_items(block[1])
            body.append(_paragraph_xml("ListParagraph", items, rev_date))
        elif kind == "table":
            header = [_as_items(c) for c in block[1]]
            rows = [[_as_items(c) for c in row] for row in block[2]]
            body.append(_table_xml(header, rows, rev_date))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>'
            + "".join(body) + SECT_PR + "</w:body></w:document>")


def write_docx(document_xml, out_path):
    """写出最小 OOXML 包（4 个必要部件 + document.xml.rels）。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", ROOT_RELS_XML)
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS_XML)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", STYLES_XML)
    return out_path


# ---------------------------------------------------------------------------
# 修订留痕：edit_plan → w:del + w:ins
# ---------------------------------------------------------------------------

def apply_edit_plan(blocks, edit_plan, rev_date):
    """把 edit_plan 应用到块列表上（就地修改：runs → 带修订标记的 items）。

    每条修改：{"find": 原文片段, "replace": 新文本, "reason": 理由}
    命中段落/单元格后，受影响 run 区间改写为 del(原文) + ins(新文)；
    每条修改只应用到第一处命中（同一文本多处出现时在报告中可见，请人工核对）。
    返回 (applied, misses)：applied 为命中记录列表，misses 为未命中记录列表。
    """
    applied, misses = [], []

    def all_run_containers():
        """产出所有可修改的 run 列表引用：段落 runs、表头与各单元格 runs。"""
        for block in blocks:
            if block[0] == "table":
                for row in [block[1]] + list(block[2]):
                    for cell in row:
                        yield cell
            else:
                yield block[1]

    # 先把所有 runs 统一规范化为 items（kind, text, bold, italic），
    # 避免第二条修改命中同一容器时元组结构不一致
    for runs in all_run_containers():
        runs[:] = [("run", t, b, i) for t, b, i in runs]

    for idx, edit in enumerate(edit_plan, start=1):
        find = edit.get("find", "")
        replace = edit.get("replace", "")
        reason = edit.get("reason", "")
        record = {"编号": idx, "类型": "replace", "原文": find,
                  "新文": replace, "理由": reason}
        if not find:
            record["命中状态"] = "未命中：find 为空"
            misses.append(record)
            continue
        hit = False
        for runs in all_run_containers():
            # 只在普通 run 里检索（已删除/已插入文本不再参与后续命中）
            concat = "".join(t for k, t, _, _ in runs if k == "run")
            pos = concat.find(find)
            if pos < 0:
                continue
            # 按字符偏移把 items 切成 [前缀 | 命中区间 | 后缀]，命中区间改 del
            new_items, cursor, end = [], 0, pos + len(find)
            for kind, text, b, it in runs:
                if kind != "run":  # 既有修订整体保留，不参与切分
                    new_items.append((kind, text, b, it))
                    continue
                r0, r1 = cursor, cursor + len(text)
                cursor = r1
                if r1 <= pos or r0 >= end:
                    new_items.append(("run", text, b, it))  # 完全在区间外
                else:
                    if r0 < pos:  # 前半段保留
                        new_items.append(("run", text[: pos - r0], b, it))
                    new_items.append(("del", text[max(0, pos - r0): end - r0], b, it))
                    if r1 > end:  # 后半段保留
                        new_items.append(("run", text[end - r0:], b, it))
            # 在最后一段 del 之后插入 ins（新文本沿用命中区第一个 run 的格式）
            first_fmt = next(((b, i) for k, _, b, i in new_items if k == "del"),
                             (False, False))
            del_idx = max(i for i, it_ in enumerate(new_items) if it_[0] == "del")
            new_items.insert(del_idx + 1, ("ins", replace, *first_fmt))
            runs[:] = new_items
            hit = True
            break
        if hit:
            record["命中状态"] = "命中"
            applied.append(record)
        else:
            record["命中状态"] = "未命中：原文片段不存在"
            misses.append(record)
    return applied, misses


def write_review_csv(applied, misses, out_path):
    """输出复核 CSV：接受状态列留空，供人工在 Word/表格软件中逐条 accept/reject。"""
    out_path = Path(out_path)
    fields = ["编号", "类型", "原文", "新文", "理由", "命中状态", "接受状态(accept/reject/留空待审)"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for rec in applied + misses:
            row = dict(rec)
            row.setdefault("接受状态(accept/reject/留空待审)", "")
            writer.writerow(row)
    return out_path


# ---------------------------------------------------------------------------
# 验证：round-trip proof
# ---------------------------------------------------------------------------

def _tokens(text):
    """token 级切分：连续词字符为一个 token，其余非空白字符各自成 token。"""
    return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)


def docx_extract_text(docx_path, include_deleted=False):
    """从 DOCX 反抽纯文本。include_deleted=False 时跳过 w:delText（即“接受全部修订”后的文本）。"""
    with zipfile.ZipFile(docx_path) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    texts = []
    for para in root.iter(f"{{{W_NS}}}p"):
        parts = []
        for node in para.iter():
            if node.tag == f"{{{W_NS}}}t" and node.text:
                parts.append(node.text)
            elif include_deleted and node.tag == f"{{{W_NS}}}delText" and node.text:
                parts.append(node.text)
        if parts:
            texts.append("".join(parts))
    return "\n".join(texts)


def verify_docx(docx_path, md_text=None, expected_text=None):
    """对 DOCX 做三层自检，返回验证结果 dict。

    1) zipfile 完整性（testzip + 必要部件齐全）
    2) word/document.xml 可被 ElementTree 良构解析
    3) 反抽文本与参考文本 token 级对比，计算保留率
    """
    result = {"docx": str(docx_path), "ok": True, "errors": []}
    p = Path(docx_path)
    result["size_bytes"] = p.stat().st_size
    result["sha256"] = sha256_of(p)

    # 1) zip 完整性
    try:
        with zipfile.ZipFile(p) as zf:
            bad = zf.testzip()
            names = set(zf.namelist())
            required = {"[Content_Types].xml", "_rels/.rels",
                        "word/document.xml", "word/styles.xml"}
            missing = required - names
            if bad is not None:
                result["errors"].append(f"zip 损坏成员: {bad}")
            if missing:
                result["errors"].append(f"缺少必要部件: {sorted(missing)}")
            result["zip_ok"] = (bad is None and not missing)
            xml_bytes = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        result["zip_ok"] = False
        result["errors"].append(f"zip 无法打开: {exc}")
        result["ok"] = False
        return result

    # 2) XML 良构 + 结构计数
    try:
        root = ET.fromstring(xml_bytes)
        result["xml_ok"] = True
        result["paragraphs"] = sum(1 for _ in root.iter(f"{{{W_NS}}}p"))
        result["tables"] = sum(1 for _ in root.iter(f"{{{W_NS}}}tbl"))
        result["ins_count"] = sum(1 for _ in root.iter(f"{{{W_NS}}}ins"))
        result["del_count"] = sum(1 for _ in root.iter(f"{{{W_NS}}}del"))
    except ET.ParseError as exc:
        result["xml_ok"] = False
        result["errors"].append(f"document.xml 解析失败: {exc}")
        result["ok"] = False
        return result

    # 3) round-trip 文本保留率
    reference = expected_text if expected_text is not None else (
        md_plain_text(md_text) if md_text is not None else None)
    if reference is not None:
        extracted = docx_extract_text(p)
        ref_tok, ext_tok = _tokens(reference), _tokens(extracted)
        ratio = SequenceMatcher(None, ref_tok, ext_tok).ratio() if (ref_tok or ext_tok) else 1.0
        result["retention"] = round(ratio, 6)
        result["ref_tokens"] = len(ref_tok)
        result["docx_tokens"] = len(ext_tok)
        result["retention_ok"] = ratio >= RETENTION_THRESHOLD
        if not result["retention_ok"]:
            result["errors"].append(
                f"round-trip 保留率 {ratio:.4f} 低于阈值 {RETENTION_THRESHOLD}")
    else:
        result["retention"] = None
        result["retention_ok"] = None

    result["ok"] = (result.get("zip_ok") and result.get("xml_ok")
                    and result.get("retention_ok") in (True, None)
                    and not result["errors"])
    return result


# ---------------------------------------------------------------------------
# 预览渲染：真实渲染降级链，绝不伪造
# ---------------------------------------------------------------------------

def _run_cmd(cmd, timeout=120, stdout_path=None):
    """运行外部命令；stdout_path 非空时把 stdout 写入文件。返回 (ok, log)。"""
    try:
        if stdout_path:
            with open(stdout_path, "wb") as f:
                proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE,
                                      timeout=timeout)
        else:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout)
        log = (proc.stderr or b"").decode("utf-8", "replace")[-2000:]
        return proc.returncode == 0, log
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def _looks_like_pdf(path):
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def _looks_like_png(path):
    try:
        with open(path, "rb") as f:
            return f.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def render_preview(docx_path, md_text, outdir, base="preview"):
    """按降级链真实渲染预览，返回 preview_status dict。

    探测顺序（全部用 shutil.which 实测，命中才执行）：
      1. soffice/libreoffice --headless --convert-to pdf   （版式级 PDF）
      2. pandoc docx -o pdf                                （版式级 PDF）
      3. textutil + cupsfilter（macOS）：docx→txt→PDF      （纯文本版式 PDF，真实渲染）
      4. qlmanage（macOS）：docx→PNG 缩略图                （真实渲染 PNG，无 PDF）
      5. 全部不可用 → preview.html（自足 HTML，明示无 PDF 渲染器）
    PDF 生成后若探测到 pdftoppm，再转 PNG 逐页预览。
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    docx_path = Path(docx_path).resolve()
    pdf_path = outdir / f"{base}.pdf"
    status = {"status": "none", "renderer": None, "pdf": None, "pngs": [],
              "notes": [], "detected": {}}

    tools = {name: shutil.which(name) for name in
             ("soffice", "libreoffice", "pandoc", "textutil",
              "cupsfilter", "qlmanage", "pdftoppm")}
    status["detected"] = {k: (v or None) for k, v in tools.items()}

    office = tools["soffice"] or tools["libreoffice"]
    rendered_pdf = False

    # 1) LibreOffice / OpenOffice
    if office:
        ok, log = _run_cmd([office, "--headless", "--convert-to", "pdf",
                            "--outdir", str(outdir), str(docx_path)])
        produced = outdir / (docx_path.stem + ".pdf")
        if ok and produced.exists() and _looks_like_pdf(produced):
            if produced != pdf_path:
                produced.replace(pdf_path)
            rendered_pdf = True
            status["renderer"] = Path(office).name
        else:
            status["notes"].append(f"soffice 转换失败（已如实记录，不伪造）: {log[-300:]}")

    # 2) pandoc
    if not rendered_pdf and tools["pandoc"]:
        ok, log = _run_cmd([tools["pandoc"], str(docx_path), "-o", str(pdf_path)])
        if ok and pdf_path.exists() and _looks_like_pdf(pdf_path):
            rendered_pdf = True
            status["renderer"] = "pandoc"
        else:
            status["notes"].append(f"pandoc 转换失败（已如实记录，不伪造）: {log[-300:]}")

    # 3) textutil + cupsfilter（macOS 降级：纯文本版式 PDF）
    if not rendered_pdf and tools["textutil"] and tools["cupsfilter"]:
        tmp_txt = outdir / f".{base}.tmp.txt"
        ok1, log1 = _run_cmd([tools["textutil"], "-convert", "txt",
                              str(docx_path), "-output", str(tmp_txt)])
        ok2, log2 = (False, "")
        if ok1 and tmp_txt.exists():
            ok2, log2 = _run_cmd([tools["cupsfilter"], "-m", "application/pdf",
                                  str(tmp_txt)], stdout_path=pdf_path)
        if ok2 and pdf_path.exists() and _looks_like_pdf(pdf_path):
            rendered_pdf = True
            status["renderer"] = "textutil+cupsfilter"
            status["notes"].append("纯文本版式 PDF（textutil 抽取 + cupsfilter 渲染），"
                                   "排版与 DOCX 不同，仅供内容预览")
        else:
            if pdf_path.exists():
                pdf_path.unlink()  # 失败的空文件必须删除，避免误当产物
            status["notes"].append(f"textutil/cupsfilter 失败（已如实记录）: {log1[-200:]} {log2[-200:]}")
        if tmp_txt.exists():
            tmp_txt.unlink()

    # PDF → PNG 逐页预览
    if rendered_pdf:
        status["pdf"] = str(pdf_path)
        status["status"] = "rendered_pdf"
        if tools["pdftoppm"]:
            ok, log = _run_cmd([tools["pdftoppm"], "-png", "-r", "120",
                                str(pdf_path), str(outdir / base)])
            pngs = sorted(outdir.glob(f"{base}-*.png"))
            if ok and pngs and all(_looks_like_png(x) for x in pngs):
                status["pngs"] = [str(x) for x in pngs]
                status["status"] = "rendered_pdf_png"
            else:
                status["notes"].append(f"pdftoppm 失败（PDF 仍有效）: {log[-300:]}")
        return status

    # 4) qlmanage：docx → PNG 缩略图（macOS 真实渲染，无 PDF）
    if tools["qlmanage"]:
        ok, log = _run_cmd([tools["qlmanage"], "-t", "-s", "1200",
                            "-o", str(outdir), str(docx_path)])
        produced = outdir / (docx_path.name + ".png")
        if ok and produced.exists() and _looks_like_png(produced):
            target = outdir / f"{base}.png"
            produced.replace(target)
            status.update(status="rendered_png", renderer="qlmanage",
                          pngs=[str(target)])
            status["notes"].append("qlmanage 生成的是首页缩略图 PNG，非完整分页预览")
            return status
        status["notes"].append(f"qlmanage 失败（已如实记录）: {log[-300:]}")

    # 5) 兜底：自足 HTML 预览（明确标注无 PDF 渲染器）
    html_path = outdir / f"{base}.html"
    html_path.write_text(_md_to_fallback_html(md_text), encoding="utf-8")
    status.update(status="html_fallback", renderer=None, pdf=None, pngs=[])
    status["html"] = str(html_path)
    status["notes"].append("未找到任何 PDF/PNG 渲染器（soffice/pandoc/textutil+cupsfilter/"
                           "qlmanage 均不可用），已生成自足 HTML 预览；不存在伪造的 PDF/PNG")
    return status


def _md_to_fallback_html(md_text):
    """把 Markdown 子集渲染为自足 HTML（仅在无渲染器时使用，带显式声明）。"""
    import html as _html

    def inline(runs):
        s = ""
        for text, bold, italic in runs:
            t = _html.escape(text)
            if bold:
                t = f"<strong>{t}</strong>"
            if italic:
                t = f"<em>{t}</em>"
            s += t
        return s

    body = []
    for block in parse_markdown(md_text):
        if block[0] in ("h1", "h2", "h3"):
            body.append(f"<{block[0]}>{inline(block[1])}</{block[0]}>")
        elif block[0] == "p":
            body.append(f"<p>{inline(block[1])}</p>")
        elif block[0] == "li":
            body.append(f"<ul><li>{inline(block[1])}</li></ul>")
        elif block[0] == "table":
            ths = "".join(f"<th>{inline(c)}</th>" for c in block[1])
            trs = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>"
                          for row in block[2])
            body.append(f"<table border='1' cellspacing='0' cellpadding='4'>"
                        f"<tr>{ths}</tr>{trs}</table>")
    banner = ("<p style='background:#fff3cd;border:1px solid #ffc107;padding:8px'>"
              "⚠ 未找到 PDF 渲染器（soffice / pandoc / textutil+cupsfilter / qlmanage "
              "均不可用），此为 HTML 兜底预览，<strong>不存在伪造的 PDF/PNG 预览文件</strong>。"
              "</p>")
    return ("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
            "<title>HTML 兜底预览</title>"
            "<style>body{font-family:Georgia,'Songti SC',serif;max-width:800px;margin:2em auto;"
            "line-height:1.7}table{border-collapse:collapse}</style></head><body>"
            + banner + "".join(body) + "</body></html>")


# ---------------------------------------------------------------------------
# forge_report.md 与 result.json 装配
# ---------------------------------------------------------------------------

def artifact_entry(path):
    p = Path(path)
    return {"path": str(p), "bytes": p.stat().st_size, "sha256": sha256_of(p)}


def write_forge_report(out_path, verifications, preview_status, applied, misses,
                       artifacts, extra_notes=None):
    lines = ["# Forge Report — 产物锻造验证报告", "",
             f"- 生成时间（UTC）：{iso_now()}",
             f"- 生成工具：docx_forge.py（纯 Python3 标准库，author={REVISION_AUTHOR}）",
             "", "## 1. DOCX 验证（round-trip proof）", ""]
    for v in verifications:
        lines += [f"### {Path(v['docx']).name}", "",
                  f"- 大小：{v['size_bytes']} bytes",
                  f"- sha256：`{v['sha256']}`",
                  f"- zip 完整性：{'通过' if v.get('zip_ok') else '失败'}",
                  f"- document.xml 良构：{'通过' if v.get('xml_ok') else '失败'}",
                  f"- 段落数（w:p）：{v.get('paragraphs', '-')}",
                  f"- 表格数（w:tbl）：{v.get('tables', '-')}",
                  f"- 修订 w:ins / w:del：{v.get('ins_count', 0)} / {v.get('del_count', 0)}"]
        if v.get("retention") is not None:
            verdict = "通过" if v["retention_ok"] else "未达标"
            lines.append(f"- round-trip 保留率：{v['retention']:.4f}"
                         f"（阈值 {RETENTION_THRESHOLD}，{verdict}；"
                         f"参考 token {v['ref_tokens']} / 反抽 token {v['docx_tokens']}）")
        if v.get("errors"):
            lines.append(f"- 错误：{'; '.join(v['errors'])}")
        lines.append("")
    lines += ["## 2. 修订留痕", "",
              f"- edit_plan 修改条数：{len(applied) + len(misses)}",
              f"- 命中：{len(applied)}；未命中：{len(misses)}", ""]
    for rec in applied:
        lines.append(f"- ✅ #{rec['编号']} `{rec['原文'][:40]}` → `{rec['新文'][:40]}`（{rec['理由']}）")
    for rec in misses:
        lines.append(f"- ❌ #{rec['编号']} 未命中：`{rec['原文'][:40]}`（{rec['命中状态']}）——如实记录，未做近似替换")
    lines += ["", "## 3. 预览渲染（真实渲染，未伪造）", "",
              f"- preview_status：`{preview_status.get('status')}`",
              f"- 命中渲染器：{preview_status.get('renderer') or '无'}",
              f"- 工具探测：{json.dumps(preview_status.get('detected', {}), ensure_ascii=False)}"]
    for note in preview_status.get("notes", []):
        lines.append(f"- 说明：{note}")
    if preview_status.get("pdf"):
        lines.append(f"- PDF：{preview_status['pdf']}")
    for png in preview_status.get("pngs", []):
        lines.append(f"- PNG：{png}")
    if preview_status.get("html"):
        lines.append(f"- HTML 兜底预览：{preview_status['html']}")
    lines += ["", "## 4. 产物清单", "",
              "| 文件 | 字节数 | sha256 |", "|---|---|---|"]
    for a in artifacts:
        lines.append(f"| {a['path']} | {a['bytes']} | `{a['sha256'][:16]}…` |")
    for note in (extra_notes or []):
        lines += ["", f"> 注：{note}"]
    lines.append("")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(out_path)


def assemble_result_json(case, outdir, verifications, preview_status, applied,
                         misses, artifacts):
    """装配 result.json：原样保留 case.json 中 output_contract 的全部键。

    契约键没有内容可填时写 "PENDING"，绝不留空也绝不编造。
    """
    contract = case.get("output_contract") or {}
    result = {}
    change_records = ([{"id": r["编号"], "type": r["类型"], "find": r["原文"],
                        "replace": r["新文"], "reason": r["理由"],
                        "status": "applied", "author": REVISION_AUTHOR}
                       for r in applied]
                      + [{"id": r["编号"], "type": r["类型"], "find": r["原文"],
                          "replace": r["新文"], "reason": r["理由"],
                          "status": "missed"} for r in misses])
    for key, default in contract.items():
        if key == "case_id":
            result[key] = case.get("case_id", "PENDING")
        elif key == "deliverable":
            result[key] = [a["path"] for a in artifacts
                           if a["path"].endswith(".docx")] or "PENDING"
        elif key == "preserved_facts":
            facts = case.get("facts") or case.get("preserved_facts")
            result[key] = facts if facts else "PENDING"
        elif key == "evidence_map":
            result[key] = {a["path"]: a["sha256"] for a in artifacts} or "PENDING"
        elif key == "change_log":
            result[key] = change_records or "PENDING"
        else:
            result[key] = default if default not in (None, "") else "PENDING"
    if "case_id" not in result:
        result["case_id"] = case.get("case_id", "PENDING")

    result.update({
        "status": "ok" if all(v["ok"] for v in verifications) else "partial",
        "skill": "editable-deliverable-forge",
        "generated_at_utc": iso_now(),
        "artifacts": artifacts,
        "round_trip": [
            {"docx": v["docx"], "retention": v.get("retention"),
             "paragraphs": v.get("paragraphs"), "tables": v.get("tables"),
             "ins": v.get("ins_count", 0), "del": v.get("del_count", 0),
             "ok": v["ok"]} for v in verifications],
        "preview_status": preview_status,
        "revision_stats": {"planned": len(applied) + len(misses),
                           "applied": len(applied), "missed": len(misses),
                           "author": REVISION_AUTHOR},
        "uncertainty": ("PENDING" if not misses else
                        f"{len(misses)} 条 edit_plan 修改未命中原文，需人工处理"),
    })
    out_path = Path(outdir) / "result.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return out_path, result


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------

def cmd_build(args):
    md_text = Path(args.md).read_text(encoding="utf-8")
    blocks = parse_markdown(md_text)
    rev_date = iso_now()
    applied, misses = [], []
    if args.edit_plan:
        plan = json.loads(Path(args.edit_plan).read_text(encoding="utf-8"))
        edits = plan.get("edits", plan) if isinstance(plan, dict) else plan
        applied, misses = apply_edit_plan(blocks, edits, rev_date)
    document_xml = blocks_to_document_xml(blocks, rev_date)
    write_docx(document_xml, args.out)
    print(f"[build] 写出 {args.out}（{Path(args.out).stat().st_size} bytes，"
          f"修订命中 {len(applied)} / 未命中 {len(misses)}）")
    if args.edit_plan and args.review_csv:
        write_review_csv(applied, misses, args.review_csv)
        print(f"[build] 复核 CSV：{args.review_csv}")
    if misses:
        print(f"[build] 警告：{len(misses)} 条修改未命中原文，已如实记录", file=sys.stderr)
    return 0


def cmd_verify(args):
    md_text = Path(args.md).read_text(encoding="utf-8") if args.md else None
    result = verify_docx(args.docx, md_text=md_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.report:
        write_forge_report(args.report, [result],
                           {"status": "not_run", "detected": {}}, [], [],
                           [artifact_entry(args.docx)])
        print(f"[verify] 报告：{args.report}")
    return 0 if result["ok"] else 1


def cmd_render(args):
    md_text = Path(args.md).read_text(encoding="utf-8") if args.md else ""
    status = render_preview(args.docx, md_text, args.outdir, base=args.base)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args):
    """端到端：case.json + draft.md [+ edit_plan.json] → 全部交付物 + result.json。"""
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    md_text = Path(args.md).read_text(encoding="utf-8")
    rev_date = iso_now()

    # 1) 干净版 DOCX
    plain_docx = outdir / "deliverable.docx"
    blocks_plain = parse_markdown(md_text)
    write_docx(blocks_to_document_xml(blocks_plain, rev_date), plain_docx)

    # 2) 修订版 DOCX + 复核 CSV
    applied, misses, tracked_docx, review_csv = [], [], None, None
    if args.edit_plan and Path(args.edit_plan).exists():
        plan = json.loads(Path(args.edit_plan).read_text(encoding="utf-8"))
        edits = plan.get("edits", plan) if isinstance(plan, dict) else plan
        blocks_tracked = parse_markdown(md_text)
        applied, misses = apply_edit_plan(blocks_tracked, edits, rev_date)
        tracked_docx = outdir / "deliverable_tracked.docx"
        write_docx(blocks_to_document_xml(blocks_tracked, rev_date), tracked_docx)
        review_csv = outdir / "review_record.csv"
        write_review_csv(applied, misses, review_csv)

    # 3) round-trip 验证（修订版按“接受全部修订后”的期望文本对比）
    verifications = [verify_docx(plain_docx, md_text=md_text)]
    if tracked_docx:
        expected = md_plain_text(md_text)
        for rec in applied:  # 期望文本 = 原文应用全部命中修改
            expected = expected.replace(rec["原文"], rec["新文"], 1)
        verifications.append(verify_docx(tracked_docx, expected_text=expected))

    # 4) 真实预览渲染（优先渲染修订版，它是要交付人工复核的主产物）
    preview_src = tracked_docx or plain_docx
    preview_status = render_preview(preview_src, md_text, outdir)

    # 5) 产物清单 + forge_report + result.json
    artifact_paths = [plain_docx]
    if tracked_docx:
        artifact_paths.append(tracked_docx)
    if review_csv:
        artifact_paths.append(review_csv)
    if preview_status.get("pdf"):
        artifact_paths.append(Path(preview_status["pdf"]))
    artifact_paths += [Path(x) for x in preview_status.get("pngs", [])]
    if preview_status.get("html"):
        artifact_paths.append(Path(preview_status["html"]))
    artifacts = [artifact_entry(p) for p in artifact_paths]

    report_path = write_forge_report(outdir / "forge_report.md", verifications,
                                     preview_status, applied, misses, artifacts)
    artifacts.append(artifact_entry(report_path))
    result_path, result = assemble_result_json(case, outdir, verifications,
                                               preview_status, applied, misses,
                                               artifacts)
    print(f"[run] 完成。status={result['status']} "
          f"retention={[v.get('retention') for v in verifications]} "
          f"preview={preview_status['status']}")
    print(f"[run] result.json：{result_path}")
    return 0 if result["status"] == "ok" else 1


def cmd_extract(args):
    print(docx_extract_text(args.docx, include_deleted=args.include_deleted))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Markdown→DOCX 编译器：可编辑产物 / 修订留痕 / round-trip 验证 / 真实预览渲染")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="Markdown 编译为 DOCX（可选修订留痕）")
    p.add_argument("--md", required=True, help="输入 Markdown 成稿")
    p.add_argument("--out", required=True, help="输出 DOCX 路径")
    p.add_argument("--edit-plan", help="edit_plan.json（find/replace/reason 列表）")
    p.add_argument("--review-csv", help="复核记录 CSV 输出路径")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("verify", help="DOCX round-trip 验证")
    p.add_argument("--docx", required=True)
    p.add_argument("--md", help="参考 Markdown（用于文本保留率对比）")
    p.add_argument("--report", help="可选：写出 forge_report.md")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("render", help="真实渲染预览（降级链，绝不伪造）")
    p.add_argument("--docx", required=True)
    p.add_argument("--md", help="Markdown 源（HTML 兜底时使用）")
    p.add_argument("--outdir", required=True)
    p.add_argument("--base", default="preview", help="预览文件基名")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("run", help="端到端：编译+修订+验证+渲染+装配 result.json")
    p.add_argument("--case", required=True, help="/input/case.json")
    p.add_argument("--md", required=True, help="成稿 Markdown")
    p.add_argument("--edit-plan", help="可选：修改记录 edit_plan.json")
    p.add_argument("--outdir", required=True, help="输出目录（/app/output）")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("extract", help="从 DOCX 反抽纯文本（调试用）")
    p.add_argument("--docx", required=True)
    p.add_argument("--include-deleted", action="store_true",
                   help="包含 w:delText（即修订前原文）")
    p.set_defaults(func=cmd_extract)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
