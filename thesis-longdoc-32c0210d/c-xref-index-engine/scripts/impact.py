#!/usr/bin/env python3
"""impact.py — 级联影响分析：给定改动锚点，列出 index.json 中所有受影响位置。

锚点三选一：
  --anchor figure:2-2 | table:2-1 | 2-2   图表编号（省略类型则两类都匹配）
  --term   "UV固化胶"                      术语（自动扩展到同组全部变体；也匹配缩略语定义）
  --section "2.1" 或 "固化工艺"            标题编号或标题文本子串
可选：
  --renumber figure:2-2=2-3               模拟编号变更，列出所有需同步修改的题注/引用点

影响类型：caption-definition（定义点/题注）| reference（引用点）|
numbering-successor（编号后继，重编号可能级联）| usage（术语使用点）|
abbreviation-definition | citation | section-heading。
输出 impact_report.json，按 (file, line) 排序，确定性。
"""
import argparse
import json
import re
import sys

_TRANS = str.maketrans("０１２３４５６７８９（）", "0123456789()")
_HYPHENS = "‐‑‒–—−"
_KIND = {"figure": "figure", "fig": "figure", "图": "figure",
         "table": "table", "表": "table"}


def _norm(s):
    s = s.translate(_TRANS)
    for h in _HYPHENS:
        s = s.replace(h, "-")
    return s


def canon_number(n):
    return "-".join(re.split(r"[-.]+", _norm(n)))


def parse_anchor(spec):
    """'figure:2-2' -> ('figure','2-2'); '2-2' -> (None,'2-2')"""
    if ":" in spec:
        k, n = spec.split(":", 1)
        k = _KIND.get(k.strip().lower())
        if k is None:
            raise ValueError("unknown anchor kind in %r (use figure/table)" % spec)
        return k, canon_number(n)
    return None, canon_number(spec)


def aff(file, line, itype, detail):
    return {"file": file, "line": line, "impact_type": itype, "detail": detail}


def impact_float(idx, kind, num):
    out = []
    for f in idx.get("floats", []):
        if (kind is None or f["kind"] == kind) and f["number"] == num:
            out.append(aff(f["file"], f["line"], "caption-definition",
                           "%s %s 题注定义点：%s" % (f["kind"], num, f.get("caption", "")[:60])))
    for r in idx.get("float_refs", []):
        if (kind is None or r["kind"] == kind) and r["number"] == num:
            out.append(aff(r["file"], r["line"], "reference",
                           "正文对 %s %s 的引用点" % (r["kind"], num)))
    # 编号后继：同类型、同章节前缀、末段更大的题注
    parts = num.split("-")
    if parts[-1].isdigit():
        prefix, last = parts[:-1], int(parts[-1])
        for f in idx.get("floats", []):
            if kind is not None and f["kind"] != kind:
                continue
            p2 = f["number"].split("-")
            if p2[:-1] == prefix and p2[-1].isdigit() and int(p2[-1]) > last:
                out.append(aff(f["file"], f["line"], "numbering-successor",
                               "%s %s 是同组编号后继，锚点重编号时可能级联" % (f["kind"], f["number"])))
    return out


def impact_term(idx, term):
    out = []
    variants = [term]
    for g in idx.get("term_groups", []):
        if term in g["variants"]:
            variants = g["variants"]
            break
    forms = idx.get("term_forms", {})
    for v in variants:
        for o in forms.get(v, []):
            out.append(aff(o["file"], o["line"], "usage",
                           "术语变体“%s”使用点（列 %d）" % (v, o.get("column", 0))))
    for d in idx.get("abbreviations", {}).get("definitions", []):
        if d["abbr"] == term or d["full"] == term:
            out.append(aff(d["file"], d["line"], "abbreviation-definition",
                           "缩略语定义点：%s（%s）" % (d["abbr"], d["full"])))
    return out


def impact_section(idx, spec):
    hs = [h for h in idx.get("headings", [])
          if h.get("number") == spec or spec in h.get("text", "")]
    if not hs:
        return [], None
    hs.sort(key=lambda h: (h["file"], h["line"]))
    h = hs[0]
    # 区间：同文件中该行之后、下一个同级或更高级标题之前
    end = None
    for h2 in idx.get("headings", []):
        if h2["file"] == h["file"] and h2["line"] > h["line"] and h2["level"] <= h["level"]:
            end = h2["line"]
            break

    def in_span(file, line):
        return file == h["file"] and h["line"] < line and (end is None or line < end)

    out = [aff(h["file"], h["line"], "section-heading",
               "命中标题：%s（level %d，区间止于行 %s）" % (h["text"], h["level"], end or "EOF"))]
    for f in idx.get("floats", []):
        if in_span(f["file"], f["line"]):
            out.append(aff(f["file"], f["line"], "caption-definition",
                           "区间内题注 %s %s" % (f["kind"], f["number"])))
    for r in idx.get("float_refs", []):
        if in_span(r["file"], r["line"]):
            out.append(aff(r["file"], r["line"], "reference",
                           "区间内引用 %s %s" % (r["kind"], r["number"])))
    for c in idx.get("citations", {}).get("references", []):
        if in_span(c["file"], c["line"]):
            out.append(aff(c["file"], c["line"], "citation",
                           "区间内引文点 %s" % c["numbers"]))
    for v, occs in idx.get("term_forms", {}).items():
        for o in occs:
            if in_span(o["file"], o["line"]):
                out.append(aff(o["file"], o["line"], "usage", "区间内术语“%s”" % v))
    return out, h


def main():
    ap = argparse.ArgumentParser(description="级联影响分析")
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--anchor", help="figure:2-2 | table:2-1 | 2-2")
    ap.add_argument("--term", help="术语")
    ap.add_argument("--section", help="标题编号或文本子串")
    ap.add_argument("--renumber", help="如 figure:2-2=2-3，模拟编号变更")
    args = ap.parse_args()
    with open(args.index, encoding="utf-8") as fh:
        idx = json.load(fh)

    chosen = [x for x in (args.anchor, args.term, args.section) if x]
    if len(chosen) != 1:
        print("ERROR: exactly one of --anchor/--term/--section is required", file=sys.stderr)
        return 2

    report = {"schema": "impact-report/v1", "affected": [], "renumber": None}
    if idx.get("note"):
        report["note"] = idx["note"]

    if args.anchor:
        kind, num = parse_anchor(args.anchor)
        report["anchor"] = {"type": "float", "kind": kind, "number": num}
        report["affected"] = impact_float(idx, kind, num)
    elif args.term:
        report["anchor"] = {"type": "term", "term": args.term}
        report["affected"] = impact_term(idx, args.term)
    else:
        report["anchor"] = {"type": "section", "section": args.section}
        affected, h = impact_section(idx, args.section)
        report["affected"] = affected
        if h is None:
            report["warning"] = "section not found: %r" % args.section

    if args.renumber:
        if "=" not in args.renumber:
            print("ERROR: --renumber expects FROM=TO, e.g. figure:2-2=2-3", file=sys.stderr)
            return 2
        frm, to = args.renumber.split("=", 1)
        fk, fn = parse_anchor(frm)
        tn = canon_number(to.split(":", 1)[-1])
        points = []
        for f in idx.get("floats", []):
            if (fk is None or f["kind"] == fk) and f["number"] == fn:
                points.append({"file": f["file"], "line": f["line"],
                               "role": "caption-definition", "current": fn, "proposed": tn})
        for r in idx.get("float_refs", []):
            if (fk is None or r["kind"] == fk) and r["number"] == fn:
                points.append({"file": r["file"], "line": r["line"],
                               "role": "reference", "current": fn, "proposed": tn})
        points.sort(key=lambda p: (p["file"], p["line"]))
        report["renumber"] = {"from": {"kind": fk, "number": fn}, "to": tn,
                              "update_points": points, "update_count": len(points)}

    report["affected"].sort(key=lambda a: (a["file"], a["line"]))
    report["affected_count"] = len(report["affected"])
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("impact report: %s -> affected=%d%s" % (
        args.out, report["affected_count"],
        " renumber_updates=%d" % report["renumber"]["update_count"] if report["renumber"] else ""))
    for a in report["affected"]:
        print("  %s:%d [%s] %s" % (a["file"], a["line"], a["impact_type"], a["detail"][:80]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
