#!/usr/bin/env python3
"""atlas.py — 类型化比较图谱与可计算空白分析。

把纳入文献规范化成类型化记录（JSONL），先做完整性校验，再做三件
确定性计算：
  1. 切面覆盖矩阵：两个 facet（默认 task × method_family）交叉，
     填出哪些格子有文献、哪些是输入文献集内的空白；
  2. 指标覆盖分析：同一 comparability_class 内，哪些记录缺报了
     该类文献常用的指标（可比性缺口）；
  3. 不可比对判定：同 task 但指标集不相交的记录对，输出
     "无法直接比较"及原因。
空白结论只陈述"输入文献集内未见"，不做全局新颖性断言。

子命令：
  validate  校验记录文件（模式、枚举、重复键），违例退出码 1
  gap       先内嵌校验，再输出 atlas_report.json / atlas_report.md

记录字段见 references/schema.md。仅依赖 Python 3 标准库。
"""
import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

VENUE_KINDS = {"journal", "conference", "preprint", "report"}
REQUIRED = ["record_id", "title", "year", "venue_kind", "task",
            "method_family", "data_domain", "metrics",
            "headline_result", "limitations", "comparability_class"]


def load_records(path):
    records = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"记录文件读取失败: {exc}", file=sys.stderr)
        sys.exit(1)
    for i, ln in enumerate(lines, 1):
        if ln.strip():
            try:
                records.append((i, json.loads(ln)))
            except json.JSONDecodeError as exc:
                print(f"第 {i} 行不是合法 JSON: {exc}", file=sys.stderr)
                sys.exit(1)
    return records


def validate_records(records):
    errors, warnings = [], []
    seen_ids, seen_keys = set(), {}
    for i, r in records:
        rid = r.get("record_id", f"<第{i}行>")
        for f in REQUIRED:
            if f not in r:
                errors.append(f"{rid}: 缺字段 {f}")
        if r.get("record_id") in seen_ids:
            errors.append(f"{rid}: record_id 重复")
        seen_ids.add(r.get("record_id"))
        y = r.get("year")
        if not isinstance(y, int) or not 1900 <= y <= 2100:
            errors.append(f"{rid}: year 非法 {y!r}")
        if r.get("venue_kind") not in VENUE_KINDS:
            errors.append(f"{rid}: venue_kind 非法 {r.get('venue_kind')!r}")
        m = r.get("metrics")
        if not isinstance(m, list) or not m or \
                not all(isinstance(x, str) and x.strip() for x in m):
            errors.append(f"{rid}: metrics 必须是非空字符串数组")
        key = (r.get("task"), r.get("method_family"),
               r.get("data_domain"))
        if all(key):
            if key in seen_keys:
                warnings.append(
                    f"{rid} 与 {seen_keys[key]} 的 "
                    f"(task, method_family, data_domain) 完全相同；"
                    f"若是独立研究请忽略，若是重复登记请合并")
            seen_keys[key] = rid
    return errors, warnings


def cmd_validate(args):
    records = load_records(args.records)
    errors, warnings = validate_records(records)
    print(json.dumps({"ok": not errors, "errors": errors,
                      "warnings": warnings}, ensure_ascii=False, indent=2))
    if errors:
        sys.exit(1)


def cmd_gap(args):
    raw = load_records(args.records)
    errors, warnings = validate_records(raw)
    if errors:
        print(json.dumps({"ok": False, "errors": errors},
                         ensure_ascii=False, indent=2))
        print("记录未通过校验，先修复再做空白分析", file=sys.stderr)
        sys.exit(1)
    records = [r for _, r in raw]
    f1, f2 = (args.facets.split(",") + ["method_family"])[:2]

    # 1) 切面覆盖矩阵
    rows = sorted({r[f1] for r in records})
    cols = sorted({r[f2] for r in records})
    cells, empty_cells = {}, []
    for a in rows:
        for b in cols:
            ids = [r["record_id"] for r in records
                   if r[f1] == a and r[f2] == b]
            cells[f"{a} × {b}"] = ids
            if not ids:
                empty_cells.append({f1: a, f2: b})

    # 2) 指标覆盖分析（按 comparability_class）
    by_class = {}
    for r in records:
        by_class.setdefault(r["comparability_class"], []).append(r)
    metric_gaps = []
    for cls, members in sorted(by_class.items()):
        union = sorted({m for r in members for m in r["metrics"]})
        for r in members:
            missing = [m for m in union if m not in r["metrics"]]
            if missing:
                metric_gaps.append({"class": cls,
                                    "record_id": r["record_id"],
                                    "missing_metrics": missing,
                                    "class_metric_union": union})

    # 3) 不可比对判定（同 task、指标集不相交）
    incomparable = []
    for a, b in combinations(sorted(records,
                                    key=lambda r: r["record_id"]), 2):
        if a["task"] != b["task"]:
            continue
        sa, sb = set(a["metrics"]), set(b["metrics"])
        if sa.isdisjoint(sb):
            incomparable.append({
                "pair": [a["record_id"], b["record_id"]],
                "reason": f"同一任务（{a['task']}）但指标集不相交："
                          f"{sorted(sa)} vs {sorted(sb)}；"
                          f"结论不能直接比较，只能分别陈述"})

    report = {
        "note": "比较图谱报告（机器生成）；空白=输入文献集内空白，"
                "不做全局新颖性断言",
        "records": len(records), "facets": [f1, f2],
        "coverage_matrix": cells,
        "empty_cells": empty_cells,
        "metric_gaps": metric_gaps,
        "incomparable_pairs": incomparable,
        "validation_warnings": warnings,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "atlas_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    md = ["# 比较图谱报告（机器生成）", "",
          f"记录数：{len(records)}；切面：{f1} × {f2}", "",
          "## 切面覆盖矩阵", "",
          "| %s \\ %s | %s |" % (f1, f2, " | ".join(cols)),
          "|" + "-|" * (len(cols) + 1)]
    for a in rows:
        md.append("| **%s** | %s |"
                  % (a, " | ".join(
                      ", ".join(cells[f"{a} × {b}"]) or "**空**"
                      for b in cols)))
    md += ["", "## 空白格（候选研究空白）", ""]
    if empty_cells:
        md += ["- `%s=%s` × `%s=%s`：输入文献集内未见（非全局空白）"
               % (f1, c[f1], f2, c[f2]) for c in empty_cells]
    else:
        md.append("（无空白格）")
    md += ["", "## 指标覆盖缺口", ""]
    if metric_gaps:
        md += ["- `%s`（类 %s）缺报指标：%s"
               % (g["record_id"], g["class"],
                  "、".join(g["missing_metrics"]))
               for g in metric_gaps]
    else:
        md.append("（各类内指标覆盖完整）")
    md += ["", "## 无法直接比较的记录对", ""]
    if incomparable:
        md += ["- `%s` vs `%s`：%s"
               % (p["pair"][0], p["pair"][1], p["reason"])
               for p in incomparable]
    else:
        md.append("（无）")
    md += ["", "口径：以上空白与缺口均只在输入文献集内成立；"
           "写入综述时必须携带该边界。"]
    (out / "atlas_report.md").write_text("\n".join(md) + "\n",
                                         encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out),
                      "empty_cells": len(empty_cells),
                      "metric_gaps": len(metric_gaps),
                      "incomparable_pairs": len(incomparable)},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate")
    p.add_argument("--records", required=True)
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("gap")
    p.add_argument("--records", required=True)
    p.add_argument("--facets", default="task,method_family",
                   help="两个 facet 字段名，逗号分隔")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_gap)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
