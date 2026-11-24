#!/usr/bin/env python3
"""page_maps.py -- evidence-atlas-forge page-map previews.

For every finding, renders one SVG "page map": the full text of the
claimed page laid out line by line, with the lines containing the
finding's quote highlighted. Pure-stdlib SVG, no external renderer.
Also writes an index.html linking all maps.

A quote that cannot be located on its page yields a map with
highlight=false (recorded in the index and manifest), never a silently
unhighlighted "success".
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

SEV_COLOR = {"critical": "#b00020", "major": "#d35400",
             "minor": "#b7950b", "advisory": "#1e8449"}


def collapse(s):
    return re.sub(r"\s+", " ", s or "").strip()


def find_quote_lines(lines, quote):
    """Return indices of lines covered by the (possibly wrapped) quote."""
    q = collapse(quote)
    if not q:
        return []
    joined = "\n".join(lines)
    flat = collapse(joined)
    if q not in flat:
        return []
    # progressive line-span search
    n = len(lines)
    for span in range(1, min(n, 40) + 1):
        for i in range(0, n - span + 1):
            if q in collapse(" ".join(lines[i:i + span])):
                return list(range(i, i + span))
    # fallback: lines containing any 25-char fragment of the quote
    frag = q[:25]
    return [i for i, ln in enumerate(lines) if frag in collapse(ln)]


def svg_page(page_no, lines, hit_lines, header, sev):
    width = 860
    line_h = 17
    top = 58
    height = top + line_h * (len(lines) + 1) + 16
    color = SEV_COLOR.get(sev, "#555")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" font-family="monospace" font-size="12">',
        f'<rect x="0" y="0" width="{width}" height="30" fill="{color}"/>',
        f'<text x="12" y="20" fill="#fff" font-weight="bold">'
        f'{html.escape(header)}</text>',
        f'<text x="12" y="42" fill="#666">page {page_no} | '
        f'{"quote highlighted" if hit_lines else "NO HIGHLIGHT (quote not located)"}'
        f'</text>',
    ]
    hits = set(hit_lines)
    for i, ln in enumerate(lines):
        y = top + line_h * i
        if i in hits:
            parts.append(f'<rect x="4" y="{y - 12}" width="{width - 8}" '
                         f'height="{line_h}" fill="#fff3a0"/>')
        parts.append(f'<text x="10" y="{y}" fill="#222">'
                     f'{html.escape(ln[:130])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    result = json.load(open(args.result, encoding="utf-8"))
    pages = {}
    for line in open(args.pages, encoding="utf-8"):
        if line.strip():
            pg = json.loads(line)
            pages[pg["page"]] = pg["text"]

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    index_rows, manifest = [], []
    for f in result.get("findings", []):
        loc = f.get("location", {})
        page = loc.get("page")
        fid = f.get("id", "F-??")
        text = pages.get(page)
        if text is None:
            manifest.append({"id": fid, "page": page, "highlight": False,
                             "svg": None, "note": "page out of range"})
            continue
        lines = text.splitlines()
        hits = find_quote_lines(lines, loc.get("quote", ""))
        name = f"{fid}_p{page}.svg".replace("/", "_")
        svg = svg_page(page, lines, hits,
                       f"{fid} | {loc.get('locator','')} | "
                       f"{f.get('severity','')}",
                       f.get("severity", "advisory"))
        (outdir / name).write_text(svg, encoding="utf-8")
        manifest.append({"id": fid, "page": page,
                         "highlight": bool(hits), "svg": name})
        index_rows.append(
            f'<tr><td><a href="{html.escape(name)}">{html.escape(fid)}'
            f'</a></td><td>{page}</td>'
            f'<td>{"yes" if hits else "<b>NO</b>"}</td></tr>')

    index = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
             "<title>page maps</title></head><body><h2>Page maps - "
             f"{html.escape(str(result.get('case_id','?')))}</h2>"
             "<table border='1' cellpadding='4'>"
             "<tr><th>finding</th><th>page</th><th>highlighted</th></tr>"
             + "".join(index_rows) + "</table></body></html>")
    (outdir / "index.html").write_text(index, encoding="utf-8")
    with open(outdir / "maps_manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    n_no = sum(1 for m in manifest if not m.get("highlight"))
    print(json.dumps({"maps": len(manifest), "unhighlighted": n_no},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
