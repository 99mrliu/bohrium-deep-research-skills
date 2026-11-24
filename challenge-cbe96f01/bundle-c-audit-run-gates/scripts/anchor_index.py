#!/usr/bin/env python3
"""anchor_index.py -- audit-run-gates stage 0 anchor table (gate G0, part 2).

pages.jsonl -> anchors.json:
  paragraph anchors  p<page>.P<para>     (blank-line separated blocks)
  figure/table       p<page>.Fig<n> / p<page>.Tab<n>
  reference section  reference_anchor (first page whose lines contain a
                     References heading)
Deterministic: no timestamps, stable ordering.
"""
import argparse
import json
import re
import sys

REF_HEAD = re.compile(
    r"^\s*(references|bibliography|works\s+cited|参考文献)\s*:?\s*$",
    re.IGNORECASE)
FIGTAB = re.compile(r"^\s*(figure|fig\.|table|图|表)\s*(\d+)", re.IGNORECASE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    anchors = []
    ref_anchor = None
    with open(args.pages, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            pg = json.loads(line)
            page = pg["page"]
            blocks = [b for b in re.split(r"\n\s*\n", pg["text"])
                      if b.strip()]
            for bi, block in enumerate(blocks, 1):
                first = " ".join(block.strip().split())[:120]
                anchors.append({"anchor": f"p{page}.P{bi}", "page": page,
                                "kind": "paragraph", "head": first})
                for ln in block.splitlines():
                    m = FIGTAB.match(ln)
                    if m:
                        kind = ("figure" if m.group(1).lower()
                                .startswith(("fig", "figure", "图"))
                                else "table")
                        anchors.append({
                            "anchor": f"p{page}."
                                      f"{'Fig' if kind == 'figure' else 'Tab'}"
                                      f"{m.group(2)}",
                            "page": page, "kind": kind,
                            "head": " ".join(ln.split())[:120]})
                    if ref_anchor is None and REF_HEAD.match(ln):
                        ref_anchor = f"p{page}.P{bi}"
    table = {"anchors": anchors, "reference_anchor": ref_anchor,
             "n_anchors": len(anchors)}
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(table, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"anchors": len(anchors),
                      "reference_anchor": ref_anchor}, ensure_ascii=False))
    sys.exit(0 if anchors else 1)


if __name__ == "__main__":
    main()
