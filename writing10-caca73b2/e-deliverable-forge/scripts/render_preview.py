#!/usr/bin/env python3
"""render_preview.py — 仅用标准库生成稿件的 SVG 分页预览。

说明:
  * 页面近似 A4(794x1123 px), 白底, 含页边距与页码;
  * 朴素 CJK 感知换行: CJK 字符宽度 = 2 单位, ASCII = 1 单位,
    1 单位 = 字号的一半(等宽近似); 这是排版近似预览, 不是出版级 PDF;
  * 标题大号加粗, 题注居中加粗, 表格绘制网格线;
  * 输出 preview-1.svg ... preview-N.svg, 完全确定性(同输入必得同输出)。

用法:
    python3 render_preview.py --input manuscript.md --out-dir ./preview [--prefix preview]

退出码: 0 = 成功; 2 = 用法/IO 错误。
仅使用 Python 标准库, 兼容 Python >= 3.9。
"""

import argparse
import html
import os
import re
import sys
import unicodedata

PAGE_W = 794
PAGE_H = 1123
MARGIN = 72
CONTENT_W = PAGE_W - 2 * MARGIN

FONT_STACK = "'Courier New','Noto Sans Mono','PingFang SC','Microsoft YaHei','Noto Sans CJK SC',monospace"

CAPTION_RE = re.compile(
    r"^\s*(图|表|Figure|Fig\.?|Table)\s*\d+\s*[.．:：]\s*\S.*$"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
EMPH_RE = re.compile(r"\*\*(.+?)\*\*|\*([^*]+?)\*")

STYLE = {
    "h1": {"size": 20, "bold": True, "lead": 30, "before": 14, "after": 8},
    "h2": {"size": 16, "bold": True, "lead": 24, "before": 12, "after": 6},
    "h3": {"size": 14, "bold": True, "lead": 21, "before": 10, "after": 5},
    "para": {"size": 12, "bold": False, "lead": 18, "before": 0, "after": 6},
    "caption": {"size": 11, "bold": True, "lead": 16, "before": 4, "after": 8},
    "table": {"size": 11, "bold": False, "lead": 16, "before": 4, "after": 8},
}


def char_units(ch):
    """CJK/宽字符记 2 单位, 其余记 1 单位。"""
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def text_units(s):
    return sum(char_units(c) for c in s)


def strip_emphasis(s):
    return EMPH_RE.sub(lambda m: m.group(1) or m.group(2), s)


def wrap_text(text, max_units):
    """按宽度单位朴素换行, 返回行列表。"""
    lines = []
    cur = ""
    cur_w = 0
    for ch in text:
        w = char_units(ch)
        if cur_w + w > max_units and cur:
            lines.append(cur)
            cur = ch
            cur_w = w
        else:
            cur += ch
            cur_w += w
    if cur:
        lines.append(cur)
    return lines or [""]


def parse_markdown(text):
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
            blocks.append({"type": "h%d" % min(len(m.group(1)), 3), "text": m.group(2).strip()})
            i += 1
            continue
        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
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
            blocks.append({"type": "para", "text": "• " + m.group(1).strip()})
            i += 1
            continue
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
        blocks.append({"type": "para", "text": " ".join(para)})
    return blocks


def esc(s):
    return html.escape(s, quote=True)


def text_elem(x, y, content, size, bold=False, anchor=None, fill="#000000"):
    attrs = 'x="%d" y="%d" font-size="%d" fill="%s"' % (x, y, size, fill)
    if bold:
        attrs += ' font-weight="bold"'
    if anchor:
        attrs += ' text-anchor="%s"' % anchor
    return "<text %s>%s</text>" % (attrs, esc(content))


def layout(blocks):
    """把块排成页面元素列表, 返回 pages: list[list[str]]。"""
    pages = []
    elems = []
    y = MARGIN
    page_no = 0

    def flush_page():
        nonlocal elems, y, page_no
        page_no += 1
        elems.append(
            text_elem(PAGE_W // 2, PAGE_H - 28, "- %d -" % page_no, 10, anchor="middle", fill="#666666")
        )
        pages.append(elems)
        elems = []
        y = MARGIN

    def ensure(height):
        if y + height > PAGE_H - MARGIN:
            flush_page()

    for b in blocks:
        st = STYLE[b["type"] if b["type"] in STYLE else "para"]
        unit_px = st["size"] * 0.5
        if b["type"] == "table":
            rows = b["rows"]
            ncols = max(len(r) for r in rows)
            rows = [r + [""] * (ncols - len(r)) for r in rows]
            col_units = [1] * ncols
            for r in rows:
                for c, cell in enumerate(r):
                    col_units[c] = max(col_units[c], min(text_units(strip_emphasis(cell)), 40))
            total = sum(col_units)
            col_px = [max(int(CONTENT_W * u / total), 40) for u in col_units]
            y += st["before"]
            for r_idx, row in enumerate(rows):
                cell_lines = [
                    wrap_text(strip_emphasis(cell), max(int(px / unit_px) - 2, 4))
                    for cell, px in zip(row, col_px)
                ]
                row_h = max(len(cl) for cl in cell_lines) * st["lead"] + 8
                ensure(row_h)
                x = MARGIN
                for cell, px, cl in zip(row, col_px, cell_lines):
                    elems.append(
                        '<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#444444" stroke-width="1"/>'
                        % (x, y, px, row_h)
                    )
                    for li, ln in enumerate(cl):
                        elems.append(
                            text_elem(
                                x + 4,
                                y + 6 + (li + 1) * st["lead"] - 4,
                                ln,
                                st["size"],
                                bold=(r_idx == 0),
                            )
                        )
                    x += px
                y += row_h
            y += st["after"]
            continue

        text = strip_emphasis(b["text"])
        max_units = max(int(CONTENT_W / unit_px), 8)
        wrapped = wrap_text(text, max_units)
        block_h = st["before"] + len(wrapped) * st["lead"] + st["after"]
        # 单段过高时允许跨页: 逐行排放
        y += st["before"]
        for ln in wrapped:
            ensure(st["lead"])
            if b["type"] == "caption":
                elems.append(
                    text_elem(PAGE_W // 2, y + st["lead"] - 5, ln, st["size"], bold=True, anchor="middle")
                )
            else:
                elems.append(text_elem(MARGIN, y + st["lead"] - 5, ln, st["size"], bold=st["bold"]))
            y += st["lead"]
        y += st["after"]

    flush_page()
    return pages


def page_svg(elems):
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="%s">'
        % (PAGE_W, PAGE_H, PAGE_W, PAGE_H, FONT_STACK),
        '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff" stroke="#cccccc" stroke-width="1"/>'
        % (PAGE_W, PAGE_H),
    ]
    parts.extend(elems)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="生成稿件的 SVG 分页预览(排版近似, 非出版级 PDF)。"
    )
    parser.add_argument("--input", required=True, help="稿件 markdown 路径")
    parser.add_argument("--out-dir", required=True, help="SVG 输出目录")
    parser.add_argument("--prefix", default="preview", help="文件名前缀(默认 preview)")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        sys.stderr.write("ERROR: cannot read %s: %s\n" % (args.input, exc))
        return 2

    blocks = parse_markdown(text)
    if not blocks:
        sys.stderr.write("ERROR: no content blocks parsed from %s\n" % args.input)
        return 2

    pages = layout(blocks)
    os.makedirs(args.out_dir, exist_ok=True)
    written = []
    for idx, elems in enumerate(pages, start=1):
        path = os.path.join(args.out_dir, "%s-%d.svg" % (args.prefix, idx))
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(page_svg(elems))
        except OSError as exc:
            sys.stderr.write("ERROR: cannot write %s: %s\n" % (path, exc))
            return 2
        written.append(path)

    sys.stdout.write(
        "rendered %d page(s) from %s -> %s\n"
        % (len(written), args.input, ", ".join(os.path.basename(p) for p in written))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
