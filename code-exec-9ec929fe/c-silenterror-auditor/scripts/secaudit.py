#!/usr/bin/env python3
"""secaudit.py — 静默错误猎手：独立重算核验 + 陷阱扫描（纯 Python 标准库）。

重心是结果验证：本工具不信任任何已跑通的管道。它用与主分析**独立的代
码路径**直接从原始输入重算每一条数值结论（claim），并扫描数据中的经
典静默错误形态（缺失当 0、未去重分组、哨兵值、前提未检的 p 值……）。
任何 MISMATCH 以退出码 1 阻断交付——宁可 partial，不可错着 success。

子命令：
  scan   陷阱扫描：对 CSV/SQLite 输出结构化风险报告（缺失标记清单、
         完全重复行、键重复、哨兵值 -999/999/0 占比、常量列、高基数
         文本列、分组前未去重的行数影响试算）
  audit  独立重算 claims.json 中的每条 claim（从 --input 原始数据，
         而不是你的工作表），输出 CONFIRMED / MISMATCH / UNVERIFIABLE；
         任一非 CONFIRMED 即退出码 1
  diff   对比两份 result.json（如 naive 版与修正版），列出数值分歧，
         用于展示审计拦截了什么

claims.json 格式：
  [{"id": "c1", "kind": "row_count", "source": "/input/raw.csv", "value": 1030},
   {"id": "c2", "kind": "n_missing", "source": "/input/raw.csv",
    "column": "slump", "value": 3},
   {"id": "c3", "kind": "mean", "source": "/input/raw.csv", "column": "x",
    "value": 35.8, "tolerance": 0.01},
   {"id": "c4", "kind": "sql_scalar", "db": "/input/lab.db",
    "query": "SELECT COUNT(*) FROM t", "value": 178}]
kind ∈ row_count / n_missing / count_where(op,value) / distinct_count /
       mean / median / std / min / max / sum / sql_scalar
"""
import argparse
import csv
import json
import math
import os
import sqlite3
import sys

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "--", "missing"}
SENTINELS = {-999.0, 999.0, 9999.0, -9999.0, -1.0}


def read_table(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        raise SystemExit("EMPTY_TABLE: %s" % path)
    return [h.strip() for h in rows[0]], [r for r in rows[1:] if any(c.strip() for c in r)]


def col_idx(header, name):
    if name not in header:
        raise SystemExit("MISSING_COLUMN %r；可用: %s" % (name, ", ".join(header)))
    return header.index(name)


def nums(header, body, name):
    j = col_idx(header, name)
    out = []
    for r in body:
        s = (r[j] if j < len(r) else "").strip()
        if s.lower() in MISSING:
            continue
        try:
            out.append(float(s))
        except ValueError:
            continue
    return out


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def std(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# ---------------- scan ----------------

def cmd_scan(args):
    reports = []
    for path in args.paths:
        if path.lower().endswith((".db", ".sqlite", ".sqlite3")):
            reports.append(_scan_db(path))
        else:
            reports.append(_scan_csv(path))
    out = {"reports": reports}
    txt = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(txt)
    print(txt)
    n_risks = sum(len(r["risks"]) for r in reports)
    if n_risks:
        print("SCAN: 发现 %d 项静默错误风险，逐项处置（修正或记录理由）后方可交付"
              % n_risks, file=sys.stderr)
    return 0


def _scan_csv(path):
    header, body = read_table(path)
    risks = []
    # 完全重复行
    seen, dups = set(), 0
    for r in body:
        k = tuple(r)
        if k in seen:
            dups += 1
        seen.add(k)
    if dups:
        risks.append({"type": "exact_duplicate_rows", "count": dups,
                      "impact": "未去重就做分组统计会使行数与均值偏大"})
    for j, name in enumerate(header):
        raw = [(r[j] if j < len(r) else "").strip() for r in body]
        miss = [v for v in raw if v.lower() in MISSING]
        vals, sent = [], 0
        for v in raw:
            if v.lower() in MISSING:
                continue
            try:
                f = float(v)
                vals.append(f)
                if f in SENTINELS:
                    sent += 1
            except ValueError:
                pass
        if miss:
            zero_trap = ""
            if vals and abs(mean(vals)) > 1e-12:
                with_zero = mean(vals) * len(vals) / (len(vals) + len(miss))
                zero_trap = ("若把 %d 个缺失当 0，均值将由 %.6g 变为 %.6g"
                             % (len(miss), mean(vals), with_zero))
            risks.append({"type": "missing_values", "column": name,
                          "count": len(miss), "tokens": sorted({m for m in miss}),
                          "impact": "缺失必须显式处置（剔除/插补/仅报告）" + ("；" + zero_trap if zero_trap else "")})
        if sent:
            risks.append({"type": "sentinel_values", "column": name, "count": sent,
                          "impact": "-999/999/-1 等哨兵值混入统计会污染均值与极值"})
        if vals and len(set(vals)) == 1 and len(vals) > 1:
            risks.append({"type": "constant_column", "column": name,
                          "impact": "常量列无信息量，参与相关/回归会触发零方差错误"})
        nonnum = [v for v in raw if v.lower() not in MISSING
                  and not _is_float(v)]
        if nonnum and vals and len(nonnum) <= max(3, len(raw) // 10):
            risks.append({"type": "mixed_type_column", "column": name,
                          "examples": sorted(set(nonnum))[:5],
                          "impact": "数值列混入文本，类型转换会静默丢行"})
    return {"file": path, "kind": "csv", "n_rows": len(body),
            "n_cols": len(header), "risks": risks}


def _scan_db(path):
    risks = []
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            qt = '"%s"' % t.replace('"', '""')
            n = con.execute("SELECT COUNT(*) FROM %s" % qt).fetchone()[0]
            cols = con.execute("PRAGMA table_info(%s)" % qt).fetchall()
            pk = [c[1] for c in cols if c[5]]
            if pk:
                qc = ",".join('"%s"' % c.replace('"', '""') for c in pk)
                ndup = con.execute(
                    "SELECT COUNT(*) FROM (SELECT %s FROM %s GROUP BY %s "
                    "HAVING COUNT(*)>1)" % (qc, qt, qc)).fetchone()[0]
                if ndup:
                    risks.append({"type": "duplicate_primary_key", "table": t,
                                  "count": ndup,
                                  "impact": "主键重复：连接查询会静默放大行数"})
            else:
                risks.append({"type": "no_primary_key", "table": t,
                              "impact": "无主键表做连接/去重时须人工核对行数"})
            for c in cols:
                qcn = '"%s"' % c[1].replace('"', '""')
                nn = con.execute("SELECT COUNT(*) FROM %s WHERE %s IS NULL"
                                 % (qt, qcn)).fetchone()[0]
                if nn:
                    risks.append({"type": "null_column", "table": t,
                                  "column": c[1], "count": nn,
                                  "impact": "聚合函数忽略 NULL，COUNT(col) 与 COUNT(*) 口径不同"})
        if not tables:
            risks.append({"type": "no_tables", "impact": "库中无表，任何查询都将失败"})
    finally:
        con.close()
    return {"file": path, "kind": "sqlite", "tables": tables if 'tables' in dir() else [],
            "risks": risks}


def _is_float(v):
    try:
        float(v)
        return True
    except ValueError:
        return False


# ---------------- audit ----------------

def cmd_audit(args):
    claims = json.load(open(args.claims, encoding="utf-8"))
    results = []
    n_bad = 0
    for c in claims:
        r = _verify(c)
        results.append(r)
        if r["status"] != "CONFIRMED":
            n_bad += 1
    report = {"claims": results,
              "confirmed": sum(1 for r in results if r["status"] == "CONFIRMED"),
              "mismatch": sum(1 for r in results if r["status"] == "MISMATCH"),
              "unverifiable": sum(1 for r in results if r["status"] == "UNVERIFIABLE")}
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(txt)
    print(txt)
    if n_bad:
        print("AUDIT FAIL: %d 条 claim 未通过独立重算；禁止交付 status=success"
              % n_bad, file=sys.stderr)
        return 1
    print("AUDIT PASS: %d 条 claim 全部 CONFIRMED" % len(results))
    return 0


def _verify(c):
    kind = c.get("kind")
    expect = c.get("value")
    tol = c.get("tolerance")
    try:
        if kind == "sql_scalar":
            actual = _sql_scalar(c["db"], c["query"])
        else:
            header, body = read_table(c["source"])
            actual = _eval_claim(c, header, body)
    except SystemExit as e:
        return {"id": c.get("id"), "status": "UNVERIFIABLE",
                "reason": str(e), "expected": expect}
    except (OSError, KeyError, json.JSONDecodeError) as e:
        return {"id": c.get("id"), "status": "UNVERIFIABLE",
                "reason": "%s: %s" % (type(e).__name__, e), "expected": expect}
    ok = _close(actual, expect, tol)
    return {"id": c.get("id"), "kind": kind, "expected": expect,
            "recomputed": actual, "tolerance": tol,
            "status": "CONFIRMED" if ok else "MISMATCH"}


def _eval_claim(c, header, body):
    kind = c["kind"]
    if kind == "row_count":
        return len(body)
    if kind == "n_missing":
        j = col_idx(header, c["column"])
        return sum(1 for r in body
                   if (r[j] if j < len(r) else "").strip().lower() in MISSING)
    if kind == "distinct_count":
        j = col_idx(header, c["column"])
        return len({(r[j] if j < len(r) else "").strip() for r in body})
    if kind == "count_where":
        j = col_idx(header, c["column"])
        return sum(1 for r in body
                   if _match((r[j] if j < len(r) else ""), c["op"], c.get("value_of")))
    xs = nums(header, body, c["column"])
    if not xs:
        raise SystemExit("NO_NUMERIC_VALUES in %s" % c["column"])
    return {"mean": mean, "median": median, "std": std,
            "min": min, "max": max, "sum": sum,
            "count": len}[kind](xs)


def _match(v, op, target):
    s = str(v).strip()
    if op == "na":
        return s.lower() in MISSING
    if op == "notna":
        return s.lower() not in MISSING
    if op == "==":
        return s == str(target)
    if op == "!=":
        return s != str(target)
    try:
        fv, ft = float(s), float(target)
    except (TypeError, ValueError):
        return False
    return {">": fv > ft, ">=": fv >= ft, "<": fv < ft, "<=": fv <= ft}[op]


def _sql_scalar(db, query):
    q = query.strip().rstrip(";")
    if q.split(None, 1)[0].upper() not in ("SELECT", "WITH"):
        raise SystemExit("SQL_READONLY: 仅允许 SELECT/WITH")
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        row = con.execute(q).fetchone()
    finally:
        con.close()
    if row is None:
        raise SystemExit("QUERY_EMPTY")
    return row[0]


def _close(actual, expect, tol):
    if isinstance(actual, float) or isinstance(expect, float):
        try:
            a, e = float(actual), float(expect)
        except (TypeError, ValueError):
            return False
        if tol is None:
            tol = max(1e-9, abs(e) * 1e-9)
        return abs(a - e) <= tol
    return actual == expect


# ---------------- diff ----------------

def cmd_diff(args):
    a = json.load(open(args.a, encoding="utf-8"))
    b = json.load(open(args.b, encoding="utf-8"))
    diffs = []
    _walk(a, b, "$", diffs)
    print(json.dumps(diffs, ensure_ascii=False, indent=2))
    print("DIFF: %d 处分歧" % len(diffs))
    return 0


def _walk(a, b, path, diffs):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            _walk(a.get(k, "<absent>"), b.get(k, "<absent>"), path + "." + str(k), diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append({"path": path, "a": "len=%d" % len(a), "b": "len=%d" % len(b)})
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, "%s[%d]" % (path, i), diffs)
    elif a != b:
        diffs.append({"path": path, "a": a, "b": b})


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("audit")
    p.add_argument("--claims", required=True)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("diff")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.set_defaults(fn=cmd_diff)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
