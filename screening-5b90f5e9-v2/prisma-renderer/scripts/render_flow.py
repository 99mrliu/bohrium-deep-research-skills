#!/usr/bin/env python3
"""render_flow.py -- 从计数台账渲染 PRISMA 2020 风格流程图。

输入 counts.json：
{"identified": 200, "duplicates_removed": 23, "screened": 177,
 "excluded": 160, "included": 12, "needs_human": 5,
 "exclusion_reasons": {"EX-DESIGN": 80, "EX-POPULATION": 50, "EX-OUTCOME": 30},
 "databases": ["pubmed", "scopus", "wos"], "search_date": "2026-11-24"}

产物（--out 目录）：
  flow.svg          矢量流程图（确定性布局，同输入同字节）
  flow.md           Mermaid 版本 + 计数表（供 Markdown 报告内嵌）
  render_check.json 渲染自检：SVG well-formed、计数闭合、盒/边数量

闭合门（references/prisma2020_spec.md）：
  R1 identified - duplicates_removed == screened
  R2 screened == excluded + included + needs_human
  R3 exclusion_reasons 合计 == excluded（给出理由分解时）
不闭合 exit 3——数字对不上时禁止渲染"好看但错"的图。
退出码：0=正常；2=输入缺失/不合法；3=闭合 FAIL。
"""
import argparse
import json
import os
import sys
import xml.dom.minidom
import xml.sax.saxutils as sx

FONT = "font-family='Helvetica,Arial,sans-serif' font-size='12'"


def text_w(s):
    w = 0
    for ch in s:
        w += 12 if ord(ch) > 0x2E7F else 6.6
    return w


def esc(s):
    return sx.escape(str(s))


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def box(self, x, y, w, h, lines, fill="#eef3fb"):
        p = ["<rect x='%.1f' y='%.1f' width='%.1f' height='%.1f' rx='4' "
             "fill='%s' stroke='#345' stroke-width='1.2'/>" % (x, y, w, h, fill)]
        ty = y + 18
        for ln in lines:
            p.append("<text x='%.1f' y='%.1f' text-anchor='middle' %s>%s</text>"
                     % (x + w / 2, ty, FONT, esc(ln)))
            ty += 15
        self.parts.extend(p)

    def arrow(self, x1, y1, x2, y2):
        self.parts.append(
            "<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f' stroke='#345' "
            "stroke-width='1.4' marker-end='url(#ah)'/>" % (x1, y1, x2, y2))

    def render(self):
        head = ("<svg xmlns='http://www.w3.org/2000/svg' width='%.0f' height='%.0f'>"
                "<defs><marker id='ah' markerWidth='8' markerHeight='8' refX='7' "
                "refY='3' orient='auto'><path d='M0,0 L7,3 L0,6 z' fill='#345'/>"
                "</marker></defs>"
                "<rect width='100%%' height='100%%' fill='white'/>" % (self.w, self.h))
        return head + "".join(self.parts) + "</svg>"


def check(name, ok, detail):
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def main():
    ap = argparse.ArgumentParser(description="PRISMA 流程图渲染")
    ap.add_argument("--counts", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if not os.path.isfile(args.counts):
        print("RENDER-ERROR: counts 缺失：%s" % args.counts, file=sys.stderr)
        sys.exit(2)
    c = json.load(open(args.counts, encoding="utf-8"))
    need = ["identified", "duplicates_removed", "screened", "excluded",
            "included", "needs_human"]
    missing = [k for k in need if not isinstance(c.get(k), int)]
    if missing:
        print("RENDER-ERROR: counts 缺整数键：%s" % missing, file=sys.stderr)
        sys.exit(2)

    checks = []
    r1 = c["identified"] - c["duplicates_removed"] == c["screened"]
    checks.append(check("R1-identification-closure", r1,
                        "%d - %d = %d vs screened=%d" % (
                            c["identified"], c["duplicates_removed"],
                            c["identified"] - c["duplicates_removed"],
                            c["screened"])))
    r2 = c["screened"] == c["excluded"] + c["included"] + c["needs_human"]
    checks.append(check("R2-screening-closure", r2,
                        "screened=%d vs %d+%d+%d=%d" % (
                            c["screened"], c["excluded"], c["included"],
                            c["needs_human"],
                            c["excluded"] + c["included"] + c["needs_human"])))
    reasons = c.get("exclusion_reasons") or {}
    if reasons:
        tot = sum(reasons.values())
        r3 = tot == c["excluded"]
        checks.append(check("R3-reason-breakdown-closure", r3,
                            "理由合计=%d vs excluded=%d" % (tot, c["excluded"])))
    if not all(x["status"] == "PASS" for x in checks):
        report = {"overall": "FAIL", "checks": checks}
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "render_check.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print("RENDER BLOCKED: 计数不闭合，禁止渲染")
        for x in checks:
            print("  %s %s -- %s" % (x["status"], x["check"], x["detail"]))
        sys.exit(3)

    # ---- 布局 ----
    dbs = c.get("databases") or []
    sdate = c.get("search_date") or "未登记"
    reason_lines = ["Records excluded (n=%d)" % c["excluded"]]
    for k in sorted(reasons):
        reason_lines.append("  %s: %d" % (k, reasons[k]))

    col_w = 300
    boxes = [
        ("id", 40, 40, ["Identification", "",
                        "Records identified from" " databases (n=%d)" % c["identified"],
                        "  sources: %s" % (", ".join(dbs) if dbs else "n/a"),
                        "  search date: %s" % sdate,
                        "Duplicates removed (n=%d)" % c["duplicates_removed"]]),
        ("sc", 40, 40 + 130, ["Screening", "",
                              "Records screened (n=%d)" % c["screened"]]),
        ("ex", 40 + col_w + 60, 40 + 130, ["Excluded", ""] + reason_lines),
        ("in", 40, 40 + 260, ["Included", "",
                              "Studies included (n=%d)" % c["included"],
                              "Awaiting human confirmation (n=%d)" % c["needs_human"]]),
    ]
    heights = {k: 30 + 15 * len(lines) for k, _x, _y, lines in boxes}
    total_h = 40 + 260 + heights["in"] + 30
    total_w = 40 + col_w + 60 + col_w + 40
    svg = Svg(total_w, total_h)
    for key, x, y, lines in boxes:
        svg.box(x, y, col_w, heights[key], lines,
                fill="#eef3fb" if key != "ex" else "#fdeeee")
    svg.arrow(40 + col_w / 2, 40 + heights["id"], 40 + col_w / 2, 40 + 130)
    svg.arrow(40 + col_w, 40 + 130 + heights["sc"] / 2,
              40 + col_w + 60, 40 + 130 + heights["ex"] / 2)
    svg.arrow(40 + col_w / 2, 40 + 130 + heights["sc"],
              40 + col_w / 2, 40 + 260)

    svg_text = svg.render()
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "flow.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg_text)

    # Mermaid 版
    mm = ["```mermaid", "flowchart TD",
          "  ID[\"Records identified (n=%d)<br/>Duplicates removed (n=%d)\"]" % (
              c["identified"], c["duplicates_removed"]),
          "  SC[\"Records screened (n=%d)\"]" % c["screened"],
          "  EX[\"Records excluded (n=%d)\"]" % c["excluded"],
          "  IN[\"Studies included (n=%d)<br/>Awaiting human confirmation (n=%d)\"]" % (
              c["included"], c["needs_human"]),
          "  ID --> SC", "  SC --> EX", "  SC --> IN", "```", "",
          "| 环节 | n |", "|---|---|"]
    for label, key in [("identified", "identified"),
                       ("duplicates_removed", "duplicates_removed"),
                       ("screened", "screened"), ("excluded", "excluded"),
                       ("included", "included"), ("needs_human", "needs_human")]:
        mm.append("| %s | %d |" % (label, c[key]))
    with open(os.path.join(args.out, "flow.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(mm) + "\n")

    # 渲染自检
    try:
        xml.dom.minidom.parseString(svg_text)
        wellformed = True
    except Exception:
        wellformed = False
    checks.append(check("R4-svg-wellformed", wellformed,
                        "xml.dom.minidom 解析%s" % ("成功" if wellformed else "失败")))
    report = {
        "overall": "PASS" if all(x["status"] == "PASS" for x in checks) else "FAIL",
        "checks": checks,
        "svg_bytes": len(svg_text.encode("utf-8")),
        "boxes": len(boxes), "arrows": 3,
    }
    with open(os.path.join(args.out, "render_check.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("RENDER %s: flow.svg (%d bytes) + flow.md -> %s" % (
        report["overall"], report["svg_bytes"], args.out))
    sys.exit(0 if report["overall"] == "PASS" else 3)


if __name__ == "__main__":
    main()
