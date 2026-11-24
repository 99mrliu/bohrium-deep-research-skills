#!/usr/bin/env python3
"""fill_demo.py — 合成示例中扮演 Agent 角色：读取 semalign 工件，完成真实
计算并填充 result.json 骨架。仅用于 examples/ 演示，非 Skill 正式组件。
纯标准库。"""
import csv
import json
import os
import sys

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--"}


def main(case_dir, work, output):
    profile = json.load(open(os.path.join(work, "profile.json"), encoding="utf-8"))
    csv_path = os.path.join(case_dir, "measurements.csv")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    n_raw = len(rows)
    seen, body = set(), []
    n_dup = 0
    for r in rows:
        key = tuple(sorted(r.items()))
        if key in seen:
            n_dup += 1
            continue
        seen.add(key)
        body.append(r)
    n_dedup = len(body)
    vals, n_missing_rows = [], 0
    for r in body:
        v = (r.get("Value (a.u.)") or "").strip().lower()
        if v in MISSING:
            n_missing_rows += 1
            continue
        vals.append(float(v))
    n_used = len(vals)
    mean = sum(vals) / n_used
    var = sum((x - mean) ** 2 for x in vals) / (n_used - 1)
    cleaned_path = os.path.join(output, "cleaned_measurements.csv")
    with open(cleaned_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(body)

    result = json.load(open(os.path.join(output, "result.json"), encoding="utf-8"))
    mapping = json.load(open(os.path.join(work, "field_mapping.json"), encoding="utf-8"))
    fuzzy = [m for m in mapping["mapping"] if m.get("needs_human_confirm")]
    result.update({
        "status": "success",
        "cleaned_table": cleaned_path,
        "summary_statistics": {
            "column": "Value (a.u.)", "n": n_used, "mean": round(mean, 4),
            "std": round(var ** 0.5, 4), "min": min(vals), "max": max(vals)},
        "row_reconciliation": {
            "raw_rows": n_raw, "after_dedup": n_dedup,
            "rows_with_missing_value": n_missing_rows, "rows_used_in_stats": n_used},
        "figures": [],
        "anomalies": result.get("anomalies", []) + [
            {"issue": "1 行完全重复 (S05)，已按任务要求删除", "action": "drop_exact"},
            {"issue": "2 行 value 缺失 (S03='NA', S08='--')，未参与统计、未插补",
             "action": "exclude_from_stats"},
        ] + [
            {"issue": "字段对齐需人工确认: %s -> %s (score=%s)"
                      % (m["dictionary_field"], m.get("column"), m.get("score")),
             "decision": "依据数据字典单位与 profile 数值范围采纳",
             "confidence": "medium"} for m in fuzzy
        ],
    })
    result["provenance"]["demo"] = ("SYNTHETIC EXAMPLE: 合成数据，fill_demo.py 真实计算，"
                                    "非正式案例结果")
    json.dump(result, open(os.path.join(output, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("filled: n_used=%d mean=%.4f" % (n_used, mean))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
