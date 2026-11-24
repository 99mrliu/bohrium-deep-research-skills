#!/usr/bin/env python3
"""合成示例管道第 2 步：amplitude 的 count/mean/std。纯标准库。"""
import csv
import json
import math
import sys

src, dst = sys.argv[1], sys.argv[2]
vals = [float(r["amplitude"]) for r in csv.DictReader(open(src, encoding="utf-8"))]
n = len(vals)
m = sum(vals) / n
sd = math.sqrt(sum((x - m) ** 2 for x in vals) / (n - 1))
json.dump({"n": n, "mean": round(m, 4), "std": round(sd, 4),
           "min": min(vals), "max": max(vals)},
          open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("stats: n=%d mean=%.4f std=%.4f" % (n, m, sd))
