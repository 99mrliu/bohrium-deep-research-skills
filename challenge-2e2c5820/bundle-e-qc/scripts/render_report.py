#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_report.py — stdlib-only：把审查报告 Markdown 渲染成独立 HTML（内联 CSS，无外部依赖）。

用法:
    python3 render_report.py <review.md> <result.json> <out.html>

支持 Markdown 子集：标题（h1-h4，自动生成目录）、表格、无序/有序列表、引用块、
**加粗**、`行内代码`。另自动附加：
- 状态徽章（按 result.json 的 status 着色：complete 绿 / partial 橙 / failed 红）；
- 「证据锚点索引（自动提取）」表：统计 [L12]、（第X节） 类定位符的出现次数与首次行号；
- 页脚：case_id + 生成时间戳；输入含「合成示例」标记时透传横幅。

运行时尚应按平台能力另用 office-renderer 产出 PDF/PNG 预览（见 SKILL.md 步骤 6）。
"""
import argparse
import datetime
import html
import json
import os
import re
import sys

ANCHOR_RE = re.compile(r"\[L\d+\]|（第[^）]{1,15}节）")
STATUS_BADGE = {
    "complete": ("审查完成", "#1a7f37"),
    "partial": ("部分完成（honest partial）", "#9a6700"),
    "failed": ("未能完成", "#cf222e"),
}
CSS = """
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;
 background:#f6f8fa;color:#1f2328;line-height:1.65}
.wrap{max-width:920px;margin:24px auto;background:#fff;padding:32px 40px;
 border:1px solid #d0d7de;border-radius:8px}
h1{border-bottom:2px solid #d0d7de;padding-bottom:.3em}
h2{border-bottom:1px solid #d8dee4;padding-bottom:.2em;margin-top:1.6em}
table{border-collapse:collapse;margin:12px 0;width:100%}
th,td{border:1px solid #d0d7de;padding:6px 10px;text-align:left;font-size:14px}
th{background:#f6f8fa}
code{background:#eff1f3;padding:1px 5px;border-radius:4px;font-size:90%}
blockquote{border-left:4px solid #d0d7de;margin:12px 0;padding:4px 14px;color:#57606a}
.badge{display:inline-block;color:#fff;font-weight:600;padding:4px 14px;
 border-radius:14px;font-size:14px}
.banner{background:#fff8c5;border:1px solid #d4a72c;color:#7d4e00;padding:8px 14px;
 border-radius:6px;font-weight:600;margin:12px 0}
.toc{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:12px 18px;
 margin:16px 0}
.toc ul{margin:6px 0}.toc .l3{margin-left:18px;list-style:circle}
footer{margin-top:32px;padding-top:12px;border-top:1px solid #d8dee4;color:#57606a;
 font-size:13px}
"""


def inline(text):
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def render_markdown(md):
    """返回 (body_html, toc[(level,text,anchor)], stats)。"""
    lines = md.splitlines()
    body, toc = [], []
    stats = {"headings": 0, "tables": 0}
    i, sec = 0, 0
    while i < len(lines):
        line = lines[i]
        hm = re.match(r"^(#{1,4})\s+(.*)$", line)
        if hm:
            level, text = len(hm.group(1)), hm.group(2).strip()
            sec += 1
            anchor = "sec-%d" % sec
            body.append('<h%d id="%s">%s</h%d>' % (level, anchor, inline(text), level))
            if level in (2, 3):
                toc.append((level, text, anchor))
            stats["headings"] += 1
            i += 1
            continue
        if line.strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            rows = []
            for bl in block:
                cells = [c.strip() for c in bl.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    continue
                rows.append(cells)
            if rows:
                parts = []
                for r, cells in enumerate(rows):
                    tag = "th" if r == 0 else "td"
                    parts.append("<tr>" + "".join("<%s>%s</%s>" % (tag, inline(c), tag)
                                                  for c in cells) + "</tr>")
                body.append("<table>" + "".join(parts) + "</table>")
                stats["tables"] += 1
            continue
        if re.match(r"^\s*[-*]\s", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s*", "", lines[i]))
                i += 1
            body.append("<ul>" + "".join("<li>%s</li>" % inline(x) for x in items) + "</ul>")
            continue
        if re.match(r"^\s*\d+[.、)]", line):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+[.、)]", lines[i]):
                items.append(re.sub(r"^\s*\d+[.、)]\s*", "", lines[i]))
                i += 1
            body.append("<ol>" + "".join("<li>%s</li>" % inline(x) for x in items) + "</ol>")
            continue
        if line.strip().startswith(">"):
            items = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                items.append(lines[i].strip().lstrip(">").strip())
                i += 1
            body.append("<blockquote>" + "<br>".join(inline(x) for x in items)
                        + "</blockquote>")
            continue
        if not line.strip():
            i += 1
            continue
        para = [line]
        i += 1
        while (i < len(lines) and lines[i].strip()
               and not re.match(r"^(#{1,4}\s|\s*[-*]\s|\s*\d+[.、)]|>)", lines[i])
               and not lines[i].strip().startswith("|")):
            para.append(lines[i])
            i += 1
        body.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
    return "\n".join(body), toc, stats


def extract_anchors(md):
    found = {}
    for ln, line in enumerate(md.splitlines(), 1):
        for a in ANCHOR_RE.findall(line):
            d = found.setdefault(a, {"count": 0, "first_line": ln})
            d["count"] += 1
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description="Markdown 审查报告 → 独立 HTML（stdlib-only）")
    ap.add_argument("review_md")
    ap.add_argument("result_json")
    ap.add_argument("out_html")
    args = ap.parse_args(argv)

    for p in (args.review_md, args.result_json):
        if not os.path.isfile(p):
            print("错误：文件不存在: %s" % p, file=sys.stderr)
            return 2
    with open(args.review_md, "r", encoding="utf-8") as f:
        md = f.read()
    with open(args.result_json, "r", encoding="utf-8") as f:
        result = json.load(f)

    body, toc, stats = render_markdown(md)
    anchors = extract_anchors(md)

    status = result.get("status", "partial")
    label, color = STATUS_BADGE.get(status, ("未知状态", "#57606a"))
    case_id = result.get("case_id", "UNKNOWN")
    verdict = result.get("verdict_summary") or ""

    toc_html = ['<nav class="toc"><strong>目录</strong><ul>']
    for level, text, anchor in toc:
        cls = ' class="l3"' if level == 3 else ""
        toc_html.append('<li%s><a href="#%s">%s</a></li>' % (cls, anchor, inline(text)))
    toc_html.append("</ul></nav>")

    banner = ('<div class="banner">合成示例，非正式案例数据</div>'
              if "合成示例" in md else "")

    anchor_rows = "".join(
        "<tr><td><code>%s</code></td><td>%d</td><td>第 %d 行</td></tr>"
        % (html.escape(a), d["count"], d["first_line"])
        for a, d in sorted(anchors.items()))
    anchor_sec = ('<h2 id="anchors-auto">证据锚点索引（自动提取）</h2>'
                  '<table><tr><th>锚点</th><th>出现次数</th><th>首次行号</th></tr>%s</table>'
                  % anchor_rows) if anchors else ""

    now = datetime.datetime.now().isoformat(timespec="seconds")
    doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>实验方案可行性审查报告 — %s</title>
<style>%s</style></head>
<body><div class="wrap">
%s
<p><span class="badge" style="background:%s">%s</span></p>
%s
%s
%s
%s
<footer>case_id：<code>%s</code> ｜ 生成时间：%s ｜ render_report.py（stdlib-only，无外部依赖）</footer>
</div></body></html>
""" % (html.escape(str(case_id)), CSS, banner, color, html.escape(label),
       "<p><strong>结论摘要：</strong>%s</p>" % inline(str(verdict)) if verdict else "",
       "\n".join(toc_html), body, anchor_sec,
       html.escape(str(case_id)), html.escape(now))

    out_dir = os.path.dirname(os.path.abspath(args.out_html))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    print("已写出: %s（标题 %d 个，表格 %d 张，锚点 %d 个，状态徽章 %s，目录条目 %d）"
          % (args.out_html, stats["headings"], stats["tables"], len(anchors),
             status, len(toc)))
    print("提示：运行时请再按平台能力用 office-renderer 产出 PDF/PNG 预览。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
