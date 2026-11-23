#!/usr/bin/env python3
"""render_preview.py -- self-contained HTML preview (+ optional PNG strip).

The HTML preview is always produced: embedded CSS, anchors highlighted,
comparison table styled, print-friendly. When matplotlib is importable, an
additional one-page PNG strip summarizing the card fields and section map is
rendered for quick visual inspection; when it is not, the preview report
states that honestly instead of failing. In the evaluation runtime any
Office/diagram deliverable must also be rendered by the platform renderer;
this script covers the notes-specific preview.
"""
import argparse
import html
import json
import re


def md_to_html(text):
    lines = text.splitlines()
    out, in_ul, in_table = [], False, False
    for line in lines:
        if line.startswith("| ") and line.endswith(" |"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set(cells[0]) <= set("-: "):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join("<%s>%s</%s>" % (tag, inline(c), tag)
                                        for c in cells) + "</tr>")
            continue
        elif in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append("<li>" + inline(line[2:]) + "</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if line.startswith("## "):
                t = line[3:]
                out.append('<h2 id="%s">%s</h2>' % (
                    html.escape(t.lower().replace(" ", "-")), inline(t)))
            elif line.startswith("# "):
                out.append("<h1>%s</h1>" % inline(line[2:]))
            elif line.strip():
                out.append("<p>%s</p>" % inline(line))
    if in_ul:
        out.append("</ul>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def inline(text):
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r'<code class="anchor">\1</code>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(#([^)]+)\)", r'<a href="#\2">\1</a>', text)
    return text


CSS = """
body{font-family:Georgia,'Songti SC',serif;max-width:880px;margin:2em auto;
padding:0 1.2em;line-height:1.65;color:#1a1a1a}
h1{border-bottom:2px solid #333;padding-bottom:.2em}
h2{margin-top:1.6em;border-bottom:1px solid #bbb}
code.anchor{background:#eef4ff;color:#1450a0;padding:0 .3em;border-radius:3px;
font-size:.85em}
table{border-collapse:collapse;margin:1em 0}
th,td{border:1px solid #999;padding:.35em .8em;text-align:left}
th{background:#f0f0f0}
@media print{body{margin:0}}
"""


def png_strip(notes, out_png):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    import matplotlib.pyplot as plt
    cjk_ok = False
    for name in ("PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
                 "Source Han Sans SC", "Microsoft YaHei", "SimHei"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            cjk_ok = True
            break
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.axis("off")
    rows = [(str(k), str(v.get("value", v))[:48] if isinstance(v, dict) else str(v)[:48])
            for k, v in (notes.get("card") or {}).items()]
    y = 0.95
    ax.text(0.02, y, notes.get("title", "notes"), fontsize=14, weight="bold",
            va="top")
    y -= 0.09
    for k, v in rows[:8]:
        ax.text(0.02, y, k, fontsize=10, weight="bold", va="top")
        ax.text(0.28, y, v, fontsize=10, va="top")
        y -= 0.06
    secs = "  |  ".join(s["heading"] for s in notes.get("sections", []))
    ax.text(0.02, 0.12, "sections: " + secs[:110], fontsize=8, va="top",
            color="#444")
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return cjk_ok


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", required=True)
    ap.add_argument("--notes", help="notes.json for the optional PNG strip")
    ap.add_argument("--out-html", required=True)
    ap.add_argument("--out-png")
    args = ap.parse_args()
    with open(args.md, encoding="utf-8") as fh:
        text = fh.read()
    page = ("<!doctype html><meta charset='utf-8'><title>notes preview</title>"
            "<style>%s</style><body>%s</body>" % (CSS, md_to_html(text)))
    with open(args.out_html, "w", encoding="utf-8") as fh:
        fh.write(page)
    report = {"html": args.out_html, "png": None, "png_status": "not requested"}
    if args.out_png:
        if not args.notes:
            report["png_status"] = "skipped: --notes missing"
        else:
            try:
                with open(args.notes, encoding="utf-8") as fh:
                    cjk_ok = png_strip(json.load(fh), args.out_png)
                report["png"] = args.out_png
                report["png_status"] = ("rendered" if cjk_ok else
                                        "rendered; no CJK font found, non-Latin "
                                        "glyphs may be missing -- inspect HTML instead")
            except ImportError:
                report["png_status"] = "unavailable: matplotlib not installed; "
                "HTML preview remains the inspection artifact"
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
