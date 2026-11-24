#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_stats.py — 独立统计复核器（上游数据真实性方向）。

与 run_case.py 不同的第二套实现：Welford 在线算法求均值/方差，
线性插值分位数独立重算，Pearson 相关用另一种累加顺序复算。
逐字段比对 statistics.json，容差 1e-6（相对），输出 verification_report.json。

用法：
    python3 verify_stats.py --source <csv/tsv/sqlite> \
        --stats /app/output/statistics.json \
        --out /app/output/verification_report.json
"""
import argparse
import csv
import json
import math
import os
import sqlite3
import sys

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "?", "missing"}


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def try_float(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def load_source(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".sqlite", ".db", ".sqlite3"):
        con = sqlite3.connect(path)
        try:
            table = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")][0]
            cur = con.execute('SELECT * FROM "%s"' % table.replace('"', '""'))
            cols = [d[0] for d in cur.description]
            rows = [["" if v is None else str(v) for v in row]
                    for row in cur.fetchall()]
            return cols, rows
        finally:
            con.close()
    text = read_text(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if "\t" in text.split("\n", 1)[0] else ","
    rows = [r for r in csv.reader(text.splitlines(), delimiter=delim) if r]
    return [c.strip() for c in rows[0]], rows[1:]


def welford(vals):
    """One-pass Welford: returns (n, mean, M2)."""
    n, mean, m2 = 0, 0.0, 0.0
    for x in vals:
        n += 1
        delta = x - mean
        mean += delta / n
        m2 += delta * (x - mean)
    return n, mean, m2


def quantile_type7(sorted_vals, p):
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * p
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.stats, encoding="utf-8") as fh:
        stats_doc = json.load(fh)
    cols, rows = load_source(args.source)
    idx = {c: j for j, c in enumerate(cols)}

    report = {"source": os.path.abspath(args.source),
              "method": "independent second implementation (Welford one-pass "
                        "variance, type-7 quantiles, re-accumulated Pearson)",
              "tolerance_rel": 1e-6, "checks": [], "n_pass": 0, "n_fail": 0}

    def close(a, b):
        if a is None or b is None:
            return a == b
        return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))

    def record(name, ok, recomputed, reported):
        report["checks"].append({"check": name, "passed": bool(ok),
                                 "recomputed": recomputed,
                                 "reported": reported})
        report["n_pass" if ok else "n_fail"] += 1

    desc = stats_doc.get("descriptive", {})
    col_vals = {}
    for c in cols:
        vals = []
        for r in rows:
            cell = r[idx[c]] if idx[c] < len(r) else ""
            if str(cell).strip().lower() in MISSING_TOKENS:
                continue
            f = try_float(cell)
            if f is not None:
                vals.append(f)
        col_vals[c] = vals

    for c, st in desc.items():
        if c not in idx:
            record("column_present:%s" % c, False, "missing", "present")
            continue
        vals = col_vals[c]
        n, mean, m2 = welford(vals)
        sd = math.sqrt(m2 / (n - 1)) if n > 1 else 0.0
        sv = sorted(vals)
        record("n:%s" % c, n == st["n"], n, st["n"])
        record("mean:%s" % c, close(mean, st["mean"]), mean, st["mean"])
        record("sd:%s" % c, close(sd, st["sd"]), sd, st["sd"])
        record("sem:%s" % c, close(sd / math.sqrt(n) if n else 0.0,
                                   st["sem"]), sd / math.sqrt(n) if n else 0.0,
               st["sem"])
        record("median:%s" % c, close(quantile_type7(sv, 0.5), st["median"]),
               quantile_type7(sv, 0.5), st["median"])
        record("q1:%s" % c, close(quantile_type7(sv, 0.25), st["q1"]),
               quantile_type7(sv, 0.25), st["q1"])
        record("q3:%s" % c, close(quantile_type7(sv, 0.75), st["q3"]),
               quantile_type7(sv, 0.75), st["q3"])
        record("min:%s" % c, close(sv[0] if sv else None, st["min"]),
               sv[0] if sv else None, st["min"])
        record("max:%s" % c, close(sv[-1] if sv else None, st["max"]),
               sv[-1] if sv else None, st["max"])

    for ent in stats_doc.get("correlations", []):
        x, y = col_vals.get(ent["x"]), col_vals.get(ent["y"])
        if x is None or y is None:
            continue
        # align by pairwise completeness using original rows
        pairs = []
        for r in rows:
            cx = r[idx[ent["x"]]] if idx[ent["x"]] < len(r) else ""
            cy = r[idx[ent["y"]]] if idx[ent["y"]] < len(r) else ""
            fx, fy = try_float(cx), try_float(cy)
            if fx is not None and fy is not None:
                pairs.append((fx, fy))
        n = len(pairs)
        if n < 3:
            continue
        mx = sum(p[0] for p in pairs) / n
        my = sum(p[1] for p in pairs) / n
        sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
        sxx = sum((p[0] - mx) ** 2 for p in pairs)
        syy = sum((p[1] - my) ** 2 for p in pairs)
        r_re = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None
        record("pearson:%s~%s" % (ent["x"], ent["y"]),
               close(r_re, ent["pearson_r"]), r_re, ent["pearson_r"])
        record("pearson_n:%s~%s" % (ent["x"], ent["y"]), n == ent["n"],
               n, ent["n"])

    # group sizes
    grp = stats_doc.get("group", {})
    if grp.get("column") and grp["column"] in idx and grp.get("n_per_level"):
        counts = {}
        for r in rows:
            v = r[idx[grp["column"]]] if idx[grp["column"]] < len(r) else ""
            f = try_float(v)
            key = (str(int(f)) if f is not None and float(f).is_integer()
                   else str(v).strip())
            if key and key.lower() not in MISSING_TOKENS:
                counts[key] = counts.get(key, 0) + 1
        for lev, n_rep in grp["n_per_level"].items():
            record("group_n:%s=%s" % (grp["column"], lev),
                   counts.get(lev) == n_rep, counts.get(lev), n_rep)

    report["all_passed"] = report["n_fail"] == 0
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"all_passed": report["all_passed"],
                      "n_pass": report["n_pass"],
                      "n_fail": report["n_fail"]}, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
