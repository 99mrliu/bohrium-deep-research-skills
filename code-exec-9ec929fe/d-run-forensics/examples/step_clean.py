#!/usr/bin/env python3
"""合成示例管道第 1 步：清洗 signals.csv -> work/clean.csv。纯标准库。"""
import csv
import sys

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--"}

src, dst = sys.argv[1], sys.argv[2]
rows = list(csv.reader(open(src, encoding="utf-8")))
header, body = rows[0], rows[1:]
seen, out = set(), []
for r in body:
    if (r[2].strip().lower() if len(r) > 2 else "") in MISSING:
        continue
    k = tuple(r)
    if k in seen:
        continue
    seen.add(k)
    out.append(r)
with open(dst, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(out)
print("clean: %d -> %d rows" % (len(body), len(out)))
