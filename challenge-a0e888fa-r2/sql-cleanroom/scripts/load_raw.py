#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""load_raw.py —— CSV -> SQLite 保真载入（载入保真：不推断、不转换、全记录）

输入一个（可能被注入存储/编码故障的）CSV 转写件，输出：
  - case.db         SQLite 数据库，含表 raw(line_no INTEGER, 每列 TEXT) 与 _meta
  - load_report.json 载入报告：原始 sha256、编码判定、分隔符、行列数、异常说明

原则：
  * 所有单元格按 TEXT 原样保留，不做任何静默类型转换；
  * 编码判定（utf-8-sig / utf-8 / 回退 gb18030 / latin-1）显式写入报告；
  * 列数不一致的行以 NULL 补齐 / 截断并在报告中逐行说明，不丢弃数据；
  * 任何人工修正只能发生在后续 steps.sql，且必须写入 change_log。

退出码：0 成功；3 载入失败（文件缺失/无法解码/无数据行/无表头）。
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sqlite3
import sys


def detect_encoding(raw_bytes):
    """返回 (encoding, note)。所有候选均失败时返回 (None, note)。"""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", "检测到 UTF-8 BOM，按 utf-8-sig 解码并剥离 BOM"
    try:
        raw_bytes.decode("utf-8")
        return "utf-8", "UTF-8 严格解码成功"
    except UnicodeDecodeError:
        pass
    for enc in ("gb18030", "latin-1"):
        try:
            raw_bytes.decode(enc)
            return enc, "UTF-8 严格解码失败，回退 %s（故障修复，已显式记录）" % enc
        except UnicodeDecodeError:
            continue
    return None, "utf-8/gb18030/latin-1 均无法解码，载入中止"


def detect_delimiter(first_line):
    candidates = [",", ";", "\t", "|"]
    counts = {c: first_line.count(c) for c in candidates}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        return ",", "首行无候选分隔符，按单列逗号格式处理"
    return best, "按首行候选分隔符计数判定（,=%d ;=%d \\t=%d |=%d）" % (
        counts[","], counts[";"], counts["\t"], counts["|"])


def sanitize_columns(header):
    """列名清洗为安全标识符；空名/重名改名并记录。返回 (cols, notes)。"""
    cols, notes, seen = [], [], {}
    for i, h in enumerate(header):
        name = (h or "").strip()
        if not name:
            name = "col_%d" % (i + 1)
            notes.append("第 %d 列表头为空，命名为 %s" % (i + 1, name))
        base = name
        if name in seen:
            seen[base] += 1
            name = "%s__%d" % (base, seen[base])
            notes.append("表头重复 '%s'，第 %d 列改名为 %s" % (base, i + 1, name))
        else:
            seen[base] = 1
        cols.append(name)
    return cols, notes


def q(ident):
    return '"' + ident.replace('"', '""') + '"'


def main():
    ap = argparse.ArgumentParser(description="CSV -> SQLite 保真载入")
    ap.add_argument("--input", required=True, help="输入 CSV 路径")
    ap.add_argument("--db", required=True, help="输出 SQLite 数据库路径（case.db）")
    ap.add_argument("--report", required=True, help="输出载入报告 JSON 路径")
    args = ap.parse_args()

    report = {
        "input_file": os.path.abspath(args.input),
        "db_file": os.path.abspath(args.db),
        "status": "failed",
        "notes": [],
    }

    if not os.path.isfile(args.input):
        report["notes"].append("输入文件不存在：%s" % args.input)
        _dump(args.report, report)
        print("load_raw: 输入文件不存在：%s" % args.input, file=sys.stderr)
        return 3

    with open(args.input, "rb") as f:
        raw_bytes = f.read()
    report["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
    report["size_bytes"] = len(raw_bytes)

    if not raw_bytes:
        report["notes"].append("输入文件为 0 字节，无法载入")
        _dump(args.report, report)
        print("load_raw: 输入文件为 0 字节", file=sys.stderr)
        return 3

    encoding, enc_note = detect_encoding(raw_bytes)
    report["encoding"] = encoding
    report["encoding_note"] = enc_note
    if encoding is None:
        _dump(args.report, report)
        print("load_raw: 无法解码输入文件", file=sys.stderr)
        return 3
    text = raw_bytes.decode(encoding)
    # 物理行数（按换行符粗计，供人工核对；逻辑行数以 csv 解析为准）
    report["physical_lines"] = text.count("\n") + (0 if text.endswith("\n") else 1)

    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter, delim_note = detect_delimiter(first_line)
    report["delimiter"] = "\\t" if delimiter == "\t" else delimiter
    report["delimiter_note"] = delim_note

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows or not any(cell.strip() for cell in rows[0]):
        report["notes"].append("未找到有效表头行，载入中止")
        _dump(args.report, report)
        print("load_raw: 未找到有效表头行", file=sys.stderr)
        return 3

    header = rows[0]
    cols, col_notes = sanitize_columns(header)
    report["notes"].extend(col_notes)
    n_cols = len(cols)

    data_rows = rows[1:]
    # 丢弃完全空白的行（所有单元格皆为空白），并记录
    kept, blank_skipped = [], 0
    for r in data_rows:
        if all((c or "").strip() == "" for c in r):
            blank_skipped += 1
        else:
            kept.append(r)
    if blank_skipped:
        report["notes"].append("跳过 %d 个全空白物理行（非数据）" % blank_skipped)
    if not kept:
        report["notes"].append("表头之外没有任何数据行，载入中止")
        _dump(args.report, report)
        print("load_raw: 无数据行", file=sys.stderr)
        return 3

    ragged = []
    for idx, r in enumerate(kept, start=1):
        if len(r) < n_cols:
            ragged.append("第 %d 行仅 %d 列（期望 %d），缺失列以 NULL 补齐" % (idx, len(r), n_cols))
            r.extend([None] * (n_cols - len(r)))
        elif len(r) > n_cols:
            ragged.append("第 %d 行有 %d 列（期望 %d），多余列已截断（原值见源文件 sha256 可复核）" % (idx, len(r), n_cols))
            del r[n_cols:]
    if ragged:
        report["ragged_rows"] = ragged

    if os.path.exists(args.db):
        os.remove(args.db)
    conn = sqlite3.connect(args.db)
    try:
        col_defs = ", ".join(q(c) + " TEXT" for c in cols)
        conn.execute("CREATE TABLE raw (line_no INTEGER PRIMARY KEY, %s)" % col_defs)
        conn.executemany(
            "INSERT INTO raw (line_no, %s) VALUES (?, %s)"
            % (", ".join(q(c) for c in cols), ", ".join("?" * n_cols)),
            [(i, *r) for i, r in enumerate(kept, start=1)],
        )
        conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO _meta (key, value) VALUES (?, ?)",
            [
                ("source_file", os.path.abspath(args.input)),
                ("sha256", report["sha256"]),
                ("encoding", encoding),
                ("delimiter", report["delimiter"]),
                ("columns", json.dumps(cols, ensure_ascii=False)),
                ("n_rows", str(len(kept))),
                ("n_cols", str(n_cols)),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    report["n_rows"] = len(kept)
    report["n_cols"] = n_cols
    report["columns"] = cols
    report["status"] = "success"
    _dump(args.report, report)
    print("load_raw: OK rows=%d cols=%d encoding=%s sha256=%s"
          % (len(kept), n_cols, encoding, report["sha256"][:16]))
    return 0


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    sys.exit(main())
