#!/usr/bin/env python3
"""emit_formats.py — 将 mindmap.json 确定性导出为多种可编辑格式。

用法:
    python3 scripts/emit_formats.py --map mindmap.json --outdir OUT

输出（同名输入、字节级确定性：相同输入必然产生字节一致的输出）:
    mindmap.mm    FreeMind XML（主交付格式，可导入 FreeMind / Freeplane / XMind）
    mindmap.opml  OPML 2.0 大纲
    mindmap.md    缩进 Markdown 大纲
    mindmap.mmd   Mermaid mindmap 语法
    mindmap.html  自包含 Markmap 页面（含离线可读的静态嵌套列表回退）

仅使用 Python 标准库。子节点顺序按 id 字典序稳定排序，不依赖输入顺序之外的任何因素。
"""
import argparse
import html as _html
import json
import os
import sys
from xml.sax.saxutils import escape as _xml_escape

MM_VERSION = "1.0.1"
MARKMAP_CDN = "https://cdn.jsdelivr.net/npm/markmap-autoloader@0.18"


def xml_attr(s):
    """XML 属性转义（含双引号、单引号、&、<、>）。"""
    return _xml_escape(str(s), {'"': "&quot;", "'": "&apos;"})


def xml_text(s):
    """XML 文本节点转义。"""
    return _xml_escape(str(s))


def write_text(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def load_map(path):
    """载入并校验 mindmap.json；返回 (root, nodes, children, relations)。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "root" not in data or "nodes" not in data:
        sys.stderr.write("错误：mindmap.json 必须包含 root 与 nodes 字段。\n")
        sys.exit(2)
    nodes = {}
    for n in data["nodes"]:
        for key in ("id", "label"):
            if key not in n:
                sys.stderr.write("错误：节点缺少必填字段 %s：%r\n" % (key, n))
                sys.exit(2)
        if n["id"] in nodes:
            sys.stderr.write("错误：节点 id 重复：%s\n" % n["id"])
            sys.exit(2)
        nodes[n["id"]] = n
    root = data["root"]
    if root not in nodes:
        sys.stderr.write("错误：root 指向不存在的节点 id：%s\n" % root)
        sys.exit(2)
    children = {nid: [] for nid in nodes}
    for n in data["nodes"]:
        p = n.get("parent")
        if p is None:
            if n["id"] != root:
                sys.stderr.write("错误：非根节点 parent 为 null：%s\n" % n["id"])
                sys.exit(2)
            continue
        if p not in nodes:
            sys.stderr.write("错误：节点 %s 的 parent 不存在：%s\n" % (n["id"], p))
            sys.exit(2)
        children[p].append(n["id"])
    for k in children:
        children[k].sort()  # 稳定子节点顺序：按 id 字典序
    relations = sorted(
        data.get("relations", []),
        key=lambda r: (r["from"], r["to"], r.get("type", "")),
    )
    for r in relations:
        for ep in ("from", "to"):
            if r.get(ep) not in nodes:
                sys.stderr.write("错误：关系端点不存在：%r\n" % r)
                sys.exit(2)
    return root, nodes, children, relations


# ---------------------------------------------------------------- FreeMind

def emit_mm(root, nodes, children, relations, path):
    rel_from = {}
    for r in relations:
        rel_from.setdefault(r["from"], []).append(r)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<map version="%s">' % MM_VERSION]

    def rec(nid, depth):
        n = nodes[nid]
        ind = "  " * (depth + 1)
        attrs = 'TEXT="%s" ID="%s"' % (xml_attr(n["label"]), xml_attr(nid))
        kids = children.get(nid, [])
        note = n.get("note")
        rels = rel_from.get(nid, [])
        if not kids and note is None and not rels:
            lines.append("%s<node %s/>" % (ind, attrs))
            return
        lines.append("%s<node %s>" % (ind, attrs))
        if note is not None:
            lines.append(
                '%s  <rich_content TYPE="NOTE"><html><head/><body><p>%s</p>'
                "</body></html></rich_content>" % (ind, xml_text(note))
            )
        for r in rels:
            lines.append('%s  <arrowlink DESTINATION="%s"/>'
                         % (ind, xml_attr(r["to"])))
        for c in kids:
            rec(c, depth + 1)
        lines.append("%s</node>" % ind)

    rec(root, 0)
    lines.append("</map>")
    write_text(path, "\n".join(lines) + "\n")


# ---------------------------------------------------------------- OPML

def emit_opml(root, nodes, children, path):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<opml version="2.0">',
             "  <head>",
             "    <title>%s</title>" % xml_text(nodes[root]["label"]),
             "  </head>",
             "  <body>"]

    def rec(nid, depth):
        n = nodes[nid]
        ind = "  " * (depth + 2)
        attrs = 'text="%s"' % xml_attr(n["label"])
        if n.get("kind"):
            attrs += ' type="%s"' % xml_attr(n["kind"])
        if n.get("note") is not None:
            attrs += ' _note="%s"' % xml_attr(n["note"])
        kids = children.get(nid, [])
        if not kids:
            lines.append("%s<outline %s/>" % (ind, attrs))
            return
        lines.append("%s<outline %s>" % (ind, attrs))
        for c in kids:
            rec(c, depth + 1)
        lines.append("%s</outline>" % ind)

    rec(root, 0)
    lines.append("  </body>")
    lines.append("</opml>")
    write_text(path, "\n".join(lines) + "\n")


# ---------------------------------------------------------------- Markdown

def build_md_lines(root, nodes, children, relations):
    lines = ["# %s" % nodes[root]["label"], ""]
    if nodes[root].get("note"):
        lines.append("> 备注：%s" % nodes[root]["note"])
        lines.append("")

    def rec(nid, depth):
        n = nodes[nid]
        tag = "（%s）" % n["kind"] if n.get("kind") else ""
        lines.append("%s- %s%s" % ("  " * depth, n["label"], tag))
        if n.get("note"):
            lines.append("%s- 备注：%s" % ("  " * (depth + 1), n["note"]))
        for c in children.get(nid, []):
            rec(c, depth + 1)

    for c in children.get(root, []):
        rec(c, 0)
    if relations:
        lines.append("")
        lines.append("## 关系")
        for r in relations:
            seg = "- %s → %s（%s）" % (
                nodes[r["from"]]["label"], nodes[r["to"]]["label"],
                r.get("type", ""))
            if r.get("note"):
                seg += "：%s" % r["note"]
            lines.append(seg)
    return lines


def emit_md(root, nodes, children, relations, path):
    write_text(path, "\n".join(build_md_lines(root, nodes, children, relations)) + "\n")


# ---------------------------------------------------------------- Mermaid

def sanitize_mmd(s):
    """Mermaid mindmap 裸标签不允许圆括号/方括号，替换为全角等价字符。"""
    return (str(s).replace("(", "（").replace(")", "）")
                  .replace("[", "［").replace("]", "］"))


def emit_mmd(root, nodes, children, path):
    lines = ["mindmap",
             "  root((%s))" % sanitize_mmd(nodes[root]["label"])]

    def rec(nid, depth):
        lines.append("%s%s" % ("    " * (depth + 1),
                               sanitize_mmd(nodes[nid]["label"])))
        for c in children.get(nid, []):
            rec(c, depth + 1)

    for c in children.get(root, []):
        rec(c, 0)
    write_text(path, "\n".join(lines) + "\n")


# ---------------------------------------------------------------- HTML (Markmap)

def emit_html(root, nodes, children, relations, path, source_data):
    def rec_ul(nid):
        n = nodes[nid]
        parts = ['<li><span class="label">%s</span>' % _html.escape(str(n["label"]))]
        if n.get("kind"):
            parts.append(' <span class="kind">（%s）</span>'
                         % _html.escape(str(n["kind"])))
        if n.get("note"):
            parts.append('<div class="note">备注：%s</div>'
                         % _html.escape(str(n["note"])))
        kids = children.get(nid, [])
        if kids:
            parts.append("<ul>")
            for c in kids:
                parts.append(rec_ul(c))
            parts.append("</ul>")
        parts.append("</li>")
        return "".join(parts)

    static_ul = '<ul class="tree">%s</ul>' % rec_ul(root)
    map_json = json.dumps(source_data, ensure_ascii=False, indent=2,
                          sort_keys=True).replace("</", "<\\/")
    md_text = "\n".join(build_md_lines(root, nodes, children, relations))
    title = _html.escape(str(nodes[root]["label"]))

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>%(title)s — Markmap</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 1em 2em; }
  .markmap { width: 100%%; height: 60vh; border: 1px solid #ccc; margin-bottom: 1em; }
  .markmap svg { width: 100%%; height: 100%%; }
  .kind { color: #666; font-size: 0.9em; }
  .note { color: #555; font-size: 0.85em; margin-left: 0.5em; }
  #offline-note { color: #a00; }
</style>
</head>
<body>
<h1>%(title)s</h1>
<p id="offline-note"></p>
<div class="markmap">
<script type="text/template">
%(md)s
</script>
</div>
<h2>静态大纲（离线可读回退）</h2>
%(static)s
<script type="application/json" id="mindmap-json">
%(json)s
</script>
<script>
/* 在线时自 CDN 加载 markmap-autoloader 渲染交互图；
   加载失败（离线/网络受限）时保留下方静态嵌套列表，页面内容完整可读。 */
window.addEventListener('load', function () {
  var note = document.getElementById('offline-note');
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    note.textContent = '（当前离线：以静态大纲呈现。）';
    return;
  }
  var s = document.createElement('script');
  s.src = '%(cdn)s';
  s.onerror = function () {
    note.textContent = '（Markmap CDN 不可用：以静态大纲呈现。）';
  };
  document.head.appendChild(s);
});
</script>
</body>
</html>
""" % {"title": title, "md": md_text, "static": static_ul,
       "json": map_json, "cdn": MARKMAP_CDN}
    write_text(path, page)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="确定性多格式思维导图导出器")
    ap.add_argument("--map", required=True, help="输入 mindmap.json 路径")
    ap.add_argument("--outdir", required=True, help="输出目录")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    with open(args.map, encoding="utf-8") as f:
        source_data = json.load(f)
    root, nodes, children, relations = load_map(args.map)

    emit_mm(root, nodes, children, relations,
            os.path.join(args.outdir, "mindmap.mm"))
    emit_opml(root, nodes, children,
              os.path.join(args.outdir, "mindmap.opml"))
    emit_md(root, nodes, children, relations,
            os.path.join(args.outdir, "mindmap.md"))
    emit_mmd(root, nodes, children,
             os.path.join(args.outdir, "mindmap.mmd"))
    emit_html(root, nodes, children, relations,
              os.path.join(args.outdir, "mindmap.html"), source_data)
    sys.stdout.write("已导出 5 种格式至 %s\n" % args.outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
