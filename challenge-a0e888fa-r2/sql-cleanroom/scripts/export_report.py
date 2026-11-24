#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_report.py —— 报告即聚合查询 + 导出 + 自检

职责：
  1. 解析 report_queries.sql：以 `-- @name: <名称>` 注释标记的每条 SELECT 为一个
     命名查询，全部执行并保存结果（报告即聚合查询，数字一律来自查询，禁止手写）。
  2. 导出交付文件到 --outdir：
       cleaned.csv     表 cleaned（ORDER BY line_no）
       change_log.csv  表 change_log（按写入顺序）
       issues.csv      表 issues（按写入顺序）
       quality_report.md  由命名查询结果渲染（含自检段）
       report_check.json  自检结果 + cleaned.csv 的 sha256
  3. 自检：report_queries.sql 中名为 selfcheck 的查询必须返回 (metric, value)
     两列；本脚本对已知指标用独立的重算 SQL 再算一遍并逐项比对。
     已知指标：raw_rows / cleaned_rows / issues_rows / change_log_rows /
     null_cells(cleaned 全列空值数) / duplicates_dropped（表存在时）。
     任一已知指标不一致 -> 退出码 5；selfcheck 缺失 -> 视为不一致（退出码 5）。

退出码：0 成功且自检通过；2 运行错误（缺表/查询失败）；5 自检不一致。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys

KNOWN_METRICS = ("raw_rows", "cleaned_rows", "issues_rows", "change_log_rows",
                 "null_cells", "duplicates_dropped")


def parse_named_queries(sql_text):
    """返回 [(name, sql)]，name 取自紧邻的 -- @name: 注释，可为 None。"""
    stmts, name, buf = [], None, ""
    for line in sql_text.splitlines(True):
        m = re.match(r"\s*--\s*@name:\s*([A-Za-z0-9_]+)\s*$", line)
        if m:
            body = "\n".join(ln for ln in buf.splitlines()
                             if ln.strip() and not ln.strip().startswith("--"))
            if not body.strip():  # 缓冲区内只有注释/空行：丢弃并标记下一条语句的名称
                buf = ""
                name = m.group(1)
                continue
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                body = "\n".join(ln for ln in buf.splitlines()
                                 if ln.strip() and not ln.strip().startswith("--"))
                if body.strip():
                    stmts.append((name, buf.strip()))
            buf, name = "", None
    if buf.strip():
        stmts.append((name, buf.strip()))
    return stmts


def scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone() is not None


def recompute_metric(conn, metric):
    """对已知指标用独立 SQL 重算；无法重算返回 None。"""
    if metric == "raw_rows":
        return scalar(conn, "SELECT COUNT(*) FROM raw") if table_exists(conn, "raw") else None
    if metric == "cleaned_rows":
        return scalar(conn, "SELECT COUNT(*) FROM cleaned") if table_exists(conn, "cleaned") else None
    if metric == "issues_rows":
        return scalar(conn, "SELECT COUNT(*) FROM issues") if table_exists(conn, "issues") else None
    if metric == "change_log_rows":
        return scalar(conn, "SELECT COUNT(*) FROM change_log") if table_exists(conn, "change_log") else None
    if metric == "duplicates_dropped":
        return scalar(conn, "SELECT COUNT(*) FROM duplicates_dropped") \
            if table_exists(conn, "duplicates_dropped") else None
    if metric == "null_cells":
        if not table_exists(conn, "cleaned"):
            return None
        cols = [r[1] for r in conn.execute("PRAGMA table_info(cleaned)").fetchall()]
        if not cols:
            return 0
        parts = ["(SELECT COUNT(*) FROM cleaned WHERE \"%s\" IS NULL)" % c.replace('"', '""')
                 for c in cols]
        return scalar(conn, "SELECT " + " + ".join(parts))
    return None


def export_table(conn, name, path, order_by):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(%s)" % name).fetchall()]
    rows = conn.execute("SELECT * FROM %s ORDER BY %s" % (name, order_by)).fetchall()
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for row in rows:
            w.writerow(["" if v is None else v for v in row])
    return len(rows)


def md_table(columns, rows):
    def esc(v):
        return "" if v is None else str(v).replace("|", "\\|")
    out = ["| " + " | ".join(esc(c) for c in columns) + " |",
           "|" + "|".join([" --- "] * len(columns)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(esc(v) for v in r) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="聚合查询 -> 质量报告 + 导出 + 自检")
    ap.add_argument("--db", required=True, help="case.db 路径")
    ap.add_argument("--queries", required=True, help="report_queries.sql 路径")
    ap.add_argument("--outdir", required=True, help="输出目录（不存在则创建）")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    conn = sqlite3.connect(args.db)
    try:
        for t in ("raw", "cleaned", "change_log", "issues"):
            if not table_exists(conn, t):
                print("export_report: 缺少必需表 %s（请先运行 run_steps.py）" % t, file=sys.stderr)
                return 2

        with open(args.queries, "r", encoding="utf-8") as f:
            named = parse_named_queries(f.read())

        results = {}   # name -> (columns, rows)
        try:
            for name, sql in named:
                cur = conn.execute(sql)
                if cur.description is None:
                    continue
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                if name:
                    results[name] = (cols, rows)
        except sqlite3.Error as e:
            print("export_report: 查询执行失败：%s" % e, file=sys.stderr)
            return 2

        # ---- 导出 ----
        n_cleaned = export_table(conn, "cleaned", os.path.join(args.outdir, "cleaned.csv"), "line_no")
        n_changes = export_table(conn, "change_log", os.path.join(args.outdir, "change_log.csv"), "rowid")
        n_issues = export_table(conn, "issues", os.path.join(args.outdir, "issues.csv"), "rowid")
        with open(os.path.join(args.outdir, "cleaned.csv"), "rb") as f:
            cleaned_sha256 = hashlib.sha256(f.read()).hexdigest()

        # ---- 自检 ----
        checks, all_match = [], True
        selfcheck = results.get("selfcheck")
        if selfcheck is None:
            all_match = False
            checks.append({"metric": "(selfcheck)", "report_value": None,
                           "recomputed": None, "status": "missing_selfcheck_query"})
        else:
            cols, rows = selfcheck
            try:
                mi, vi = cols.index("metric"), cols.index("value")
            except ValueError:
                print("export_report: selfcheck 查询必须返回 metric, value 两列", file=sys.stderr)
                return 2
            for row in rows:
                metric, report_value = str(row[mi]), row[vi]
                recomputed = recompute_metric(conn, metric)
                if metric not in KNOWN_METRICS or recomputed is None:
                    status = "unverified"  # 未知指标：无法独立重算，如实记录，不计入失败
                else:
                    try:
                        ok = int(report_value) == int(recomputed)
                    except (TypeError, ValueError):
                        ok = False
                    status = "match" if ok else "MISMATCH"
                    if not ok:
                        all_match = False
                checks.append({"metric": metric, "report_value": report_value,
                               "recomputed": recomputed, "status": status})

        # ---- 渲染 quality_report.md（数字全部来自上述查询结果）----
        lines = ["# 质量报告（报告即聚合查询）",
                 "",
                 "> 本报告全部由 report_queries.sql 的查询结果渲染；任何数字未手工填写。",
                 ""]
        for name, (cols, rows) in results.items():
            if name == "selfcheck":
                continue
            lines.append("## %s" % name)
            lines.append("")
            lines.append(md_table(cols, rows))
            lines.append("")
        lines.append("## 自检（报告数字 vs 对库表独立重算）")
        lines.append("")
        lines.append(md_table(["metric", "report_value", "recomputed", "status"],
                              [(c["metric"], c["report_value"], c["recomputed"], c["status"])
                               for c in checks]))
        lines.append("")
        lines.append("- cleaned.csv sha256：`%s`" % cleaned_sha256)
        lines.append("- 导出行数：cleaned=%d，change_log=%d，issues=%d" % (n_cleaned, n_changes, n_issues))
        lines.append("")
        with open(os.path.join(args.outdir, "quality_report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        check_doc = {
            "db": os.path.abspath(args.db),
            "queries_file": os.path.abspath(args.queries),
            "cleaned_sha256": cleaned_sha256,
            "exported": {"cleaned_rows": n_cleaned, "change_log_rows": n_changes,
                         "issues_rows": n_issues},
            "checks": checks,
            "all_match": all_match,
        }
        with open(os.path.join(args.outdir, "report_check.json"), "w", encoding="utf-8") as f:
            json.dump(check_doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
    finally:
        conn.close()

    if not all_match:
        print("export_report: 自检不一致（详见 report_check.json），退出码 5", file=sys.stderr)
        return 5
    print("export_report: OK 自检通过；cleaned.csv sha256=%s" % cleaned_sha256[:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
