#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_steps.py —— 规则即数据 + 清洗即查询

职责：
  1. 读取规则目录中的四张规则 CSV（规则即数据），校验后载入 SQLite 规则表：
       missing_tokens.csv -> rule_missing_tokens(rule_id, token, class, source)
       unit_map.csv       -> rule_unit_map(rule_id, field, from_unit, to_unit, factor, source)
       qc_bounds.csv      -> rule_qc_bounds(rule_id, field, lo, hi, action, source)
       key_fields.csv     -> rule_key_fields(rule_id, field, role, source)
     校验规则：表头必须包含规定列；每一行 source 必须非空（每条规则必须有
     数据字典 / 单位QC规则 / 工单出处）；factor、lo、hi 必须可解析为数值。
     任一规则文件缺失时，创建空规则表并在 query_log 中记录警告（某些案例
     可能不需要全部四类规则）。
  2. 在一个事务内按序逐条执行 steps.sql（清洗即查询），每条语句记录序号与
     受影响行数，写入 query_log.json。任一语句报错：回滚事务、在日志中记录
     出错语句序号与错误信息，退出码 2，便于逐条定位。

退出码：0 成功；2 steps.sql 执行出错（事务已回滚）；4 规则表校验失败。
"""
import argparse
import csv
import json
import os
import sqlite3
import sys

RULE_SPECS = [
    # (文件名, 表名, [(列名, 类型, 是否数值列), ...])
    ("missing_tokens.csv", "rule_missing_tokens",
     [("token", "TEXT", False), ("class", "TEXT", False), ("source", "TEXT", False)]),
    ("unit_map.csv", "rule_unit_map",
     [("field", "TEXT", False), ("from_unit", "TEXT", False), ("to_unit", "TEXT", False),
      ("factor", "REAL", True), ("source", "TEXT", False)]),
    ("qc_bounds.csv", "rule_qc_bounds",
     [("field", "TEXT", False), ("lo", "REAL", True), ("hi", "REAL", True),
      ("action", "TEXT", False), ("source", "TEXT", False)]),
    ("key_fields.csv", "rule_key_fields",
     [("field", "TEXT", False), ("role", "TEXT", False), ("source", "TEXT", False)]),
]


def load_rule_table(conn, rules_dir, fname, table, columns, errors, warnings):
    path = os.path.join(rules_dir, fname)
    col_names = [c[0] for c in columns]
    col_defs = ", ".join("%s %s" % (c[0], c[1]) for c in columns)
    conn.execute("DROP TABLE IF EXISTS %s" % table)
    conn.execute("CREATE TABLE %s (rule_id INTEGER PRIMARY KEY, %s)" % (table, col_defs))
    if not os.path.isfile(path):
        warnings.append("规则文件 %s 不存在，已创建空表 %s" % (fname, table))
        return 0
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing_cols = [c for c in col_names if c not in header]
        if missing_cols:
            errors.append("%s: 表头缺少必需列 %s（实际表头 %s）" % (fname, missing_cols, header))
            return 0
        n = 0
        for lineno, row in enumerate(reader, start=2):  # 第 1 行为表头
            if row is None or all((v or "").strip() == "" for k, v in row.items() if k):
                continue
            n += 1
            vals = []
            for name, _typ, is_num in columns:
                v = row.get(name)
                if v is not None:
                    v = v.strip() if name != "token" else v  # token 原样保留（空串即空白哨兵）
                if name == "source" and not (v or "").strip():
                    errors.append("%s 第 %d 行：source 为空，每条规则必须注明出处（数据字典/单位QC规则/工单）"
                                  % (fname, lineno))
                if is_num:
                    if v is None or v == "":
                        errors.append("%s 第 %d 行：数值列 %s 为空" % (fname, lineno, name))
                    else:
                        try:
                            float(v)
                        except ValueError:
                            errors.append("%s 第 %d 行：数值列 %s 无法解析为数值：%r" % (fname, lineno, name, v))
                vals.append(v)
            conn.execute(
                "INSERT INTO %s (rule_id, %s) VALUES (?, %s)"
                % (table, ", ".join(col_names), ", ".join("?" * len(col_names))),
                [n] + vals,
            )
        return n


def split_statements(sql_text):
    """按 sqlite3.complete_statement 逐条切分，保持原始顺序。"""
    stmts, buf = [], ""
    for line in sql_text.splitlines(True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                stmts.append(buf.strip())
            buf = ""
    if buf.strip():
        stmts.append(buf.strip())
    return stmts


def main():
    ap = argparse.ArgumentParser(description="规则载入 + steps.sql 事务执行")
    ap.add_argument("--db", required=True, help="case.db 路径")
    ap.add_argument("--rules", required=True, help="规则 CSV 目录")
    ap.add_argument("--steps", required=True, help="steps.sql 路径")
    ap.add_argument("--log", required=True, help="输出 query_log.json 路径")
    args = ap.parse_args()

    log = {"db": os.path.abspath(args.db), "steps_file": os.path.abspath(args.steps),
           "rules_dir": os.path.abspath(args.rules), "rule_tables": {},
           "warnings": [], "statements": [], "status": "failed"}

    if not os.path.isfile(args.db):
        print("run_steps: 数据库不存在：%s（请先运行 load_raw.py）" % args.db, file=sys.stderr)
        _dump(args.log, log)
        return 2
    if not os.path.isfile(args.steps):
        print("run_steps: steps.sql 不存在：%s" % args.steps, file=sys.stderr)
        _dump(args.log, log)
        return 2

    conn = sqlite3.connect(args.db)
    errors = []
    try:
        for fname, table, columns in RULE_SPECS:
            n = load_rule_table(conn, args.rules, fname, table, columns, errors, log["warnings"])
            log["rule_tables"][table] = {"file": fname, "rows": n}
        conn.commit()
        if errors:
            log["errors"] = errors
            _dump(args.log, log)
            for e in errors:
                print("run_steps: 规则校验失败：%s" % e, file=sys.stderr)
            return 4

        with open(args.steps, "r", encoding="utf-8") as f:
            sql_text = f.read()
        stmts = split_statements(sql_text)
        # 过滤纯注释段（无实际语句）
        executable = []
        for s in stmts:
            body = "\n".join(ln for ln in s.splitlines()
                             if ln.strip() and not ln.strip().startswith("--"))
            if body.strip():
                executable.append(s)

        conn.execute("BEGIN")
        try:
            for i, stmt in enumerate(executable, start=1):
                cur = conn.execute(stmt)
                preview = " ".join(stmt.split())[:160]
                log["statements"].append({
                    "seq": i,
                    "sql_preview": preview,
                    "rows_affected": cur.rowcount if cur.rowcount != -1 else None,
                })
        except sqlite3.Error as e:
            conn.rollback()
            log["statements"].append({
                "seq": len(log["statements"]) + 1,
                "sql_preview": " ".join(stmt.split())[:160],
                "error": str(e),
            })
            _dump(args.log, log)
            print("run_steps: 第 %d 条语句执行失败，事务已回滚：%s\n  语句: %s"
                  % (len(log["statements"]), e, " ".join(stmt.split())[:200]), file=sys.stderr)
            return 2
        conn.commit()
    finally:
        conn.close()

    log["status"] = "success"
    _dump(args.log, log)
    print("run_steps: OK 执行 %d 条语句；规则表行数 %s"
          % (len(log["statements"]),
             {t: v["rows"] for t, v in log["rule_tables"].items()}))
    return 0


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    sys.exit(main())
