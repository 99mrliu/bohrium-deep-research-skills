#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_verdict.py -- 规格 × 渲染实测 → 逐项裁决，产出可复核的渲染账本。

spec 为扁平 JSON（任何来源均可，能指出来源更好）：
{
  "page.size.width_cm": 21.0, "page.size.height_cm": 29.7,
  "page.margin.top_cm": 3.17, "page.columns": 1,
  "fonts.required": ["Liberation Serif"], "fonts.embedded_all": true
}
margin 类裁决取各页实测的 min/max 区间，全部落在容差内才 PASS；
几何 UNMEASURED 时相关项记 UNMEASURED（不猜）。
退出码: 0 无 FAIL; 1 有 FAIL。

用法:
  python3 render_verdict.py spec.json measurements.json --json verdicts.json --md render_ledger.md
"""
import argparse, json, sys

def cm_close(a, b, tol):
    return abs(float(a) - float(b)) <= tol

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec")
    ap.add_argument("measurements")
    ap.add_argument("--json", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--tolerance", type=float, default=0.2,
                    help="边距容差 cm（字形框含 ascent/descent，默认 0.2）")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    meas = json.load(open(a.measurements, encoding="utf-8"))
    geo = meas.get("text_geometry", {})
    pages = geo.get("pages", []) if geo.get("status") == "OK" else []
    fonts = meas.get("fonts", {})
    verdicts = []

    def add(item, expected, measured, verdict, basis):
        verdicts.append({"item": item, "expected": expected, "measured": measured,
                         "verdict": verdict, "basis": basis})

    for key, want in spec.items():
        if key in ("page.size.width_cm", "page.size.height_cm"):
            sizes = meas.get("page_sizes", [])
            got = sizes[0]["w_cm" if key.endswith("width_cm") else "h_cm"] if sizes else None
            ok = got is not None and cm_close(got, want, 0.1)
            add(key, want, got, "PASS" if ok else ("FAIL" if got is not None else "UNMEASURED"),
                "/MediaBox 实测")
        elif key.startswith("page.margin."):
            side = key[len("page.margin."):]
            side = side[:-3] if side.endswith("_cm") else side
            mk = "margin_%s_cm" % side
            if not pages:
                add(key, want, None, "UNMEASURED", "pdftotext 几何不可用")
                continue
            vals = [p[mk] for p in pages if mk in p]
            ok = vals and all(cm_close(v, want, a.tolerance) for v in vals)
            add(key, want, {"min": min(vals), "max": max(vals)} if vals else None,
                "PASS" if ok else "FAIL",
                "pdftotext -bbox 字形框逐页实测（容差 ±%scm）" % a.tolerance)
        elif key == "page.columns":
            if not pages:
                add(key, want, None, "UNMEASURED", "pdftotext 几何不可用")
                continue
            got = max(p.get("columns_detected", 1) for p in pages)
            add(key, want, got, "PASS" if got == want else "FAIL", "版心间隙检测")
        elif key == "fonts.required":
            have = set(fonts.get("fonts", []))
            have_base = {f.split("+")[-1].replace("-", "") for f in have}
            missing = [f for f in want
                       if not any(f.replace(" ", "").lower() in h.replace(" ", "").lower()
                                  or f.replace(" ", "").lower() in hb.lower()
                                  for h in have for hb in {h.split("+")[-1]})]
            add(key, want, sorted(have), "PASS" if not missing else "FAIL",
                "/BaseFont 扫描" + ("；缺: %s" % ", ".join(missing) if missing else ""))
        elif key == "fonts.embedded_all":
            got = fonts.get("embedded_all_heuristic")
            add(key, want, got, "PASS" if got == want else "FAIL",
                "/FontFile 流计数启发式（见 references/render-method.md）")
        else:
            add(key, want, None, "UNMEASURED", "渲染层不覆盖该项，需其他证据")

    n_fail = sum(1 for v in verdicts if v["verdict"] == "FAIL")
    summary = {"total": len(verdicts),
               "pass": sum(1 for v in verdicts if v["verdict"] == "PASS"),
               "fail": n_fail,
               "unmeasured": sum(1 for v in verdicts if v["verdict"] == "UNMEASURED")}
    json.dump({"spec": a.spec, "measurements": a.measurements, "tolerance_cm": a.tolerance,
               "summary": summary, "verdicts": verdicts},
              open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    lines = ["# 渲染裁决账本（render_verdict）", "",
             "测量对象：`%s`；容差 ±%s cm" % (a.measurements, a.tolerance), "",
             "PASS %d / FAIL %d / UNMEASURED %d" % (summary["pass"], n_fail, summary["unmeasured"]), "",
             "| 检查项 | 期望 | 实测 | 判定 | 证据 |", "|---|---|---|---|---|"]
    for v in verdicts:
        lines.append("| %s | %s | %s | %s | %s |" % (
            v["item"], v["expected"],
            json.dumps(v["measured"], ensure_ascii=False) if isinstance(v["measured"], (dict, list)) else v["measured"],
            v["verdict"], v["basis"]))
    open(a.md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("PASS %d FAIL %d UNMEASURED %d -> %s" % (summary["pass"], n_fail, summary["unmeasured"], a.json))
    sys.exit(1 if n_fail else 0)

if __name__ == "__main__":
    main()
