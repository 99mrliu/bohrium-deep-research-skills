#!/usr/bin/env python3
"""apply_tex_edit.py -- structured, source-preserving edit of a .tex figure
source. Never overwrites without a version backup; every op is journaled.

Usage:
    python3 apply_tex_edit.py --tex FILE --ops OPS.json --edit-record RECORD.json

ops JSON: a list of operations, each one of:
  {"op": "replace-label", "old": "STAT3", "new": "p-STAT3"}
      Exact-substring replacement intended for node/edge label text.
      Semantically identical to replace-text but logged under a clearer name.
  {"op": "replace-text", "old": "...", "new": "..."}
      Exact-substring replacement anywhere in the source.
  {"op": "set-color", "target": "protein", "color": "blue!30"}
      Replaces the *definition* color of a biopathway style: finds the line
      "<target>/.style=" (or "<target>/.append style=") and swaps the first
      "fill=<...>" or "draw=<...>" color token; if none present, appends
      "fill=<color>" to that style line. If the style line is not found,
      falls back to replacing occurrences of "<target>" used as a node/edge
      style option is NOT attempted (too risky) -> the op fails honestly.
  {"op": "comment-out", "pattern": "..."}
      Prefixes every line containing the exact substring with "% " (unless
      already commented). Use to hide an element while keeping source.

Behavior:
  * Before any modification the original file is copied to
    <tex_dir>/versions/<basename>.vN.tex with N = next free integer.
  * Each op is applied independently with exact-match checking; an op whose
    target string is absent is marked "failed" in the journal and does NOT
    abort the remaining ops (but sets overall success=false).
  * Journal entries appended to the edit-record JSON file:
    {"timestamp", "tex", "version_backup", "op", "before_snippet",
     "after_snippet", "result": "applied"|"failed", "detail"}.
  * Prints a JSON summary; exit 0 if all ops applied, 1 if any failed,
    2 bad args.
Only Python 3 standard library.
"""

import argparse
import datetime
import json
import os
import re
import sys


def load_json(path, default):
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return default


def next_version(tex_path):
    tex_dir = os.path.dirname(os.path.abspath(tex_path))
    base = os.path.splitext(os.path.basename(tex_path))[0]
    vdir = os.path.join(tex_dir, "versions")
    os.makedirs(vdir, exist_ok=True)
    n = 1
    while os.path.isfile(os.path.join(vdir, "%s.v%d.tex" % (base, n))):
        n += 1
    backup = os.path.join(vdir, "%s.v%d.tex" % (base, n))
    with open(tex_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    with open(backup, "w", encoding="utf-8") as fh:
        fh.write(content)
    return backup, content


def snippet(text, needle, span=60):
    idx = text.find(needle)
    if idx < 0:
        return ""
    lo = max(0, idx - span)
    hi = min(len(text), idx + len(needle) + span)
    return text[lo:hi].replace("\n", "\\n")


def op_replace(text, old, new):
    if old not in text:
        return text, "failed", "old string not found (exact match required)"
    return text.replace(old, new), "applied", ""


def op_set_color(text, target, color):
    """Swap fill=/draw= color token inside a style definition (may span lines).

    The style value is everything up to the brace that closes "<target>/.style={";
    we accumulate lines until braces balance, prefer replacing fill=, else draw=,
    else append fill=<color> just before the closing brace.
    """
    lines = text.splitlines(keepends=True)
    pat = re.compile(r"(^\s*|[,{]\s*)" + re.escape(target) + r"\s*/\s*\.(?:append\s+)?style\s*=")
    for i, ln in enumerate(lines):
        if not pat.search(ln):
            continue
        # accumulate the (possibly multi-line) style value
        block, depth, j, started = [], 0, i, False
        while j < len(lines):
            block.append(lines[j])
            for ch in lines[j]:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
            j += 1
            if started and depth <= 0:
                break
        blob = "".join(block)
        m = re.search(r"fill\s*=\s*([^,\]}]+)", blob)
        key = "fill"
        if not m:
            m = re.search(r"draw\s*=\s*([^,\]}]+)", blob)
            key = "draw"
        if m:
            newblob = blob[:m.start()] + "%s=%s" % (key, color) + blob[m.end():]
        else:
            # insert fill=<color> before the final closing brace of the value
            k = blob.rfind("}")
            if k < 0:
                return text, "failed", "malformed style block for '%s'" % target
            head = blob[:k].rstrip()
            sep = "" if head.endswith(("{", ",")) else ", "
            newblob = head + sep + "fill=%s" % color + blob[k:]
        lines[i:j] = [newblob]
        return "".join(lines), "applied", (
            "style '%s' updated at lines %d-%d (%s=)" % (target, i + 1, j, key))
    return text, "failed", ("no style definition line for '%s' found; refusing "
                            "risky fallback (edit the .tex by hand instead)" % target)


def op_comment_out(text, pattern):
    if pattern not in text:
        return text, "failed", "pattern not found (exact match required)"
    lines = text.splitlines(keepends=True)
    hit = 0
    for i, ln in enumerate(lines):
        stripped = ln.lstrip()
        if pattern in ln and not stripped.startswith("%"):
            indent = ln[: len(ln) - len(stripped)]
            lines[i] = indent + "% " + stripped
            hit += 1
    if hit == 0:
        return text, "failed", "pattern only present in already-commented lines"
    return "".join(lines), "applied", "%d line(s) commented out" % hit


def apply_op(text, op):
    kind = op.get("op")
    if kind in ("replace-label", "replace-text"):
        return op_replace(text, str(op.get("old", "")), str(op.get("new", "")))
    if kind == "set-color":
        return op_set_color(text, str(op.get("target", "")), str(op.get("color", "")))
    if kind == "comment-out":
        return op_comment_out(text, str(op.get("pattern", "")))
    return text, "failed", "unknown op type: %r" % kind


def main():
    ap = argparse.ArgumentParser(description="Structured source-preserving .tex edit.")
    ap.add_argument("--tex", required=True)
    ap.add_argument("--ops", required=True, help="JSON file: list of ops")
    ap.add_argument("--edit-record", required=True, help="journal JSON (appended)")
    args = ap.parse_args()

    if not os.path.isfile(args.tex):
        print(json.dumps({"success": False, "error": "tex not found: %s" % args.tex}))
        return 2
    try:
        ops = load_json(args.ops, None)
        assert isinstance(ops, list) and ops, "ops must be a non-empty list"
    except Exception as exc:
        print(json.dumps({"success": False, "error": "ops file invalid: %s" % exc}))
        return 2

    backup, original = next_version(args.tex)
    text = original
    record = load_json(args.edit_record, [])
    results = []

    for op in ops:
        before = snippet(text, str(op.get("old", op.get("target", op.get("pattern", "")))))
        new_text, result, detail = apply_op(text, op)
        after = snippet(new_text, str(op.get("new", op.get("color", op.get("pattern", "")))))
        entry = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "tex": os.path.abspath(args.tex),
            "version_backup": backup,
            "op": op,
            "before_snippet": before,
            "after_snippet": after,
            "result": result,
            "detail": detail,
        }
        record.append(entry)
        results.append({"op": op.get("op"), "result": result, "detail": detail})
        if result == "applied":
            text = new_text

    if text != original:
        with open(args.tex, "w", encoding="utf-8") as fh:
            fh.write(text)
    rec_dir = os.path.dirname(os.path.abspath(args.edit_record))
    os.makedirs(rec_dir, exist_ok=True)
    with open(args.edit_record, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)

    failed = [r for r in results if r["result"] != "applied"]
    print(json.dumps({
        "success": not failed,
        "version_backup": backup,
        "modified": text != original,
        "ops_total": len(results),
        "ops_failed": len(failed),
        "results": results,
        "edit_record": os.path.abspath(args.edit_record),
    }, ensure_ascii=False, indent=1))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
