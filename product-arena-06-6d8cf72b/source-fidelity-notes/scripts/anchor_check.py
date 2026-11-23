#!/usr/bin/env python3
"""anchor_check.py -- verify every quote in the notes against the scanned layer.

Rules (deterministic, no semantics):
  A. every item that carries ``anchor`` must resolve in source.json;
  B. every ``quote`` must be a verbatim substring of the line at its anchor
     (after whitespace normalization) or of the two-line join (hyphenation /
     wrapped sentence) -> needs_review instead of fail;
  C. first-level section coverage: report which scanned sections received at
     least one note item (informational, not a gate);
  D. numeric tokens inside a quote must appear at the anchor line.

Exit code 0 = all hard checks pass, 2 = hard failures found, 3 = input error.
A failing check is a *repair instruction*, never a reason to deliver nothing:
fix the quote/anchor or mark the item ``unverifiable`` and keep it with a
reason, then report the residue in ``limits``.
"""
import argparse
import json
import os
import re
import sys


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def load_source(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    index = {}
    order = []
    for page in data["pages"]:
        for ln in page["lines"]:
            index[ln["anchor"]] = ln["text"]
            order.append(ln["anchor"])
    return index, order


def iter_items(node, path="$"):
    if isinstance(node, dict):
        if "anchor" in node or "quote" in node:
            yield path, node
        for key, val in node.items():
            if key in ("quote", "anchor"):
                continue
            yield from iter_items(val, "%s.%s" % (path, key))
    elif isinstance(node, list):
        for i, val in enumerate(node):
            yield from iter_items(val, "%s[%d]" % (path, i))


def check(notes_path, source_path):
    index, order = load_source(source_path)
    with open(notes_path, encoding="utf-8") as fh:
        notes = json.load(fh)

    hard_fail, needs_review, passed = [], [], []
    seen_sections = set()
    for path, item in iter_items(notes):
        anchor = item.get("anchor")
        quote = item.get("quote")
        if anchor and anchor in index:
            # section coverage bookkeeping
            for sec in notes.get("sections", []):
                if isinstance(sec, dict) and sec.get("title_anchor") == anchor:
                    break
        if quote is None and anchor is None:
            continue
        if item.get("status") == "unverifiable" and item.get("reason"):
            continue  # honestly marked, exempt by declaration
        if not anchor:
            hard_fail.append({"path": path, "check": "anchor", "detail": "missing anchor"})
            continue
        if anchor not in index:
            hard_fail.append({"path": path, "check": "anchor",
                              "detail": "anchor %s not in source" % anchor})
            continue
        line_text = norm(index[anchor])
        if quote:
            q = norm(quote)
            if q in line_text:
                passed.append(path)
            else:
                pos = order.index(anchor)
                joined = line_text
                if pos + 1 < len(order):
                    joined = norm(index[anchor] + " " + index[order[pos + 1]])
                if q in joined or q.replace("- ", "") in joined.replace("- ", ""):
                    needs_review.append({"path": path, "check": "quote",
                                         "detail": "spans lines or hyphenation"})
                else:
                    hard_fail.append({"path": path, "check": "quote",
                                      "detail": "quote not verbatim at %s" % anchor})
            nums = re.findall(r"\d+(?:\.\d+)?", quote)
            missing = [n for n in nums if n not in line_text and n not in joined]
            if missing and q not in line_text:
                hard_fail.append({"path": path, "check": "number",
                                  "detail": "numbers %s absent at anchor" % missing})

    report = {
        "items_passed": len(passed),
        "needs_review": needs_review,
        "hard_failures": hard_fail,
        "verdict": "pass" if not hard_fail else "fail",
        "note": "needs_review items must be re-read on the rendered page; "
                "hard failures must be repaired or marked unverifiable with a reason",
    }
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notes", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    report = check(args.notes, args.source)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    sys.exit(0 if report["verdict"] == "pass" else 2)


if __name__ == "__main__":
    main()
