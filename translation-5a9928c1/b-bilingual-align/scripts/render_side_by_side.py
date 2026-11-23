#!/usr/bin/env python3
"""render_side_by_side.py — render alignment.json as a bilingual
side-by-side HTML table (and optional Markdown table).

Pure standard library. Single <table>, inline <style> only, no external
assets. Every row carries id="<src_id>" so any pair is directly linkable;
each status has its own CSS class:
  aligned            -> plain
  anchor-mismatch    -> amber background
  missing/extra      -> red background
  merged/split       -> blue background
"""
import argparse
import html
import json
import re
import sys

TAG_RE = re.compile(r"^\s*\[\[(P\d{4})\]\]")

CSS = """
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
       margin: 1.5em; color: #222; }
h1 { font-size: 1.3em; }
nav { font-size: 0.85em; margin: 0.8em 0; line-height: 1.9; }
nav a { margin-right: 0.5em; text-decoration: none;
        border: 1px solid #bbb; border-radius: 3px; padding: 0 4px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ccc; padding: 6px 8px; vertical-align: top;
         text-align: left; font-size: 0.92em; }
th { background: #f0f0f0; position: sticky; top: 0; }
td.seg, th.seg { white-space: nowrap; width: 1%; }
td.page { white-space: nowrap; }
.status { font-size: 0.8em; color: #555; }
tr.aligned td { }
tr.anchor-mismatch td { background: #fff3cd; }
tr.missing-translation td, tr.extra-translation td { background: #f8d7da; }
tr.merged-in-target td, tr.split-in-target td { background: #cfe2ff; }
.summary { margin: 0.8em 0; font-size: 0.95em; }
"""

STATUS_CLASSES = ("aligned", "anchor-mismatch", "missing-translation",
                  "extra-translation", "merged-in-target",
                  "split-in-target")


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_targets(path):
    """Return list of {'tag','text'} from .txt blocks or paragraphs.jsonl."""
    if path.endswith(".jsonl"):
        return [{"tag": p.get("seg_id"), "text": p["text"]}
                for p in load_jsonl(path)]
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    blocks = []
    for chunk in re.split(r"\n\s*\n", raw):
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        if not lines:
            continue
        tag = None
        m = TAG_RE.match(lines[0])
        if m:
            tag = m.group(1)
            lines = lines[1:]
        blocks.append({"tag": tag, "text": " ".join(lines)})
    return blocks


def first80(text):
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= 80 else text[:77] + "..."


def md_cell(text):
    return first80(text).replace("|", "\\|")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alignment", required=True)
    ap.add_argument("--src", required=True, help="source paragraphs.jsonl")
    ap.add_argument("--tgt", required=True,
                    help="target .txt blocks or paragraphs.jsonl")
    ap.add_argument("--out", required=True, help="bilingual.html output")
    ap.add_argument("--md", help="optional bilingual.md output")
    args = ap.parse_args()

    with open(args.alignment, "r", encoding="utf-8") as fh:
        alignment = json.load(fh)
    src = {p["seg_id"]: p for p in load_jsonl(args.src)}
    tgts = load_targets(args.tgt)

    pairs = alignment["pairs"]
    cov = alignment.get("coverage", {})

    # ---------- HTML ----------
    counts = {}
    for p in pairs:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    summary = (" | ".join("%s: %d" % (k, counts[k]) for k in sorted(counts))
               + " | coverage %d/%d"
               % (cov.get("aligned", 0), cov.get("source_paragraphs", 0)))

    nav_ids = []
    for p in pairs:
        if p["src_id"]:
            nav_ids.append(p["src_id"])
        else:
            nav_ids.append("extra-%d" % p["tgt_ids"][0])

    rows = []
    for p, anchor_name in zip(pairs, nav_ids):
        status = p["status"]
        cls = status if status in STATUS_CLASSES else "aligned"
        seg = p["src_id"] or "(extra)"
        sp = src.get(p["src_id"]) if p["src_id"] else None
        page = ("%d-%d" % (sp["page_start"], sp["page_end"])) if sp else "-"
        src_text = sp["text"] if sp else "(no source paragraph)"
        tgt_text = "\n".join(tgts[j]["text"] for j in p["tgt_ids"]
                             if 0 <= j < len(tgts)) or "(no translation)"
        rows.append(
            '<tr class="%s" id="%s"><td class="seg">%s</td>'
            '<td class="page">%s</td><td>%s</td><td>%s</td>'
            '<td class="status">%s</td></tr>'
            % (cls, html.escape(anchor_name), html.escape(seg),
               html.escape(page), html.escape(src_text),
               html.escape(tgt_text), html.escape(status)))

    nav_links = " ".join(
        '<a href="#%s">%s</a>' % (html.escape(a), html.escape(a))
        for a in nav_ids)
    doc = (
        "<!DOCTYPE html>\n<html lang=\"zh\">\n<head>\n"
        "<meta charset=\"utf-8\">\n<title>bilingual alignment</title>\n"
        "<style>%s</style>\n</head>\n<body>\n"
        "<h1>Bilingual paragraph alignment</h1>\n"
        "<p class=\"summary\">%s</p>\n"
        "<nav>%s</nav>\n"
        "<table>\n<thead><tr><th class=\"seg\">Seg ID</th><th>Page</th>"
        "<th>Source</th><th>Translation</th><th>Status</th></tr></thead>\n"
        "<tbody>\n%s\n</tbody>\n</table>\n</body>\n</html>\n"
        % (CSS, html.escape(summary), nav_links, "\n".join(rows)))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(doc)

    # ---------- Markdown ----------
    if args.md:
        lines = ["# Bilingual paragraph alignment", "",
                 summary, "",
                 "| Seg ID | Page | Status | Source (<=80 chars) | "
                 "Translation (<=80 chars) |", "|---|---|---|---|---|"]
        for p in pairs:
            seg = p["src_id"] or "(extra)"
            sp = src.get(p["src_id"]) if p["src_id"] else None
            page = ("%d-%d" % (sp["page_start"], sp["page_end"])) if sp else "-"
            src_t = md_cell(sp["text"]) if sp else "(no source)"
            tgt_t = md_cell(" / ".join(tgts[j]["text"] for j in p["tgt_ids"]
                                       if 0 <= j < len(tgts))) \
                if p["tgt_ids"] else "(no translation)"
            lines.append("| %s | %s | %s | %s | %s |"
                         % (seg, page, p["status"], src_t, tgt_t))
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    print("rendered %d pairs -> %s" % (len(pairs), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
