#!/usr/bin/env python3
"""render_preview.py — blocks.jsonl + anchor_map.json -> deliverable.md + preview.html

deliverable.md : every block rendered once, prefixed with an inline anchor
                 tag [[p{page}-b{seq}]]. header/footer blocks are moved into
                 an appendix section (not silently dropped). unresolved blocks
                 are kept and explicitly marked. Blocks whose bbox is null are
                 rendered and tagged "bbox: n/a" (QC will warn, not crash).

preview.html   : one fully self-contained file: inline CSS only, no external
                 URLs, no <script>, no webfonts. Sidebar lists every page with
                 anchor links; each block in the main flow carries
                 data-anchor="p{page}-b{seq}" and title="page/bbox/kind".
                 header/footer dimmed, unresolved red-outlined, equations
                 monospace, captions italic. Deterministic (no timestamps).

Python 3 stdlib only.
"""
import argparse
import html
import json
import os
import sys

KIND_LABEL = {
    "heading": "heading", "body": "body", "caption": "caption",
    "equation": "equation", "reference": "reference",
    "header": "header", "footer": "footer", "unresolved": "unresolved",
}
APPENDIX_KINDS = ("header", "footer")


def load_anchor_index(path):
    with open(path, encoding="utf-8") as f:
        am = json.load(f)
    if not am.get("schema_valid", False):
        sys.stderr.write("error: anchor_map reports invalid schema; fix "
                         "blocks first\n")
        sys.exit(3)
    idx = {}
    for e in am["anchors"]:
        idx[e["block_id"]] = e
    return am, idx


def bbox_str(bbox):
    if bbox is None:
        return "n/a"
    return "[" + ", ".join("%.1f" % float(v) for v in bbox) + "]"


def block_text_md(b):
    t = b.get("text")
    if t is None:
        reason = b.get("reason") or "no reason given"
        return "*[UNRESOLVED — text unavailable; reason: %s]*" % reason
    return t


def render_md(blocks, idx):
    """Return deliverable.md text. Every block appears exactly once with its
    [[anchor]] tag; header/footer go to the appendix."""
    main, appendix = [], []
    for b in blocks:
        e = idx[b["id"]]
        (appendix if b["kind"] in APPENDIX_KINDS else main).append((b, e))
    lines = []
    lines.append("# Deliverable (rendered reading view)")
    lines.append("")
    lines.append("> Each block carries an inline anchor tag `[[p{page}-b{seq}]]` "
                 "mapping back to page/column/bbox in the source PDF. "
                 "Header/footer blocks are relocated to the appendix below; "
                 "nothing is dropped.")
    lines.append("")
    cur_page = None
    for b, e in main:
        if e["page"] != cur_page:
            cur_page = e["page"]
            lines.append("")
            lines.append("## Page %d" % cur_page)
            lines.append("")
        tag = "[[%s]]" % e["anchor"]
        meta = "kind=%s, page=%d, col=%d, bbox=%s" % (
            e["kind"], e["page"], e["column"], bbox_str(e["bbox"]))
        body = block_text_md(b)
        if b["kind"] == "heading":
            lines.append("### %s %s" % (tag, body))
        elif b["kind"] == "equation":
            lines.append("%s `%s`" % (tag, body))
        else:
            lines.append("%s %s" % (tag, body))
        lines.append("")
        lines.append("<sub>%s</sub>" % meta)
        lines.append("")
    lines.append("")
    lines.append("## Appendix: running headers and footers")
    lines.append("")
    lines.append("These blocks belong to the page furniture (kind=header|footer). "
                 "They are rendered here, still anchored, rather than dropped.")
    lines.append("")
    for b, e in appendix:
        tag = "[[%s]]" % e["anchor"]
        meta = "kind=%s, page=%d, col=%d, bbox=%s" % (
            e["kind"], e["page"], e["column"], bbox_str(e["bbox"]))
        lines.append("- %s %s — <sub>%s</sub>" % (tag, block_text_md(b), meta))
    lines.append("")
    return "\n".join(lines)


CSS = """
:root{--ink:#1c2733;--dim:#8a94a0;--accent:#2456a6;--warn:#c62828;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Helvetica Neue","Segoe UI",Arial,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:#f6f7f9;display:flex}
nav#sidebar{position:fixed;top:0;left:0;bottom:0;width:210px;overflow-y:auto;background:#101820;color:#dfe6ee;padding:14px 12px;font-size:13px}
nav#sidebar h1{font-size:13px;margin:0 0 10px;letter-spacing:.08em;text-transform:uppercase;color:#9fb0c3}
nav#sidebar ul{list-style:none;margin:0;padding:0}
nav#sidebar li{margin:2px 0}
nav#sidebar a{color:#cfe0f5;text-decoration:none;display:block;padding:3px 8px;border-radius:4px}
nav#sidebar a:hover{background:#1e2c3c}
nav#sidebar .pg{font-weight:700;margin-top:10px;color:#8fd0ff}
main{margin-left:230px;max-width:860px;padding:28px 32px 80px;background:#fff;min-height:100vh;flex:1}
.block{margin:0 0 14px;padding:10px 14px;border-left:3px solid #d8dee6;border-radius:0 6px 6px 0;background:#fff}
.block .anch{display:inline-block;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;color:#fff;background:var(--accent);border-radius:3px;padding:1px 6px;margin-right:8px;vertical-align:middle}
.block .meta{display:block;font-size:11px;color:var(--dim);margin-top:6px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.block.kind-heading{font-size:20px;font-weight:700;border-left-color:var(--accent)}
.block.kind-body{font-size:15px;line-height:1.65}
.block.kind-caption{font-size:13px;font-style:italic;color:#42505e;border-left-color:#7fb2e5}
.block.kind-equation{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#f0f4fa;border-left-color:#5b8dd9;font-size:14px}
.block.kind-reference{font-size:13px;color:#39424e;border-left-color:#b9c4d0}
.block.kind-header,.block.kind-footer{opacity:.45;font-size:12px;color:var(--dim);border-left-color:#c9d2dc;background:#fafbfc}
.block.kind-unresolved{border:1.5px solid var(--warn);border-left:4px solid var(--warn);background:#fff5f5}
.block.kind-unresolved .anch{background:var(--warn)}
.badge-nobbox{display:inline-block;font-size:10px;color:#7a5a00;background:#fff3cd;border:1px solid #e6cf7a;border-radius:3px;padding:0 5px;margin-left:6px}
h2.page-sep{margin:26px 0 12px;font-size:14px;color:#5a6a7a;border-bottom:1px solid #e2e7ee;padding-bottom:6px}
section#appendix h2{margin-top:40px;font-size:16px;color:#5a6a7a;border-top:2px solid #d8dee6;padding-top:16px}
"""


def esc(s):
    return html.escape(s if s is not None else "", quote=True)


def render_html(blocks, idx, anchor_map):
    pages = []
    for e in anchor_map["anchors"]:
        if e["page"] not in pages:
            pages.append(e["page"])

    side = ['<h1>Pages</h1>', '<ul>']
    for p in pages:
        first = next(a for a in anchor_map["anchors"] if a["page"] == p)
        side.append('<li class="pg"><a href="#pg-%d">Page %d</a></li>' % (p, p))
        for e in anchor_map["anchors"]:
            if e["page"] == p:
                side.append('<li><a href="#%s">%s &middot; %s</a></li>'
                            % (esc(e["anchor"]), esc(e["anchor"]),
                               esc(e["kind"])))
    side.append('</ul>')
    sidebar = "\n".join(side)

    def block_html(b, e):
        classes = "block kind-%s" % esc(e["kind"])
        title = "anchor=%s | page=%d col=%d | bbox=%s | kind=%s" % (
            e["anchor"], e["page"], e["column"], bbox_str(e["bbox"]),
            KIND_LABEL.get(e["kind"], e["kind"]))
        t = b.get("text")
        if t is None:
            reason = b.get("reason") or "no reason given"
            body = "<em>[UNRESOLVED &mdash; text unavailable; reason: %s]</em>" \
                % esc(reason)
        else:
            body = esc(t)
        nobbox = ('<span class="badge-nobbox">bbox: n/a</span>'
                  if e["bbox"] is None else "")
        meta = ("page %d &middot; col %d &middot; bbox %s &middot; kind %s"
                % (e["page"], e["column"], esc(bbox_str(e["bbox"])),
                   esc(e["kind"])))
        return ('<div class="%s" id="%s" data-anchor="%s" title="%s">'
                '<span class="anch">%s</span>%s%s'
                '<span class="meta">%s</span></div>'
                % (classes, esc(e["anchor"]), esc(e["anchor"]), esc(title),
                   esc(e["anchor"]), body, nobbox, meta))

    main_parts, appendix_parts = [], []
    cur_page = None
    for b in blocks:
        e = idx[b["id"]]
        if b["kind"] in APPENDIX_KINDS:
            appendix_parts.append(block_html(b, e))
            continue
        if e["page"] != cur_page:
            cur_page = e["page"]
            main_parts.append('<h2 class="page-sep" id="pg-%d">Page %d</h2>'
                              % (cur_page, cur_page))
        main_parts.append(block_html(b, e))

    doc = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Render Proof Preview</title>",
        "<style>%s</style>" % CSS,
        "</head>",
        "<body>",
        '<nav id="sidebar">%s</nav>' % sidebar,
        "<main>",
        "\n".join(main_parts),
        '<section id="appendix">',
        "<h2>Appendix &mdash; running headers &amp; footers</h2>",
        "\n".join(appendix_parts),
        "</section>",
        "</main>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(doc)


def main():
    ap = argparse.ArgumentParser(
        description="Render deliverable.md and self-contained preview.html")
    ap.add_argument("--blocks", required=True, help="path to blocks.jsonl")
    ap.add_argument("--anchor-map", required=True, help="path to anchor_map.json")
    ap.add_argument("--out-md", required=True, help="path for deliverable.md")
    ap.add_argument("--out-html", required=True, help="path for preview.html")
    args = ap.parse_args()

    anchor_map, idx = load_anchor_index(args.anchor_map)
    blocks = []
    with open(args.blocks, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                blocks.append(json.loads(line))
    missing = [b.get("id") for b in blocks if b.get("id") not in idx]
    if missing:
        sys.stderr.write("error: %d block(s) missing from anchor_map: %s\n"
                         % (len(missing), ", ".join(map(str, missing))))
        return 3

    md = render_md(blocks, idx)
    html_doc = render_html(blocks, idx, anchor_map)

    for path, content in ((args.out_md, md), (args.out_html, html_doc)):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    sys.stdout.write("ok: %d blocks -> %s, %s\n"
                     % (len(blocks), args.out_md, args.out_html))
    return 0


if __name__ == "__main__":
    sys.exit(main())
