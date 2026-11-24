#!/usr/bin/env python3
"""render_preview.py -- 开题文档 JSON -> 纯文本 SVG 预览 + 自包含 HTML 预览页。

用法:
    python3 render_preview.py DOC_JSON OUT_SVG OUT_HTML

产物（均为 UTF-8 文本，符合无二进制约束）:
  OUT_SVG   逐节卡片图：编号+标题+首段摘要+段落/表格/字数统计；
            阶段计划节（id=schedule）附加横向甘特条，数据直接解析自该节
            表格（开始季度/结束季度列），与 Markdown 交付同源。
  OUT_HTML  自包含预览页：内嵌样式 + 内嵌同一份 SVG，浏览器可直接打开。

确定性: 不读系统时钟，同输入同输出。渲染前复用 render_markdown 的
schema 校验，校验失败以退出码 2 拦截。
"""
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_markdown import validate_document  # noqa: E402

W = 720
CARD_X, CARD_W = 20, 680
CARD_H = 96
SUMMARY_CHARS = 52          # 摘要每行字符数
SUMMARY_LINES = 2
COLOR_HEAD = "#1d4e89"
COLOR_BAR = ["#3a7ca5", "#5c9ead", "#8fb8c9", "#2f6690", "#4d8fb1", "#79a9c2"]


def esc(s):
    return html.escape(str(s), quote=True)


def char_count(paras):
    """字数口径：段落文本去除空白后的字符数（不含表格，见 schema 第 7 节）。"""
    return sum(len("".join(p.split())) for p in paras)


def summary_lines(paras):
    text = paras[0] if paras else ""
    lines = [text[i:i + SUMMARY_CHARS]
             for i in range(0, SUMMARY_CHARS * SUMMARY_LINES, SUMMARY_CHARS)]
    lines = [ln for ln in lines if ln]
    if len(text) > SUMMARY_CHARS * SUMMARY_LINES and lines:
        lines[-1] = lines[-1] + " …"
    return lines


def gantt_rows(doc):
    for sec in doc["sections"]:
        if sec.get("id") == "schedule":
            tab = sec["table"]
            rows = []
            for r in tab["rows"]:
                rows.append({"code": r[0], "task": r[1],
                             "start": int(r[2]), "end": int(r[3]),
                             "deliverable": r[4]})
            return rows
    return []


def render_gantt(doc, x, y, width):
    """在 (x, y) 起渲染甘特条，返回 (svg 片段列表, 占用高度)。"""
    meta = doc["meta"]
    quarters = int(meta["period"]["quarters"])
    rows = gantt_rows(doc)
    label_w = 200
    bar_x0 = x + label_w + 10
    bar_w = width - label_w - 30
    qw = bar_w / quarters
    row_h = 22
    parts = []
    # 季度网格与轴标签
    for q in range(quarters + 1):
        gx = bar_x0 + q * qw
        parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#ddd"/>'
                     % (gx, y + 14, gx, y + 14 + len(rows) * row_h))
        if q < quarters:
            parts.append('<text x="%.1f" y="%d" font-size="9" fill="#888">Q%d</text>'
                         % (gx + 3, y + 10, q + 1))
    for i, r in enumerate(rows):
        ry = y + 16 + i * row_h
        bx = bar_x0 + (r["start"] - 1) * qw
        bw = (r["end"] - r["start"] + 1) * qw
        parts.append('<text x="%d" y="%d" font-size="10" fill="#333">%s %s</text>'
                     % (x + 4, ry + 11, esc(r["code"]), esc(r["task"])))
        parts.append('<rect x="%.1f" y="%d" width="%.1f" height="13" rx="3" '
                     'fill="%s"/>' % (bx, ry, bw, COLOR_BAR[i % len(COLOR_BAR)]))
        parts.append('<text x="%.1f" y="%d" font-size="9" fill="#666">Q%d–Q%d</text>'
                     % (bx + bw + 3, ry + 11, r["start"], r["end"]))
    return parts, 16 + len(rows) * row_h + 8


def render_svg(doc):
    meta = doc["meta"]
    period = meta["period"]
    # 先排版计算总高度
    cards = sorted(doc["sections"], key=lambda s: s["number"])
    heights = []
    for sec in cards:
        h = CARD_H
        if sec.get("id") == "schedule":
            h += 16 + len(gantt_rows(doc)) * 22 + 8
        heights.append(h)
    total_h = 70 + sum(heights) + 12 * len(cards) + 40

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="sans-serif">' % (W, total_h, W, total_h),
        '<rect x="0" y="0" width="%d" height="%d" fill="#fafbfc"/>' % (W, total_h),
        '<text x="%d" y="26" font-size="15" font-weight="bold" fill="#222">%s</text>'
        % (CARD_X, esc(meta["title"])),
        '<text x="%d" y="46" font-size="11" fill="#555">%s · %s · 周期 %s 至 %s · '
        '经费 %s 万元 · 版本 %s（%s）</text>'
        % (CARD_X, esc(meta["discipline"]), esc(meta["degree"]),
           esc(period["start"]), esc(period["end"]),
           esc(meta["budget_wan"]), esc(meta["version"]), esc(meta["date"])),
    ]
    y = 62
    for sec, h in zip(cards, heights):
        is_gantt = sec.get("id") == "schedule"
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" rx="8" fill="white" '
                     'stroke="%s" stroke-width="1.5"/>'
                     % (CARD_X, y, CARD_W, h,
                        "#c97b2d" if is_gantt else "#b9c6d4"))
        parts.append('<text x="%d" y="%d" font-size="13" font-weight="bold" '
                     'fill="%s">[%d] %s</text>'
                     % (CARD_X + 12, y + 22, COLOR_HEAD, sec["number"],
                        esc(sec["title"])))
        for i, ln in enumerate(summary_lines(sec["paragraphs"])):
            parts.append('<text x="%d" y="%d" font-size="11" fill="#333">%s</text>'
                         % (CARD_X + 12, y + 42 + i * 15, esc(ln)))
        stats = "段落 %d · 表格 %s · 字数 %d" % (
            len(sec["paragraphs"]),
            "1" if sec.get("table") else "0",
            char_count(sec["paragraphs"]))
        parts.append('<text x="%d" y="%d" font-size="10" fill="#888">%s</text>'
                     % (CARD_X + 12, y + CARD_H - 10, esc(stats)))
        if is_gantt:
            gp, _ = render_gantt(doc, CARD_X + 12, y + CARD_H, CARD_W - 24)
            parts.extend(gp)
        y += h + 12
    parts.append('<text x="%d" y="%d" font-size="10" fill="#999">'
                 '本 SVG 为纯文本预览，由 document JSON 确定性渲染；'
                 '甘特条数据与 Markdown 交付中的阶段计划表同源。</text>'
                 % (CARD_X, total_h - 12))
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(doc, svg_text):
    meta = doc["meta"]
    cards = sorted(doc["sections"], key=lambda s: s["number"])
    li = "".join(
        "<li><b>[%d] %s</b> —— 段落 %d，字数 %d</li>"
        % (s["number"], esc(s["title"]), len(s["paragraphs"]),
           char_count(s["paragraphs"]))
        for s in cards)
    return """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>%(title)s —— 开题预览</title>
<style>
body { font-family: sans-serif; max-width: 780px; margin: 24px auto; color: #222; }
h1 { font-size: 20px; }
.meta { color: #555; font-size: 13px; }
.toc { background: #f4f7fa; border-radius: 8px; padding: 8px 8px 8px 28px; }
.note { color: #999; font-size: 12px; }
svg { max-width: 100%%; height: auto; border: 1px solid #e2e8f0; border-radius: 8px; }
</style>
</head>
<body>
<h1>%(title)s</h1>
<p class="meta">%(discipline)s · %(degree)s · 申请人 %(author)s · 导师 %(advisor)s ·
版本 %(version)s（%(date)s）</p>
<h2>章节速览</h2>
<ol class="toc">%(li)s</ol>
<h2>卡片预览（SVG 文本图）</h2>
%(svg)s
<p class="note">本页为自包含 HTML（内嵌样式与 SVG，均为文本）；由 document JSON
确定性渲染，与 proposal.md 同源。主交付请以可编辑的 proposal.md 为准。</p>
</body>
</html>
""" % {"title": esc(meta["title"]), "discipline": esc(meta["discipline"]),
       "degree": esc(meta["degree"]), "author": esc(meta["author"]),
       "advisor": esc(meta["advisor"]), "version": esc(meta["version"]),
       "date": esc(meta["date"]), "li": li, "svg": svg_text}


def main(argv):
    if len(argv) != 4 or argv[1] in ("-h", "--help"):
        sys.exit("usage: render_preview.py DOC_JSON OUT_SVG OUT_HTML")
    with open(argv[1], encoding="utf-8") as f:
        doc = json.load(f)
    errors = validate_document(doc)
    if errors:
        print("schema 校验失败，拒绝渲染（共 %d 处）:" % len(errors), file=sys.stderr)
        for e in errors:
            print("  - %s" % e, file=sys.stderr)
        sys.exit(2)
    svg_text = render_svg(doc)
    html_text = render_html(doc, svg_text)
    with open(argv[2], "w", encoding="utf-8", newline="\n") as f:
        f.write(svg_text)
    with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
        f.write(html_text)
    print(json.dumps({"svg": argv[2], "svg_bytes": len(svg_text.encode("utf-8")),
                      "html": argv[3],
                      "html_bytes": len(html_text.encode("utf-8"))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
