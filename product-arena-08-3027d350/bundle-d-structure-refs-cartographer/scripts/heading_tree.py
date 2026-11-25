#!/usr/bin/env python3
"""heading_tree.py - detect multi-level section headings from per-page text.

Input : per-page text file with '=== page N ===' markers (see common.py),
        plus an optional size-hint TSV (page<TAB>line<TAB>font_size).
Output: <out>/headings.json  nested tree + flat list + inconsistencies
        <out>/toc.json       flat table of contents with anchors and pages

Detection rules (deterministic, regex + heuristics):
  * numbered headings        1 / 1.1 / 1.1.1   (title must contain no '.')
  * appendix headings        Appendix A / A.1
  * known unnumbered heads   Abstract, References, Acknowledgments, ...
  * ALL-CAPS short lines     (>=85% uppercase letters)
  * size-hint short lines    (only when --sizes is given)

Numbering gaps (1.3 after 1.1), missing parents (2.2.1 without 2.2),
duplicate numbers and level jumps are REPORTED in 'inconsistencies',
never auto-fixed.

Exit codes: 0 headings found, 2 usage/IO error, 3 no headings detected.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_pages, read_sizes, write_json, median, slugify

NUMBERED_RE = re.compile(r"^(\d+(?:\.\d+){0,4})\.?\s+([A-Za-z\"“‘][^.\n]{0,90})$")
APP_SUB_RE = re.compile(r"^([A-Z])\.(\d+(?:\.\d+){0,3})\.?\s+([A-Za-z][^.\n]{0,80})$")
APPENDIX_RE = re.compile(r"^[Aa]ppendix\s+([A-Z])\b[:\-. ]*(.*)$")
KNOWN_LEVEL1 = {
    "abstract", "keywords", "key words", "references", "bibliography",
    "acknowledgments", "acknowledgements", "appendix", "appendices",
    "supplementary material", "supplementary materials",
}
MAX_HEADING_LEN = 100
MIN_CAPS_LETTERS = 4
CAPS_RATIO = 0.85


def classify(line, size, body_size):
    """Classify one line; return heading dict or None."""
    s = line.strip()
    if not s or len(s) > MAX_HEADING_LEN:
        return None
    m = NUMBERED_RE.match(s)
    if m:
        num, title = m.group(1), m.group(2).strip()
        return {"number": num, "title": title,
                "level": num.count(".") + 1, "kind": "numbered"}
    m = APP_SUB_RE.match(s)
    if m:
        num = m.group(1) + "." + m.group(2)
        return {"number": num, "title": m.group(3).strip(),
                "level": num.count(".") + 1, "kind": "appendix"}
    m = APPENDIX_RE.match(s)
    if m:
        title = m.group(2).strip() or ("Appendix " + m.group(1))
        return {"number": m.group(1), "title": title, "level": 1, "kind": "appendix"}
    norm = s.rstrip(":").strip().lower()
    if norm in KNOWN_LEVEL1:
        return {"number": None, "title": s.rstrip(":"), "level": 1, "kind": "known"}
    letters = [c for c in s if c.isalpha()]
    if (len(letters) >= MIN_CAPS_LETTERS and len(s) <= 80
            and sum(c.isupper() for c in letters) / len(letters) >= CAPS_RATIO):
        level = 1
        if size is not None and body_size:
            level = 1 if size >= body_size * 1.3 else 2
        return {"number": None, "title": s, "level": level, "kind": "allcaps"}
    if (size is not None and body_size and size >= body_size * 1.2
            and len(s) <= 80 and not s.endswith(".")):
        level = 1 if size >= body_size * 1.35 else 2
        return {"number": None, "title": s, "level": level, "kind": "sizehint"}
    return None


def detect(pages, sizes):
    body = median(sizes.values()) if sizes else None
    found = []
    for pg in pages:
        for i, line in enumerate(pg["lines"], 1):
            size = sizes.get((pg["page"], i)) if sizes else None
            h = classify(line, size, body)
            if h:
                h["page"] = pg["page"]
                h["line"] = i
                found.append(h)
    return found


def make_anchor(h, used):
    if h["number"]:
        base = "sec-" + h["number"].replace(".", "-")
    else:
        base = "sec-" + slugify(h["title"])
    anchor, n = base, 2
    while anchor in used:
        anchor = "%s-%d" % (base, n)
        n += 1
    used.add(anchor)
    return anchor


def build(headings):
    """Build the nested tree; return (root, flat, inconsistencies)."""
    inconsistencies = []
    root = {"number": None, "title": "<document>", "level": 0, "page": None,
            "anchor": "root", "kind": "root", "children": []}
    stack = [root]
    number_to_node = {}
    flat = []
    used_anchors = {"root"}
    prev = None

    for h in headings:
        anchor = make_anchor(h, used_anchors)
        node = {"number": h["number"], "title": h["title"], "level": h["level"],
                "page": h["page"], "line": h["line"], "anchor": anchor,
                "kind": h["kind"], "children": []}
        flat.append({k: node[k] for k in
                     ("anchor", "number", "title", "level", "page", "line", "kind")})

        if h["number"] and h["number"] in number_to_node:
            inconsistencies.append({
                "type": "duplicate_number",
                "message": "section number '%s' used more than once "
                           "(second occurrence page %d)" % (h["number"], h["page"]),
                "page": h["page"]})
        if prev is not None and h["level"] > prev["level"] + 1:
            inconsistencies.append({
                "type": "level_jump",
                "message": "heading '%s' (level %d, page %d) follows '%s' "
                           "(level %d) with no intermediate level"
                           % (h["title"], h["level"], h["page"],
                              prev["title"], prev["level"]),
                "page": h["page"]})

        # default parent: nearest open heading with smaller level
        while len(stack) > 1 and stack[-1]["level"] >= h["level"]:
            stack.pop()

        # numbered headings: prefer the node whose number is a prefix
        parent = None
        if h["number"] and "." in h["number"]:
            parts = h["number"].split(".")
            direct = ".".join(parts[:-1])
            for k in range(len(parts) - 1, 0, -1):
                pfx = ".".join(parts[:k])
                if pfx in number_to_node:
                    parent = number_to_node[pfx]
                    break
            if direct not in number_to_node:
                inconsistencies.append({
                    "type": "missing_parent",
                    "message": "heading '%s %s' (page %d) implies parent section "
                               "'%s' which is absent from the document"
                               % (h["number"], h["title"], h["page"], direct),
                    "page": h["page"]})
        if parent is not None:
            idx = next((i for i, n in enumerate(stack) if n is parent), None)
            if idx is not None:
                stack[:] = stack[: idx + 1]
            else:
                parent = None
        if parent is None:
            parent = stack[-1]
        parent["children"].append(node)

        if parent is not root and h["level"] > parent["level"] + 1:
            inconsistencies.append({
                "type": "level_jump",
                "message": "heading '%s %s' (level %d, page %d) is nested under "
                           "'%s' (level %d): intermediate level missing"
                           % (h["number"] or "", h["title"], h["level"], h["page"],
                              (parent["number"] or parent["title"]), parent["level"]),
                "page": h["page"]})

        if h["number"]:
            number_to_node[h["number"]] = node
        stack.append(node)
        prev = h

    def check_gaps(node):
        kids = []
        for c in node["children"]:
            if not c["number"] or c["level"] != node["level"] + 1:
                continue
            # only compare children belonging to this numbering family
            if node["number"] and not c["number"].startswith(node["number"] + "."):
                continue
            if not node["number"] and "." in c["number"]:
                continue
            kids.append(c)
        seq = []
        for c in kids:
            last = c["number"].split(".")[-1]
            if last.isdigit():
                seq.append((int(last), c))
        if seq:
            expected = seq[0][0]
            for value, child in seq:
                if value != expected:
                    parent_name = node["number"] or node["title"]
                    inconsistencies.append({
                        "type": "numbering_gap",
                        "message": "under '%s': expected child number ending "
                                   "in %d but found '%s' (page %d)"
                                   % (parent_name, expected,
                                      child["number"], child["page"]),
                        "page": child["page"]})
                    expected = value
                expected += 1
        for c in node["children"]:
            check_gaps(c)

    check_gaps(root)
    return root, flat, inconsistencies


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build a multi-level heading tree and TOC from per-page text.")
    ap.add_argument("--pages", required=True,
                    help="per-page text file with '=== page N ===' markers")
    ap.add_argument("--sizes", default=None,
                    help="optional TSV: page<TAB>line_no<TAB>font_size")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)

    try:
        pages, warnings = read_pages(args.pages)
    except OSError as exc:
        print("error: cannot read pages file: %s" % exc, file=sys.stderr)
        return 2
    sizes = {}
    if args.sizes:
        try:
            sizes = read_sizes(args.sizes)
        except OSError as exc:
            print("error: cannot read sizes file: %s" % exc, file=sys.stderr)
            return 2

    headings = detect(pages, sizes)
    tree, flat, inconsistencies = build(headings)
    status = "ok" if headings else "no_headings_detected"

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    write_json({
        "status": status,
        "meta": {"source": Path(args.pages).name,
                 "pages": len(pages),
                 "headings": len(flat),
                 "warnings": warnings},
        "flat": flat,
        "tree": tree,
        "inconsistencies": inconsistencies,
    }, outdir / "headings.json")
    write_json({
        "status": status,
        "count": len(flat),
        "entries": [{"anchor": e["anchor"], "number": e["number"],
                     "title": e["title"], "level": e["level"], "page": e["page"]}
                    for e in flat],
    }, outdir / "toc.json")

    print("heading_tree: headings=%d inconsistencies=%d -> %s"
          % (len(flat), len(inconsistencies), outdir))
    for w in warnings:
        print("warning: %s" % w, file=sys.stderr)
    return 0 if headings else 3


if __name__ == "__main__":
    sys.exit(main())
