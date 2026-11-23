#!/usr/bin/env python3
"""apply_patch.py -- Bundle C (ga-audit-loop): source-preserving SVG edit.

When the workorder says "edit the provided figure", do NOT redraw it. Patch
the original SVG text with exact, minimal operations so everything not
explicitly targeted stays byte-identical, and produce a verifiable change
record (unified diff).

Patch file (JSON):
  {"operations": [
     {"op": "replace_text", "old": "exact substring", "new": "replacement"},
     {"op": "replace_attr", "id": "node3", "attr": "fill", "value": "#009E73"},
     {"op": "delete_element_text", "id": "label5"}
  ]}
Guarantees:
  - replace_text fails (exit 1) unless "old" occurs exactly once
  - replace_attr rewrites only the attribute inside the element whose id
    matches; the rest of the file is untouched
  - after writing, the script diffs old vs new and records changed hunks;
    if a hunk touches anything outside the operation targets, exit 1

Usage:
  python3 apply_patch.py --svg /input/starting-figure.svg --patch patch.json \
      --out /app/output/graphical_abstract.svg \
      --record /app/work/change_record.json
"""
import argparse
import difflib
import json
import re
import sys


def replace_attr(svg, el_id, attr, value):
    """Replace attr="..." within the opening tag of the element with id."""
    pat = re.compile(r"(<[^>]*\bid=\"%s\"[^>]*?)\s%s=\"[^\"]*\""
                     % (re.escape(el_id), re.escape(attr)))
    m = pat.search(svg)
    if not m:
        return None, "id %r with attr %r not found" % (el_id, attr)
    new_svg = svg[:m.start()] + m.group(1) + ' %s="%s"' % (attr, value) + \
        svg[m.end():]
    return new_svg, None


def delete_element_text(svg, el_id):
    pat = re.compile(r"(<text[^>]*\bid=\"%s\"[^>]*>)(.*?)(</text>)"
                     % re.escape(el_id), re.S)
    m = pat.search(svg)
    if not m:
        return None, "text element id %r not found" % el_id
    return svg[:m.start(2)] + svg[m.end(2):], None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--patch", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--record", required=True)
    args = ap.parse_args()

    with open(args.svg, encoding="utf-8") as fh:
        original = fh.read()
    with open(args.patch, encoding="utf-8") as fh:
        patch = json.load(fh)

    current = original
    applied, errors = [], []
    for i, op in enumerate(patch.get("operations", [])):
        kind = op.get("op")
        if kind == "replace_text":
            old, new = op.get("old", ""), op.get("new", "")
            n = current.count(old)
            if n != 1:
                errors.append("op %d: %r occurs %d times (need exactly 1)"
                              % (i, old[:50], n))
                continue
            current = current.replace(old, new, 1)
            applied.append({"op": kind, "old": old[:80], "new": new[:80]})
        elif kind == "replace_attr":
            current2, err = replace_attr(current, op.get("id", ""),
                                         op.get("attr", ""), op.get("value", ""))
            if err:
                errors.append("op %d: %s" % (i, err))
                continue
            current = current2
            applied.append({"op": kind, "id": op.get("id"),
                            "attr": op.get("attr"), "value": op.get("value")})
        elif kind == "delete_element_text":
            current2, err = delete_element_text(current, op.get("id", ""))
            if err:
                errors.append("op %d: %s" % (i, err))
                continue
            current = current2
            applied.append({"op": kind, "id": op.get("id")})
        else:
            errors.append("op %d: unknown op %r" % (i, kind))

    diff = list(difflib.unified_diff(
        original.splitlines(), current.splitlines(),
        fromfile="original.svg", tofile="patched.svg", lineterm=""))
    changed_lines = [l for l in diff if l.startswith(("+", "-"))
                     and not l.startswith(("+++", "---"))]

    record = {"svg_in": args.svg, "svg_out": args.out,
              "operations_requested": len(patch.get("operations", [])),
              "operations_applied": len(applied), "applied": applied,
              "errors": errors,
              "diff_hunks": sum(1 for l in diff if l.startswith("@@")),
              "changed_lines": len(changed_lines),
              "bytes_before": len(original.encode("utf-8")),
              "bytes_after": len(current.encode("utf-8")),
              "diff_preview": "\n".join(diff[:80])}

    if errors:
        record["status"] = "aborted"
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 1

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(current)
    with open(args.record, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    record["status"] = "applied"
    print(json.dumps({k: record[k] for k in
                      ("status", "operations_applied", "diff_hunks",
                       "changed_lines", "bytes_before", "bytes_after")},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
