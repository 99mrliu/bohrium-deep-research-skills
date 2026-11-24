#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_bilingual.py — delivery-forge preview renderer (合成示例兼容).

Convert a bilingual master markdown into:
  (a) a self-contained bilingual HTML file (embedded CSS, interleaved
      source/target styling, print-friendly), and
  (b) a real PDF preview + a PNG preview of page 1, rendered with
      matplotlib's PdfPages (deterministic wrapped-line layout, no
      external renderer).

Bilingual master format (documented in references/method.md):
  * Headings: markdown ATX lines  "# Title" / "## Title" ...
  * Paired segments:
        ⟦S0001⟧
        > SRC: English source sentence.
        > TGT: 中文译文。
  * Any other non-empty line is kept as a raw paragraph (SRC-styled).

Core logic uses ONLY the Python standard library. matplotlib (declared
preinstalled in the runtime image) is used ONLY for the PDF/PNG preview.
If matplotlib cannot be imported, previews are honestly skipped: the
reason is written into the QA log, status is "skipped", exit code 0.
We never fake a preview.

Usage:
  python3 render_bilingual.py --master bilingual_master.md \
      --outdir output/ --basename bilingual
Writes:
  <outdir>/<basename>.html          always
  <outdir>/<basename>.pdf           if matplotlib available
  <outdir>/<basename>_page1.png     if matplotlib available
  <outdir>/render_qa_log.json       always
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import textwrap

# ---------------------------------------------------------------- format ---

SEG_ID_RE = re.compile(r"^⟦(S\d{4,})⟧\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def parse_master(text):
    """Parse bilingual master markdown into an ordered block list.

    Returns a list of dicts:
      {"type": "heading", "level": int, "text": str}
      {"type": "segment", "id": str, "src": str, "tgt": str}
      {"type": "raw", "text": str}
    """
    blocks = []
    current = None  # open segment dict
    in_comment = False
    for line in text.splitlines():
        stripped = line.strip()
        # skip HTML comments (possibly multi-line)
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        m = SEG_ID_RE.match(stripped)
        if m:
            if current:
                blocks.append(current)
            current = {"type": "segment", "id": m.group(1), "src": "", "tgt": ""}
            continue
        hm = HEADING_RE.match(line)
        if hm and current is None:
            blocks.append({"type": "heading", "level": len(hm.group(1)),
                           "text": hm.group(2).strip()})
            continue
        if line.strip().startswith(">") and current is not None:
            payload = line.strip()[1:].strip()
            if payload.upper().startswith("SRC:"):
                current["src"] = (current["src"] + " " + payload[4:].strip()).strip()
            elif payload.upper().startswith("TGT:"):
                current["tgt"] = (current["tgt"] + " " + payload[4:].strip()).strip()
            elif payload:
                current["src"] = (current["src"] + " " + payload).strip()
            continue
        if current is not None:
            if line.strip() == "":
                blocks.append(current)
                current = None
            else:  # unmarked continuation inside a segment
                current["src"] = (current["src"] + " " + line.strip()).strip()
            continue
        if line.strip():
            blocks.append({"type": "raw", "text": line.strip()})
    if current:
        blocks.append(current)
    return blocks


# ------------------------------------------------------------------ HTML ---

HTML_CSS = """
:root { --src:#1a3a5c; --tgt:#5c1a1a; --rule:#c9d4e0; }
* { box-sizing: border-box; }
body { font-family: "Helvetica Neue", "PingFang SC", "Noto Sans CJK SC",
       "Microsoft YaHei", sans-serif; max-width: 880px; margin: 2em auto;
       padding: 0 1.2em; color: #222; line-height: 1.6; }
h1,h2,h3,h4 { border-bottom: 2px solid var(--rule); padding-bottom: .2em; }
.seg { border: 1px solid var(--rule); border-radius: 6px; margin: .8em 0;
       padding: .6em .9em; page-break-inside: avoid; }
.seg .sid { font-size: .72em; color: #888; font-family: monospace; }
.src { color: var(--src); margin: .25em 0; }
.tgt { color: var(--tgt); margin: .25em 0; border-top: 1px dashed var(--rule);
       padding-top: .25em; }
.src::before { content: "SRC · "; font-weight: bold; font-size: .8em; }
.tgt::before { content: "TGT · "; font-weight: bold; font-size: .8em; }
.raw { margin: .6em 0; }
@media print { body { margin: 0; max-width: none; } .seg { border: none;
       border-bottom: 1px solid var(--rule); border-radius: 0; } }
"""


def render_html(blocks, title):
    parts = ["<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
             "<title>%s</title><style>%s</style></head><body>" % (html.escape(title), HTML_CSS)]
    for b in blocks:
        if b["type"] == "heading":
            lvl = min(b["level"], 4)
            parts.append("<h%d>%s</h%d>" % (lvl, html.escape(b["text"]), lvl))
        elif b["type"] == "segment":
            parts.append('<div class="seg"><span class="sid">⟦%s⟧</span>' % html.escape(b["id"]))
            if b["src"]:
                parts.append('<p class="src">%s</p>' % html.escape(b["src"]))
            if b["tgt"]:
                parts.append('<p class="tgt">%s</p>' % html.escape(b["tgt"]))
            parts.append("</div>")
        else:
            parts.append('<p class="raw">%s</p>' % html.escape(b["text"]))
    parts.append("</body></html>")
    return "\n".join(parts)


# ------------------------------------------------------------- previews ----

# Common CJK font locations scanned in priority order.
CJK_FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux (Noto Sans CJK / WenQuanYi)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


def discover_cjk_font():
    """Return (path_or_None, warning_or_None). Never raises."""
    for path in CJK_FONT_CANDIDATES:
        if os.path.isfile(path):
            return path, None
    return None, ("no CJK font found in %d candidate paths; falling back to "
                  "matplotlib default font — CJK glyphs may render as boxes "
                  "(tofu) in the PDF/PNG preview" % len(CJK_FONT_CANDIDATES))


def flatten_for_preview(blocks):
    """Turn blocks into a flat list of (style, text) lines for pagination."""
    lines = []
    for b in blocks:
        if b["type"] == "heading":
            lines.append(("heading", b["text"]))
            lines.append(("blank", ""))
        elif b["type"] == "segment":
            # ASCII brackets in the PDF/PNG preview: ⟦ ⟧ (U+27E6/27E7) are
            # missing from many CJK fonts and would render as tofu. The HTML
            # keeps the original ⟦ ⟧ delimiters.
            lines.append(("sid", "[" + b["id"] + "]"))
            if b["src"]:
                lines.append(("src", "SRC · " + b["src"]))
            if b["tgt"]:
                lines.append(("tgt", "TGT · " + b["tgt"]))
            lines.append(("blank", ""))
        else:
            lines.append(("raw", b["text"]))
    return lines


def render_previews(blocks, pdf_path, png_path, qa):
    """Render PDF (all pages) + PNG (page 1) with matplotlib. Never fakes."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.backends.backend_pdf import PdfPages
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except Exception as exc:  # honest degradation, exit stays 0
        qa["previews"] = {"status": "skipped",
                          "reason": "matplotlib import failed: %s: %s"
                                    % (type(exc).__name__, exc)}
        return qa

    font_path, warning = discover_cjk_font()
    qa["font"] = {"requested": "CJK sans", "warning": warning}
    if font_path:
        font_manager.fontManager.addfont(font_path)
        prop = font_manager.FontProperties(fname=font_path)
        qa["font"]["path"] = font_path
        qa["font"]["family"] = prop.get_name()
    else:
        prop = font_manager.FontProperties()
        qa["font"]["path"] = None
        qa["font"]["family"] = prop.get_name()
        qa["font_warning"] = warning

    flat = flatten_for_preview(blocks)
    width_chars = 46          # deterministic wrap width (CJK ~2 cells)
    page_h_lines = 34         # lines per page
    page_size = (8.27, 11.69)  # A4 portrait in inches

    def wrap(style, text):
        if not text:
            return [""]
        w = width_chars if style != "heading" else 34
        return textwrap.wrap(text, width=w, break_long_words=False,
                             replace_whitespace=False) or [""]

    pages, cur = [], []
    for style, text in flat:
        for wl in wrap(style, text):
            cur.append((style, wl))
            if len(cur) >= page_h_lines:
                pages.append(cur)
                cur = []
    if cur:
        pages.append(cur)
    if not pages:
        pages = [[("raw", "(empty master)")]]

    colors = {"heading": "#111111", "sid": "#888888", "src": "#1a3a5c",
              "tgt": "#5c1a1a", "raw": "#222222", "blank": "#222222"}
    sizes = {"heading": 13, "sid": 7, "src": 9, "tgt": 9, "raw": 9, "blank": 9}
    styles = {"heading": "bold"}

    def draw_page(page_lines, page_no, total):
        fig = plt.figure(figsize=page_size)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        n = max(len(page_lines), 1)
        for i, (style, wl) in enumerate(page_lines):
            y = 1.0 - (i + 1) / (n + 2)
            ax.text(0.07, y, wl, fontproperties=prop, fontsize=sizes[style],
                    fontweight=styles.get(style, "normal"),
                    color=colors[style], va="center", ha="left")
        ax.text(0.5, 0.015, "page %d / %d — delivery-forge preview (deterministic layout)"
                % (page_no, total), ha="center", fontsize=7, color="#999999")
        return fig

    total = len(pages)
    with PdfPages(pdf_path) as pdf:
        for i, page in enumerate(pages, 1):
            fig = draw_page(page, i, total)
            pdf.savefig(fig)
            if i == 1:
                fig.savefig(png_path, dpi=110)
            plt.close(fig)

    qa["previews"] = {"status": "generated", "pdf": os.path.basename(pdf_path),
                      "png": os.path.basename(png_path), "pages": total,
                      "layout": {"wrap_chars": width_chars,
                                 "lines_per_page": page_h_lines,
                                 "page_size_in": list(page_size)}}
    return qa


# ------------------------------------------------------------------ main ---

def main(argv=None):
    ap = argparse.ArgumentParser(description="Render bilingual master into HTML + PDF/PNG previews.")
    ap.add_argument("--master", required=True, help="bilingual master markdown path")
    ap.add_argument("--outdir", required=True, help="output directory")
    ap.add_argument("--basename", default="bilingual", help="output basename (default: bilingual)")
    args = ap.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    with open(args.master, "r", encoding="utf-8") as fh:
        text = fh.read()
    blocks = parse_master(text)

    qa = {
        "tool": "render_bilingual.py",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "master": os.path.abspath(args.master),
        "blocks": {
            "headings": sum(1 for b in blocks if b["type"] == "heading"),
            "segments": sum(1 for b in blocks if b["type"] == "segment"),
            "raw": sum(1 for b in blocks if b["type"] == "raw"),
        },
        "segments_missing_tgt": [b["id"] for b in blocks
                                 if b["type"] == "segment" and not b["tgt"]],
    }

    html_path = os.path.join(args.outdir, args.basename + ".html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(blocks, title=os.path.basename(args.master)))
    qa["html"] = {"status": "generated", "file": os.path.basename(html_path),
                  "bytes": os.path.getsize(html_path)}

    pdf_path = os.path.join(args.outdir, args.basename + ".pdf")
    png_path = os.path.join(args.outdir, args.basename + "_page1.png")
    qa = render_previews(blocks, pdf_path, png_path, qa)

    log_path = os.path.join(args.outdir, "render_qa_log.json")
    with open(log_path, "w", encoding="utf-8") as fh:
        json.dump(qa, fh, ensure_ascii=False, indent=2)

    print("render_qa_log: html=%s previews=%s font=%s" % (
        qa["html"]["status"], qa["previews"]["status"],
        qa.get("font", {}).get("family") or "n/a"))
    return 0  # honest degradation: skip never fails the run


if __name__ == "__main__":
    sys.exit(main())
