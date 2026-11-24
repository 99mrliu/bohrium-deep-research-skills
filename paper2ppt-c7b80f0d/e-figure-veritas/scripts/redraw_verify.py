#!/usr/bin/env python3
"""redraw_verify.py — 重绘可核验：声明数值与机器可读来源逐一比对，容差 0。

比对 spec.json 中声明的 x.values 与每个 series.values，对 --data CSV 中
column 对应列做**逐值精确相等**（float 解析后 ==，容差 0）。任一漂移：
  - redraw_report.json 中记录 mismatched 明细（series/index/spec_value/source_value）
  - 退出码 1（门禁：mismatch > 0 即 error）
全部一致：退出码 0。

可选 --anchors evidence.json：若提供，额外记录其中声明的锚点数值是否都能在
CSV 中出现（仅记录，不改退出码）。

退出码：0 全部匹配；1 存在漂移；2 输入/模式错误。
"""
import argparse
import csv
import json
import os
import sys


def load_csv_columns(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cols = {}
    for name in (rows[0].keys() if rows else []):
        cols[name] = [float(r[name]) for r in rows]
    return cols


def compare_series(label, spec_values, source_values, mismatched, matched):
    if len(spec_values) != len(source_values):
        mismatched.append({
            "series": label, "index": None,
            "spec_value": f"len={len(spec_values)}",
            "source_value": f"len={len(source_values)}",
            "reason": "length mismatch",
        })
        return
    for i, (a, b) in enumerate(zip(spec_values, source_values)):
        fa, fb = float(a), float(b)
        if fa == fb:  # 容差 0：精确相等
            matched.append({"series": label, "index": i, "value": repr(fa)})
        else:
            mismatched.append({
                "series": label, "index": i,
                "spec_value": repr(fa), "source_value": repr(fb),
                "reason": "numeric drift (tolerance 0)",
            })


def main():
    ap = argparse.ArgumentParser(
        description="Verify redrawn-chart declared values against the source CSV (tolerance 0).")
    ap.add_argument("spec", help="spec.json used by chart_redraw.py")
    ap.add_argument("--data", required=True, help="source data.csv")
    ap.add_argument("--anchors", default=None, help="optional evidence.json")
    ap.add_argument("--report", default="redraw_report.json")
    args = ap.parse_args()

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read spec: {exc}\n")
        return 2
    if not os.path.isfile(args.data):
        sys.stderr.write(f"error: data CSV not found: {args.data}\n")
        return 2

    columns = load_csv_columns(args.data)
    matched, mismatched = [], []

    xcol = spec.get("x", {}).get("column")
    if xcol not in columns:
        sys.stderr.write(f"error: x column '{xcol}' not in CSV\n")
        return 2
    compare_series(f"x[{xcol}]", spec["x"]["values"], columns[xcol],
                   mismatched, matched)
    for s in spec.get("series", []):
        col = s.get("column")
        if col not in columns:
            mismatched.append({"series": s.get("name", col), "index": None,
                               "spec_value": "present", "source_value": "absent",
                               "reason": f"column '{col}' not in CSV"})
            continue
        compare_series(s["name"], s["values"], columns[col], mismatched, matched)

    anchor_notes = []
    if args.anchors:
        if os.path.isfile(args.anchors):
            with open(args.anchors, encoding="utf-8") as fh:
                anchors = json.load(fh)
            flat = sorted({v for col in columns.values() for v in col})
            for a in anchors.get("values", []):
                anchor_notes.append({"value": a,
                                     "found_in_csv": float(a) in flat})
        else:
            anchor_notes.append({"warning": f"anchors file not found: {args.anchors}"})

    report = {
        "spec": os.path.abspath(args.spec),
        "data": os.path.abspath(args.data),
        "generated_by": "redraw_verify.py",
        "tolerance": 0,
        "matched_count": len(matched),
        "mismatched_count": len(mismatched),
        "matched": matched,
        "mismatched": mismatched,
        "anchor_notes": anchor_notes,
        "verdict": "pass" if not mismatched else "error: numeric drift detected",
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(f"matched={len(matched)} mismatched={len(mismatched)} -> {args.report}")
    if mismatched:
        sys.stderr.write("error: numeric drift detected; redraw must be fixed "
                         "before the figure may enter the deck\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
