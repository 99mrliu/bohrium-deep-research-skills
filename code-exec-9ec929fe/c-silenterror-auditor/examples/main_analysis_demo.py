#!/usr/bin/env python3
"""main_analysis_demo.py — 合成示例中扮演"主分析管道"（被审计对象）。
读取 readings.csv，去重、剔除缺失与哨兵值，输出 clean.csv 与统计。
同时输出一份 result_fixed.json；naive 版由 run_example.sh 内联生成。
仅用于 examples/ 演示。纯标准库。"""
import csv
import json
import math
import os
import sys

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--"}
SENTINELS = {-999.0, 999.0, 9999.0, -9999.0}


def main(case_dir, work, out):
    rows = list(csv.DictReader(open(os.path.join(case_dir, "readings.csv"),
                                    encoding="utf-8")))
    seen, body = set(), []
    for r in rows:
        k = tuple(sorted(r.items()))
        if k not in seen:
            seen.add(k)
            body.append(r)
    vals, kept = [], []
    for r in body:
        v = r["reading"].strip()
        if v.lower() in MISSING:
            continue
        f = float(v)
        if f in SENTINELS:
            continue
        vals.append(f)
        kept.append(r)
    clean_path = os.path.join(work, "clean.csv")
    with open(clean_path, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(kept)
    n = len(vals)
    m = sum(vals) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in vals) / (n - 1))
    result = {"case_id": "synthetic-demo-secaudit-001", "status": "success",
              "cleaned_table": clean_path,
              "summary_statistics": {"column": "reading", "n": n,
                                     "mean": round(m, 4), "std": round(sd, 4),
                                     "min": min(vals), "max": max(vals)},
              "anomalies": ["NA 缺失 1 行剔除", "-999 哨兵值 1 行剔除",
                            "完全重复行 1 行剔除",
                            "lab.db 无主键且 reading 含 NULL：仅用于演示 scan，未参与统计"],
              "provenance": {"demo": "SYNTHETIC EXAMPLE: 合成数据，非正式案例结果"}}
    json.dump(result, open(os.path.join(out, "result_fixed.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)
    print("main analysis: n=%d mean=%.4f std=%.4f" % (n, m, sd))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
