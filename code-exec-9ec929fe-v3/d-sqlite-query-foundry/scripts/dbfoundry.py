#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dbfoundry：SQLite 查询铸造厂。

子命令：
  survey     数据库建档：结构、行数、列画像、潜在连接键（扇出风险）。
  exec       以只读方式逐条执行 .sql 文件，捕获 EXPLAIN QUERY PLAN，
             写结果快照 CSV 并对行数做基线对账，元数据落盘。
  reconcile  以独立改写的 SQL 复核关键行数与聚合，裁定 PASS/FAIL。

仅使用 Python 3.9+ 标准库，无网络访问。
一切错误信息以 [dbfoundry] 前缀写入 stderr。
"""

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_SAMPLE_VALUES = 5
NUMERIC_TYPE_RE = re.compile(r"INT|REAL|FLOA|DOUB|NUM|DEC", re.IGNORECASE)
# 启发式表名提取：FROM/JOIN 后的裸标识符。无法识别子查询别名展开与
# CTE（会把 CTE 名当作表名，随后 COUNT 失败并如实记录 error），见 SKILL.md 局限性。
TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN)\s+[\"`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
JOIN_RE = re.compile(r"\bJOIN\b", re.IGNORECASE)
LINE_COMMENT_RE = re.compile(r"--[^\n]*")


def eprint(msg):
    print("[dbfoundry] " + str(msg), file=sys.stderr)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def base_meta(db_path):
    return {
        "db_path": str(db_path),
        "db_sha256": sha256_file(db_path),
        "sqlite_version": sqlite3.sqlite_version,
        "generated_utc": utc_now(),
    }


def open_ro(db_path):
    p = Path(db_path)
    if not p.is_file():
        eprint("数据库文件不存在：%s" % db_path)
        sys.exit(2)
    try:
        conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        eprint("以只读方式打开数据库失败：%s" % exc)
        sys.exit(2)
    return conn


def json_safe(value):
    if isinstance(value, bytes):
        return "<blob %d bytes>" % len(value)
    return value


def write_json(path, obj):
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def quote_ident(name):
    return '"%s"' % name.replace('"', '""')


# ---------------------------------------------------------------- survey


def profile_column(conn, table, col):
    qtbl = quote_ident(table)
    qcol = quote_ident(col["name"])
    col["null_count"] = conn.execute(
        "SELECT COUNT(*) FROM %s WHERE %s IS NULL" % (qtbl, qcol)
    ).fetchone()[0]
    col["distinct_count"] = conn.execute(
        "SELECT COUNT(DISTINCT %s) FROM %s" % (qcol, qtbl)
    ).fetchone()[0]
    if NUMERIC_TYPE_RE.search(col["type"] or ""):
        mn, mx = conn.execute(
            "SELECT MIN(%s), MAX(%s) FROM %s" % (qcol, qcol, qtbl)
        ).fetchone()
        col["min"] = json_safe(mn)
        col["max"] = json_safe(mx)
    else:
        rows = conn.execute(
            "SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL LIMIT %d"
            % (qcol, qtbl, qcol, MAX_SAMPLE_VALUES)
        ).fetchall()
        col["sample_values"] = [json_safe(r[0]) for r in rows]


def render_survey_md(survey):
    lines = []
    add = lines.append
    add("# 数据库建档（survey）")
    add("")
    add("- 数据库：`%s`" % survey["db_path"])
    add("- 文件 sha256：`%s`" % survey["db_sha256"])
    add("- SQLite 版本：%s" % survey["sqlite_version"])
    add("- 建档时间（UTC）：%s" % survey["generated_utc"])
    add("")
    add("## 对象清单")
    add("")
    add("| 名称 | 类型 | 行数 |")
    add("| --- | --- | --- |")
    for obj in survey["objects"]:
        add("| `%s` | %s | %s |" % (obj["name"], obj["type"], obj.get("row_count")))
    for obj in survey["objects"]:
        kind = "表" if obj["type"] == "table" else "视图"
        add("")
        add("## %s `%s`（行数：%s）" % (kind, obj["name"], obj.get("row_count")))
        add("")
        add("| 列 | 类型 | 主键 | NOT NULL | NULL 行数 | 去重计数 | 最小值 | 最大值 | 样例值 |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for col in obj["columns"]:
            samples = "、".join(repr(v) for v in col.get("sample_values", []))
            add("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                col["name"],
                col["type"] or "—",
                "是" if col["pk"] else "否",
                "是" if col["notnull"] else "否",
                col.get("null_count", "—"),
                col.get("distinct_count", "—"),
                col.get("min", "—"),
                col.get("max", "—"),
                samples or "—",
            ))
        if obj.get("row_count_error"):
            add("")
            add("> 行数统计失败：%s" % obj["row_count_error"])
    add("")
    add("## 潜在连接键（跨表同名列，扇出风险提示）")
    add("")
    if survey["shared_columns"]:
        add("| 列名 | 同时出现的表 |")
        add("| --- | --- |")
        for cname, tables in survey["shared_columns"].items():
            add("| `%s` | %s |" % (cname, "、".join("`%s`" % t for t in tables)))
        add("")
        add("> 提示：以上同名列可能被用作 JOIN 条件。若连接基数非一对一，"
            "结果行数会被放大（扇出），须以 exec 的基线对账核实。")
    else:
        add("未发现跨表同名列。")
    return "\n".join(lines) + "\n"


def cmd_survey(args):
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    conn = open_ro(args.db)
    survey = base_meta(args.db)
    objects = conn.execute(
        "SELECT name, type FROM sqlite_master "
        "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    ).fetchall()
    survey["objects"] = []
    column_to_tables = {}
    for obj_name, obj_type in objects:
        entry = {"name": obj_name, "type": obj_type, "columns": []}
        try:
            entry["row_count"] = conn.execute(
                "SELECT COUNT(*) FROM %s" % quote_ident(obj_name)
            ).fetchone()[0]
        except sqlite3.Error as exc:
            entry["row_count"] = None
            entry["row_count_error"] = str(exc)
        info = conn.execute(
            "PRAGMA table_info(%s)" % quote_ident(obj_name)
        ).fetchall()
        for _cid, cname, ctype, notnull, _dflt, pk in info:
            col = {"name": cname, "type": ctype or "",
                   "notnull": bool(notnull), "pk": bool(pk)}
            try:
                profile_column(conn, obj_name, col)
            except sqlite3.Error as exc:
                col["profile_error"] = str(exc)
            entry["columns"].append(col)
            column_to_tables.setdefault(cname, [])
            if obj_name not in column_to_tables[cname]:
                column_to_tables[cname].append(obj_name)
        survey["objects"].append(entry)
    survey["shared_columns"] = {
        c: ts for c, ts in sorted(column_to_tables.items()) if len(ts) > 1
    }
    conn.close()
    write_json(work / "survey.json", survey)
    (work / "survey.md").write_text(render_survey_md(survey), encoding="utf-8")
    print(json.dumps({
        "survey_json": str(work / "survey.json"),
        "survey_md": str(work / "survey.md"),
        "objects": len(survey["objects"]),
    }, ensure_ascii=False))
    sys.exit(0)


# ---------------------------------------------------------------- exec


def split_statements(text):
    """朴素地按分号切分语句（已知限制：不识别字符串字面量内的分号与块注释）。"""
    statements = []
    for chunk in text.split(";"):
        if LINE_COMMENT_RE.sub("", chunk).strip():
            statements.append(chunk.strip())
    return statements


def cmd_exec(args):
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        sql_text = Path(args.sql).read_text(encoding="utf-8")
    except OSError as exc:
        eprint("读取 SQL 文件失败：%s" % exc)
        sys.exit(2)
    statements = split_statements(sql_text)
    if not statements:
        eprint("SQL 文件中没有可执行语句：%s" % args.sql)
        sys.exit(2)
    conn = open_ro(args.db)
    common = base_meta(args.db)
    common["sql_file"] = str(args.sql)
    common["tag"] = args.tag
    common["max_rows"] = args.max_rows
    common["timeout_seconds"] = args.timeout
    for index, stmt in enumerate(statements, 1):
        meta = dict(common)
        meta["statement_index"] = index
        meta["sql"] = stmt
        meta_path = outdir / ("%s_%d.meta.json" % (args.tag, index))
        csv_path = outdir / ("%s_%d.csv" % (args.tag, index))
        # 1) 先取查询计划（计划失败即视为语句错误，记录并停止）。
        try:
            plan_rows = conn.execute("EXPLAIN QUERY PLAN " + stmt).fetchall()
            meta["query_plan"] = [" | ".join(str(x) for x in row) for row in plan_rows]
        except sqlite3.Error as exc:
            meta["status"] = "sql_error"
            meta["error"] = "EXPLAIN QUERY PLAN 失败：%s" % exc
            write_json(meta_path, meta)
            eprint("第 %d 条语句计划阶段出错，已停止：%s（详见 %s）"
                   % (index, exc, meta_path))
            sys.exit(1)
        # 2) 带墙钟超时的执行（set_progress_handler 周期性检查，超时返回 1 中断）。
        deadline = time.monotonic() + float(args.timeout)
        state = {"timed_out": False}

        def _handler():
            if time.monotonic() > deadline:
                state["timed_out"] = True
                return 1
            return 0

        conn.set_progress_handler(_handler, 5000)
        started = time.perf_counter()
        columns, rows, truncated = [], [], False
        try:
            cur = conn.execute(stmt)
            if cur.description:
                columns = [d[0] for d in cur.description]
                for row in cur:
                    if len(rows) >= args.max_rows:
                        truncated = True
                        break
                    rows.append(row)
        except sqlite3.Error as exc:
            conn.set_progress_handler(None, 0)
            meta["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            if state["timed_out"]:
                meta["status"] = "timeout"
                meta["error"] = "超过墙钟超时 %.1f 秒，语句被中断" % float(args.timeout)
            else:
                meta["status"] = "sql_error"
                meta["error"] = str(exc)
            write_json(meta_path, meta)
            eprint("第 %d 条语句执行失败（status=%s），已停止；详见 %s"
                   % (index, meta["status"], meta_path))
            sys.exit(1)
        finally:
            conn.set_progress_handler(None, 0)
        meta["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        meta["columns"] = columns
        # 3) 结果快照落盘并哈希（空结果同样写只有表头的 CSV）。
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if columns:
                writer.writerow(columns)
            writer.writerows(rows)
        meta["result_csv"] = str(csv_path)
        meta["result_csv_sha256"] = sha256_file(csv_path)
        meta["rows_returned"] = len(rows)
        meta["rows_truncated"] = truncated
        if not columns:
            meta["status"] = "no_result_set"
        elif len(rows) == 0:
            meta["status"] = "empty_result"
        else:
            meta["status"] = "ok"
        # 4) 基线对账：对 SQL 中命名的每张表取未过滤 COUNT(*)，
        #    计算 rows_returned / baseline；JOIN 查询行数超过最大单表基线时给出扇出预警。
        tables = []
        for m in TABLE_REF_RE.finditer(stmt):
            tname = m.group(1)
            if tname not in tables:
                tables.append(tname)
        baselines = {}
        for tname in tables:
            try:
                n = conn.execute(
                    "SELECT COUNT(*) FROM %s" % quote_ident(tname)
                ).fetchone()[0]
                baselines[tname] = {
                    "unfiltered_count": n,
                    "ratio_rows_returned_over_baseline": (len(rows) / n) if n else None,
                }
            except sqlite3.Error as exc:
                baselines[tname] = {"unfiltered_count": None, "error": str(exc)}
        meta["baseline_reconciliation"] = baselines
        known = [v["unfiltered_count"] for v in baselines.values()
                 if v.get("unfiltered_count") is not None]
        meta["fanout_warning"] = bool(JOIN_RE.search(stmt)) and bool(known) \
            and len(rows) > max(known)
        write_json(meta_path, meta)
        print(json.dumps({
            "statement_index": index,
            "status": meta["status"],
            "rows_returned": meta["rows_returned"],
            "rows_truncated": truncated,
            "fanout_warning": meta["fanout_warning"],
            "meta": str(meta_path),
        }, ensure_ascii=False))
    conn.close()
    sys.exit(0)


# ---------------------------------------------------------------- reconcile


def cmd_reconcile(args):
    try:
        claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        eprint("读取复核声明失败：%s" % exc)
        sys.exit(2)
    conn = open_ro(args.db)
    recon = base_meta(args.db)
    recon["claim_id"] = claim.get("id")
    recon["description"] = claim.get("description")
    recon["sql_reference"] = claim.get("sql_reference")
    checks_out = []
    any_fail = False
    for idx, chk in enumerate(claim.get("checks", []), 1):
        kind = chk.get("kind")
        sql = chk.get("sql", "")
        expect = chk.get("expect", {})
        record = {"index": idx, "kind": kind, "sql": sql, "expect": expect}
        try:
            rows = conn.execute(sql).fetchall()
        except sqlite3.Error as exc:
            record["status"] = "FAIL"
            record["error"] = "复核 SQL 执行失败：%s" % exc
            any_fail = True
            checks_out.append(record)
            continue
        if kind == "row_count":
            got = len(rows)
            record["got"] = got
            record["status"] = "PASS" if got == expect.get("rows") else "FAIL"
        elif kind == "aggregate":
            got = rows[0][0] if rows and rows[0] else None
            record["got"] = got
            ok = False
            if got is not None and expect.get("value") is not None:
                try:
                    ok = abs(float(got) - float(expect["value"])) <= float(
                        expect.get("tolerance", 0))
                except (TypeError, ValueError):
                    ok = got == expect["value"]
            record["status"] = "PASS" if ok else "FAIL"
        else:
            record["status"] = "FAIL"
            record["error"] = "未知复核类型：%r（支持 row_count / aggregate）" % kind
        if record["status"] == "FAIL":
            any_fail = True
        checks_out.append(record)
    conn.close()
    recon["checks"] = checks_out
    recon["overall"] = "FAIL" if any_fail else "PASS"
    write_json(args.out, recon)
    print(json.dumps({"overall": recon["overall"],
                      "checks": len(checks_out),
                      "out": str(args.out)}, ensure_ascii=False))
    sys.exit(1 if any_fail else 0)


# ---------------------------------------------------------------- main


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dbfoundry",
        description="SQLite 查询铸造厂：建档、只读执行与行数对账、独立复核。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("survey", help="数据库建档")
    s.add_argument("--db", required=True, help="SQLite 数据库文件路径")
    s.add_argument("--work", required=True, help="建档输出目录")
    s.set_defaults(func=cmd_survey)

    e = sub.add_parser("exec", help="只读执行 .sql 并对账")
    e.add_argument("--db", required=True, help="SQLite 数据库文件路径")
    e.add_argument("--sql", required=True, help="待执行的 .sql 文件")
    e.add_argument("--tag", required=True, help="产物文件前缀标签")
    e.add_argument("--outdir", required=True, help="结果输出目录")
    e.add_argument("--max-rows", type=int, default=100000, help="单语句结果截断上限")
    e.add_argument("--timeout", type=float, default=30.0, help="单语句墙钟超时（秒）")
    e.set_defaults(func=cmd_exec)

    r = sub.add_parser("reconcile", help="独立复核关键聚合")
    r.add_argument("--db", required=True, help="SQLite 数据库文件路径")
    r.add_argument("--claim", required=True, help="复核声明 claim.json")
    r.add_argument("--out", required=True, help="复核结果输出路径")
    r.set_defaults(func=cmd_reconcile)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
