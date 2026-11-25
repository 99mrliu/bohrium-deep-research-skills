#!/usr/bin/env python3
"""render_review.py — 生成自包含 review.html（单文件，无外部资源）。

布局：左栏页面列表 + 内联 SVG（直接内嵌 overlays/page-N.svg 的同一字节，
不用 <img> 外链）；右栏按阅读序（order 字段）的块文本，每块前缀锚点徽章
[p1.b3]。hover 徽章高亮对应 SVG 矩形（描边加粗），点击徽章平滑滚动到该矩形；
全部交互为纯内联 JS。所有文本严格 HTML 转义（& < > " '）。
文件头注释注明生成时间（UTC）与输入文件 sha256。

overlays/page-N.svg 缺失时按 svg_common 就地重建并记 warning（退出码 2），
保证 review.html 始终可产出。
退出码：0=成功，2=部分，3=失败。
"""

import argparse
import hashlib
import html
import json
import os
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_common  # noqa: E402

EXIT_OK, EXIT_PARTIAL, EXIT_FAIL = 0, 2, 3


def esc(s):
    """HTML 转义，quote=True 覆盖双引号与单引号。"""
    return html.escape(str(s), quote=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


CSS = """
* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,"Helvetica Neue",Arial,sans-serif; color:#222; }
header { padding:10px 16px; background:#f5f5f5; border-bottom:1px solid #ddd;
         font-size:13px; }
header code { background:#eee; padding:1px 4px; border-radius:3px; }
#wrap { display:flex; height:calc(100vh - 46px); }
#left { width:52%; overflow:auto; padding:12px; border-right:1px solid #ddd; }
#right { width:48%; overflow:auto; padding:12px; }
.page { margin-bottom:24px; }
.page h2 { font-size:14px; margin:0 0 6px; color:#555; }
.page svg { max-width:100%; height:auto; border:1px solid #ccc; }
.blk { margin:0 0 12px; padding:8px 10px; border:1px solid #e3e3e3;
       border-radius:6px; }
.blk.hi { outline:2px solid #d62728; }
.badge { font-family:monospace; font-size:12px; cursor:pointer;
         border:1px solid #999; border-radius:4px; background:#fff;
         padding:1px 6px; margin-right:6px; }
.badge:hover { background:#ffe9e9; border-color:#d62728; }
.kind { font-size:11px; color:#fff; border-radius:3px; padding:1px 5px; }
.meta { font-size:11px; color:#888; margin-top:4px; }
p.txt { margin:6px 0 0; font-size:13px; line-height:1.5; white-space:pre-wrap;
        word-break:break-word; }
"""

JS = """
function rectsOf(a){var g=document.getElementById('blk-'+a);
  return g?g.querySelectorAll('rect'):[];}
function setHi(a,on){var rs=rectsOf(a);
  rs.forEach(function(r){r.setAttribute('stroke-width',on?'3':'1.2');});
  var d=document.getElementById('card-'+a);
  if(d){d.classList.toggle('hi',on);}}
document.querySelectorAll('.badge').forEach(function(b){
  var a=b.getAttribute('data-anchor');
  b.addEventListener('mouseenter',function(){setHi(a,true);});
  b.addEventListener('mouseleave',function(){setHi(a,false);});
  b.addEventListener('click',function(){
    var g=document.getElementById('blk-'+a);
    if(g){g.scrollIntoView({behavior:'smooth',block:'center'});}
    setHi(a,true);setTimeout(function(){setHi(a,false);},1500);});
});
document.querySelectorAll('#left g[id^="blk-"]').forEach(function(g){
  var a=g.id.slice(4);
  g.addEventListener('mouseenter',function(){setHi(a,true);});
  g.addEventListener('mouseleave',function(){setHi(a,false);});
  g.addEventListener('click',function(){
    var d=document.getElementById('card-'+a);
    if(d){d.scrollIntoView({behavior:'smooth',block:'center'});}});
});
"""


class _SanityParser(HTMLParser):
    """仅用于解析自检：能跑完全文即视为无异常。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = 0

    def handle_starttag(self, tag, attrs):
        self.tags += 1


def load_blocks(path):
    blocks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                blocks.append(json.loads(line))
    return blocks


def main():
    ap = argparse.ArgumentParser(description="生成自包含 review.html")
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--page-meta", required=True)
    ap.add_argument("--out-dir", required=True, help="产物根目录（含 overlays/）")
    ap.add_argument("--out", default=None, help="review.html 路径，默认 <out-dir>/review.html")
    args = ap.parse_args()

    out_html = args.out or os.path.join(args.out_dir, "review.html")
    report = {"script": "render_review.py", "warnings": [], "status": "failed",
              "anchors": 0, "pages": 0, "output": out_html}

    try:
        blocks = load_blocks(args.blocks)
        with open(args.page_meta, encoding="utf-8") as f:
            pages = json.load(f)["pages"]
    except Exception as e:  # noqa: BLE001
        report["warnings"].append(f"输入读取失败: {type(e).__name__}: {e}"[:300])
        return finish(report, args.out_dir, EXIT_FAIL)

    blocks_by_page = {}
    for b in blocks:
        blocks_by_page.setdefault(int(b["page"]), []).append(b)
    blocks_sorted = sorted(blocks, key=lambda b: b.get("order", 0))

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    in_hashes = {"blocks.jsonl": sha256_file(args.blocks),
                 "page_meta.json": sha256_file(args.page_meta)}

    parts = ["<!DOCTYPE html>", '<html lang="zh">', "<head>",
             '<meta charset="utf-8">',
             "<title>Anchored Review — 逐块锚点复核</title>",
             f"<style>{CSS}</style>", "</head>", "<body>",
             f"<!-- generated-at: {generated_at} | "
             + " | ".join(f"sha256({k})={v}" for k, v in in_hashes.items()) + " -->",
             "<header><strong>Anchored Review</strong> · "
             f"生成时间 <code>{esc(generated_at)}</code> · "
             f"输入哈希 " + " ".join(
                 f"<code>{esc(k)}:{esc(v[:12])}…</code>" for k, v in in_hashes.items())
             + " · 用法：hover/点击右侧徽章 ↔ 左侧矩形</header>",
             '<div id="wrap"><div id="left">']

    overlays_dir = os.path.join(args.out_dir, "overlays")
    for p in pages:
        pno = int(p["page"])
        svg_path = os.path.join(overlays_dir, f"page-{pno}.svg")
        if os.path.isfile(svg_path):
            with open(svg_path, encoding="utf-8") as f:
                svg = f.read()
        else:
            svg = svg_common.build_page_svg(p["width"], p["height"],
                                            blocks_by_page.get(pno, []))
            report["warnings"].append(
                f"overlays/page-{pno}.svg 缺失，已按 svg_common 就地重建")
        parts.append(f'<section class="page" id="page-{pno}">'
                     f"<h2>Page {pno} — {esc(p['width'])} × {esc(p['height'])} pt"
                     f"（{len(blocks_by_page.get(pno, []))} 块）</h2>")
        parts.append(svg)
        parts.append("</section>")
    parts.append('</div><div id="right">')

    for b in blocks_sorted:
        anchor = str(b["id"])
        kind = str(b.get("kind", "body"))
        color = svg_common.KIND_COLORS.get(kind, svg_common.DEFAULT_COLOR)
        bbox = ", ".join(f"{float(v):.1f}" for v in b["bbox"])
        parts.append(
            f'<div class="blk" id="card-{esc(anchor)}" data-anchor="{esc(anchor)}">'
            f'<button class="badge" data-anchor="{esc(anchor)}">[{esc(anchor)}]</button>'
            f'<span class="kind" style="background:{color}">{esc(kind)}</span>'
            f'<p class="txt">{esc(b.get("text", ""))}</p>'
            f'<div class="meta">page {int(b["page"])} · column {int(b.get("column", 1))} '
            f'· order {int(b.get("order", 0))} · bbox [{esc(bbox)}] pt（y 向下）</div>'
            f"</div>"
        )
    parts.append("</div></div>")
    parts.append(f"<script>{JS}</script>")
    parts.append("</body></html>")
    doc = "\n".join(parts) + "\n"

    parser = _SanityParser()
    try:
        parser.feed(doc)
        parser.close()
    except Exception as e:  # noqa: BLE001
        report["warnings"].append(f"HTML 解析自检失败: {type(e).__name__}: {e}"[:300])
        return finish(report, args.out_dir, EXIT_FAIL)

    os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)

    report.update({"anchors": len(blocks_sorted), "pages": len(pages),
                   "html_tags": parser.tags,
                   "status": "partial" if report["warnings"] else "success"})
    return finish(report, args.out_dir,
                  EXIT_PARTIAL if report["warnings"] else EXIT_OK)


def finish(report, out_dir, code):
    report["exit_code"] = code
    path = os.path.join(out_dir, "review.report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
