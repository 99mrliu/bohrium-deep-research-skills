#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_render.py — 写作产物可检查预览渲染（纯 Python 3 标准库）。

把 Markdown 稿件渲染为：
  1. preview.html      —— 自包含 HTML（内联 CSS，lang="zh-CN"），正确处理
     标题 / 列表 / 表格 / 加粗 / 行内代码 / 引用 / 代码块，中文正常；
  2. preview_pageN.svg —— 逐行文本 SVG 预览，每页固定行数分页。

渲染校验（不过即失败）：
  - 稿件中的每个标题字符串必须出现在 HTML 产物中；
  - preview.html 与各 SVG 产物非空且达到最小体积。
校验失败：把失败原因如实写入 <outdir>/render_error.json，并以非零退出，
禁止假装成功。

退出码
------
  0  成功
  2  输入缺失或不可读
  6  渲染或校验失败（render_error.json 已写出）

输出确定性：不含时间戳等易变量。
"""
import argparse
import html
import json
import os
import re
import sys

MIN_HTML_BYTES = 200
MIN_SVG_BYTES = 100

CSS = """
body{font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
max-width:820px;margin:2rem auto;padding:0 1.2rem;line-height:1.8;color:#1a1a1a;}
h1{border-bottom:2px solid #3357c0;padding-bottom:.3rem;}
h2{border-bottom:1px solid #c9c9e0;padding-bottom:.2rem;}
table{border-collapse:collapse;width:100%;margin:1rem 0;}
th,td{border:1px solid #99a;padding:.4rem .6rem;text-align:left;}
th{background:#eef2fb;}
code{background:#f2f2f2;padding:.1rem .3rem;border-radius:3px;}
pre{background:#f7f7f7;padding:.8rem;overflow:auto;border-radius:4px;}
blockquote{border-left:4px solid #99b;margin:.5rem 0;padding:.2rem 1rem;color:#555;}
""".strip()


def render_inline(text):
    """行内渲染：先转义，再处理 code / 加粗 / 斜体。"""
    t = html.escape(text)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', t)
    return t


def strip_inline(text):
    """去掉行内 Markdown 记号，得到纯文本（用于标题校验）。"""
    t = re.sub(r'`([^`]*)`', r'\1', text)
    t = t.replace("**", "").replace("*", "")
    return t.strip()


def split_row(line):
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def is_block_start(line):
    s = line.strip()
    if not s:
        return True
    return bool(
        re.match(r'^#{1,6}\s', s)
        or s.startswith("```")
        or re.match(r'^[-*]\s+', s)
        or re.match(r'^\d+[.、]\s+', s)
        or s.startswith(">")
        or s.startswith("|")
    )


def md_to_html(md_text):
    """Markdown 子集 -> HTML 块列表。返回 (blocks, headings)。"""
    lines = md_text.splitlines()
    blocks = []
    headings = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        # 代码块
        if s.startswith("```"):
            j = i + 1
            code = []
            while j < n and not lines[j].strip().startswith("```"):
                code.append(lines[j])
                j += 1
            blocks.append("<pre><code>%s</code></pre>" % html.escape("\n".join(code)))
            i = j + 1
            continue
        # 标题
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            level = len(m.group(1))
            raw = m.group(2).strip()
            headings.append(strip_inline(raw))
            blocks.append("<h%d>%s</h%d>" % (level, render_inline(raw), level))
            i += 1
            continue
        # 表格：当前行以 | 开头且下一行是分隔行
        if s.startswith("|") and i + 1 < n and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            header = split_row(line)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            out = ["<table><thead><tr>"]
            out += ["<th>%s</th>" % render_inline(c) for c in header]
            out.append("</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join("<td>%s</td>" % render_inline(c) for c in r) + "</tr>")
            out.append("</tbody></table>")
            blocks.append("".join(out))
            continue
        # 无序列表
        if re.match(r'^\s*[-*]\s+', line):
            items = []
            while i < n and re.match(r'^\s*[-*]\s+', lines[i]):
                items.append(re.sub(r'^\s*[-*]\s+', '', lines[i]).strip())
                i += 1
            blocks.append("<ul>" + "".join("<li>%s</li>" % render_inline(x) for x in items) + "</ul>")
            continue
        # 有序列表
        if re.match(r'^\s*\d+[.、]\s+', line):
            items = []
            while i < n and re.match(r'^\s*\d+[.、]\s+', lines[i]):
                items.append(re.sub(r'^\s*\d+[.、]\s+', '', lines[i]).strip())
                i += 1
            blocks.append("<ol>" + "".join("<li>%s</li>" % render_inline(x) for x in items) + "</ol>")
            continue
        # 引用
        if s.startswith(">"):
            qlines = []
            while i < n and lines[i].strip().startswith(">"):
                qlines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append("<blockquote><p>%s</p></blockquote>" % render_inline(" ".join(qlines)))
            continue
        # 段落：收集到空行或下一个块起点
        para = [s]
        i += 1
        while i < n and lines[i].strip() and not is_block_start(lines[i]):
            para.append(lines[i].strip())
            i += 1
        blocks.append("<p>%s</p>" % render_inline(" ".join(para)))
    return blocks, headings


def build_html(blocks, title):
    body = "\n".join(blocks)
    return ("<!DOCTYPE html>\n"
            "<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>%s</title>\n<style>\n%s\n</style>\n</head>\n<body>\n%s\n</body>\n</html>\n"
            % (html.escape(title), CSS, body))


def xml_escape(s):
    return html.escape(s, quote=True)


def render_svg_pages(md_text, outdir, lines_per_page, prefix="preview_page"):
    """逐行文本 SVG 预览，每页固定行数分页。"""
    raw_lines = md_text.splitlines()
    if lines_per_page < 1:
        lines_per_page = 1
    pages = [raw_lines[k:k + lines_per_page]
             for k in range(0, len(raw_lines), lines_per_page)] or [[]]
    W, PAD, LH, FS = 794, 40, 22, 13
    files = []
    for idx, page in enumerate(pages, 1):
        H = PAD * 2 + LH * (len(page) + 1)
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H),
            '<rect width="%d" height="%d" fill="#ffffff" stroke="#cccccc"/>' % (W, H),
            ('<text x="%d" y="%d" font-size="11" fill="#888888" font-family="monospace">'
             '第 %d 页 / 共 %d 页</text>') % (PAD, PAD - 10, idx, len(pages)),
        ]
        y = PAD + LH
        for ln in page:
            disp = ln if len(ln) <= 88 else ln[:85] + "..."
            parts.append(
                '<text x="%d" y="%d" font-size="%d" fill="#222222" '
                'font-family="\'PingFang SC\',\'Microsoft YaHei\',\'Noto Sans CJK SC\',monospace">%s</text>'
                % (PAD, y, FS, xml_escape(disp)))
            y += LH
        parts.append("</svg>")
        fname = "%s%d.svg" % (prefix, idx)
        with open(os.path.join(outdir, fname), "w", encoding="utf-8") as fh:
            fh.write("\n".join(parts) + "\n")
        files.append(fname)
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description="Markdown -> 自包含 HTML + 分页 SVG 预览")
    ap.add_argument("--md", required=True, help="Markdown 稿件路径（只读）")
    ap.add_argument("--outdir", required=True, help="输出目录")
    ap.add_argument("--lines-per-page", type=int, default=40, help="SVG 每页行数（默认 40）")
    ap.add_argument("--title", default=None, help="HTML 标题（默认取首个一级标题或文件名）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.md):
        print("ERROR: 输入不存在: %s" % args.md, file=sys.stderr)
        return 2
    try:
        with open(args.md, "r", encoding="utf-8") as fh:
            md_text = fh.read()
    except OSError as e:
        print("ERROR: 读取失败: %s" % e, file=sys.stderr)
        return 2

    errors = []
    html_path = os.path.join(args.outdir, "preview.html")
    svg_files = []

    try:
        os.makedirs(args.outdir, exist_ok=True)
        blocks, headings = md_to_html(md_text)
        title = args.title
        if not title:
            m = re.search(r'^#\s+(.*)$', md_text, re.MULTILINE)
            title = strip_inline(m.group(1)) if m else os.path.basename(args.md)
        html_doc = build_html(blocks, title)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html_doc)
        svg_files = render_svg_pages(md_text, args.outdir, args.lines_per_page)
    except Exception as e:  # 渲染异常：如实记录，绝不假装成功
        errors.append("渲染异常: %r" % (e,))
        html_doc = ""

    # --- 渲染校验 ---
    if not errors:
        if not os.path.isfile(html_path) or os.path.getsize(html_path) < MIN_HTML_BYTES:
            errors.append("preview.html 缺失或体积过小（<%d 字节）" % MIN_HTML_BYTES)
        for h in headings:
            if h and h not in html_doc:
                errors.append("标题字符串未出现在 HTML 产物中: %s" % h)
        for f in svg_files:
            p = os.path.join(args.outdir, f)
            if not os.path.isfile(p) or os.path.getsize(p) < MIN_SVG_BYTES:
                errors.append("SVG 产物缺失或体积过小: %s" % f)
        if not svg_files:
            errors.append("未生成任何 SVG 预览页")

    if errors:
        err = {"status": "error", "script": "preview_render.py",
               "input": args.md, "errors": errors}
        try:
            os.makedirs(args.outdir, exist_ok=True)
            with open(os.path.join(args.outdir, "render_error.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(err, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        except OSError:
            pass
        for e in errors:
            print("ERROR: %s" % e, file=sys.stderr)
        return 6

    print("preview.html: %s（%d 字节）" % (html_path, os.path.getsize(html_path)))
    for f in svg_files:
        p = os.path.join(args.outdir, f)
        print("%s（%d 字节）" % (p, os.path.getsize(p)))
    print("校验通过：%d 个标题均在产物中，产物非空。" % len(headings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
