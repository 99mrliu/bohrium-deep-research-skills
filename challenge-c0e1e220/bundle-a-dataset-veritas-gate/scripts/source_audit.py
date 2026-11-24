#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_audit — dataset-veritas-gate 重心脚本 1：上游数据真实性与跨源一致性审计。

在计算任何统计量之前先回答三个问题：
  1. 这份数据是什么？（文件清点 + sha256 + 已知数据集指纹软核对）
  2. CSV 与 SQLite 是不是同一份数据？（行数闭合 / 列映射 / 逐值比对）
  3. 每个字段的类型与单位口径是什么？（CSV 嗅探 + SQLite affinity 审计 +
     numeric-in-text 陷阱识别）

用法：
  python3 source_audit.py run --input-dir /input --work-dir /app/work
      写出 /app/work/source_audit.json 并打印摘要；exit 0=完成（有 warning 也 0），
      exit 1=入口级失败（目录不存在等）。

原则：已知数据集指纹只做"软核对"——不匹配只写 warning，绝不硬拒。
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_a as pa

COMPARE_FULL_LIMIT = 5000  # 行数 ≤5000 全量逐值比对；否则确定性 stride 采样


# ==================================================================
# CSV / DB 画像
# ==================================================================

def profile_csv(input_dir, fname):
    path = os.path.join(input_dir, fname)
    info = pa.read_csv_table(path)
    rows = info["rows"]
    n_cols = max((len(r) for r in rows), default=0)
    return {"file": fname, "encoding": info["encoding"],
            "delimiter": info["delimiter"], "has_header": info["has_header"],
            "header": info["header"], "n_rows": len(rows), "n_cols": n_cols,
            "rows": rows}


def profile_db(input_dir, fname):
    path = os.path.join(input_dir, fname)
    out = {"file": fname, "tables": []}
    import sqlite3
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        names = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for tname in names:
            cols = []
            for cid, name, decl, notnull, dflt, pk in cur.execute(f'PRAGMA table_info("{tname}")'):
                cols.append({"name": name, "decl_type": decl or "",
                             "affinity": pa.sqlite_affinity(decl)})
            raw = cur.execute(f'SELECT * FROM "{tname}"').fetchall()
            # numeric-in-text：affinity=TEXT 且 ≥95% 非空值可解析为数值
            for j, c in enumerate(cols):
                if c["affinity"] != "TEXT":
                    c["numeric_in_text"] = False
                    c["numeric_fraction"] = None
                    continue
                vals = [r[j] for r in raw
                        if r[j] is not None and not pa.is_missing(r[j])]
                if not vals:
                    c["numeric_in_text"] = False
                    c["numeric_fraction"] = 0.0
                    continue
                n_num = sum(1 for v in vals if pa.try_float(v) is not None)
                frac = n_num / len(vals)
                c["numeric_fraction"] = round(frac, 4)
                c["numeric_in_text"] = frac >= 0.95
            out["tables"].append({
                "name": tname, "n_rows": len(raw), "n_cols": len(cols),
                "columns": cols,
                "create_sql": cur.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (tname,)).fetchone()[0],
                "_rows": raw})
    finally:
        conn.close()
    return out


# ==================================================================
# 列映射与逐值比对
# ==================================================================

def norm_name(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def map_columns(csv_header, db_cols, csv_ncols):
    """CSV 列 → DB 列映射。返回 (mapping[{csv_col, db_col, method}], 主方法)。"""
    mapping = []
    db_names = [c["name"] for c in db_cols]
    used = set()
    methods = []
    headerless = csv_header is None
    header = csv_header or [f"c{j}" for j in range(csv_ncols)]
    for j, h in enumerate(header):
        hit, method = None, None
        if headerless:
            # 无表头时名称相等没有意义，直接按位置映射
            if j < len(db_names) and db_names[j] not in used:
                hit, method = db_names[j], "positional"
        elif h in db_names and h not in used:
            hit, method = h, "exact"
        else:
            nh = norm_name(h)
            for dn in db_names:
                if dn not in used and norm_name(dn) == nh:
                    hit, method = dn, "fuzzy"
                    break
        if hit is None and j < len(db_names) and db_names[j] not in used:
            hit, method = db_names[j], "positional"
        if hit is not None:
            used.add(hit)
            methods.append(method)
            mapping.append({"csv_col": h, "csv_index": j, "db_col": hit, "method": method})
    main = "mixed"
    if methods and all(m == methods[0] for m in methods):
        main = methods[0]
    elif methods:
        main = "mixed(" + ",".join(sorted(set(methods))) + ")"
    return mapping, (main or "none")


def compare_values(csv_rows, mapping, db_rows, db_cols):
    """逐值比对。≤5000 行全量；否则确定性 stride 采样（每隔 step 行，口径写入结果）。"""
    db_idx = {c["name"]: j for j, c in enumerate(db_cols)}
    n = min(len(csv_rows), len(db_rows))
    if n <= COMPARE_FULL_LIMIT:
        idxs = range(n)
        scope = f"full（全量 {n} 行）"
    else:
        step = math.ceil(n / COMPARE_FULL_LIMIT)
        idxs = range(0, n, step)
        scope = f"stride-sample（>5000 行，确定性每隔 {step} 行采样，共 {len(list(idxs))} 行；非随机无 seed）"
    n_cmp = 0
    mismatches = []
    n_missing_equal = 0
    for i in idxs:
        cr = csv_rows[i]
        dr = db_rows[i]
        for m in mapping:
            cv = cr[m["csv_index"]] if m["csv_index"] < len(cr) else ""
            dv = pa.normalize_db_cell(dr[db_idx[m["db_col"]]])
            n_cmp += 1
            if pa.is_missing(cv) and (dv == "" or pa.is_missing(dv)):
                n_missing_equal += 1
                continue
            cf, df_ = pa.try_float(cv), pa.try_float(dv)
            if cf is not None and df_ is not None:
                tol = max(1e-9 * max(abs(cf), abs(df_)), 1e-12)
                if abs(cf - df_) > tol:
                    if len(mismatches) < 20:
                        mismatches.append({"row": i, "csv_col": m["csv_col"],
                                           "db_col": m["db_col"], "csv": cv, "db": dv})
            else:
                if str(cv).strip() != str(dv).strip():
                    if len(mismatches) < 20:
                        mismatches.append({"row": i, "csv_col": m["csv_col"],
                                           "db_col": m["db_col"], "csv": cv, "db": dv})
    return {"compare_scope": scope, "n_cells_compared": n_cmp,
            "n_value_mismatch_sampled": len(mismatches),
            "mismatch_examples": mismatches}


# ==================================================================
# 指纹软核对
# ==================================================================

def fingerprint_check(shapes, task_text):
    """shapes: [(rows, cols), ...] 来自各数据源。软核对：只提示，不硬拒。"""
    out = []
    for shape, fp in pa.FINGERPRINTS.items():
        shape_hit = shape in shapes
        kw_hit = any(k in task_text for k in fp["keywords"]) if task_text else False
        if shape_hit and kw_hit:
            out.append({"dataset": fp["dataset"], "shape": list(shape),
                        "shape_hit": True, "keyword_hit": True,
                        "verdict": "consistent",
                        "note": "形状与 task.md 关键词一致（软核对通过；仅提示，不构成真实性证明）",
                        "columns": fp["columns"]})
        elif shape_hit and not kw_hit:
            out.append({"dataset": fp["dataset"], "shape": list(shape),
                        "shape_hit": True, "keyword_hit": False,
                        "verdict": "warning",
                        "note": f"数据形状像 {fp['dataset']}（{shape[0]}×{shape[1]}）"
                                f"但 task.md 未出现关键词 {fp['keywords']}，请人工确认数据集身份",
                        "columns": fp["columns"]})
        elif not shape_hit and kw_hit:
            out.append({"dataset": fp["dataset"], "shape": list(shape),
                        "shape_hit": False, "keyword_hit": True,
                        "verdict": "warning",
                        "note": f"task.md 提及 {fp['dataset']} 但各数据源形状均不是 "
                                f"{shape[0]}×{shape[1]}，请确认是否裁剪/抽样过",
                        "columns": fp["columns"]})
    return out


# ==================================================================
# 主审计
# ==================================================================

def audit_input(input_dir, task_text=None):
    if task_text is None:
        tm = os.path.join(input_dir, "task.md")
        task_text = ""
        if os.path.isfile(tm):
            with open(tm, "r", encoding="utf-8", errors="replace") as f:
                task_text = f.read()
    files = sorted(f for f in os.listdir(input_dir)
                   if os.path.isfile(os.path.join(input_dir, f)))
    inventory = [{"file": f, "size": os.path.getsize(os.path.join(input_dir, f)),
                  "sha256": pa.sha256_file(os.path.join(input_dir, f))} for f in files]

    csvs, dbs = [], []
    for f in files:
        if f.lower().endswith((".csv", ".tsv")):
            csvs.append(profile_csv(input_dir, f))
        elif f.lower().endswith((".db", ".sqlite", ".sqlite3")):
            dbs.append(profile_db(input_dir, f))

    warnings = []
    for d in dbs:
        for t in d["tables"]:
            nit = [c["name"] for c in t["columns"] if c.get("numeric_in_text")]
            if nit:
                warnings.append(
                    f"numeric-in-text: {d['file']} 表 {t['name']} 的列 {nit} "
                    f"以 TEXT affinity 存储数值（numeric_fraction≥0.95），已识别；"
                    f"跨源比对与统计解析将按数值处理")

    # 跨源一致性：CSV ↔ DB 配对（一一配对按数量最小值；优先同名 stem）
    cross = []
    pairs = []
    if len(csvs) == 1 and len(dbs) == 1:
        pairs = [(csvs[0], dbs[0])]
    else:
        used = set()
        for c in csvs:
            stem = os.path.splitext(c["file"])[0].lower()
            hit = next((d for d in dbs if os.path.splitext(d["file"])[0].lower() == stem
                        and d["file"] not in used), None)
            if hit:
                used.add(hit["file"])
                pairs.append((c, hit))
        for c in csvs:
            if any(pc is c for pc, _ in pairs):
                continue
            free = [d for d in dbs if d["file"] not in used]
            if free:
                used.add(free[0]["file"])
                pairs.append((c, free[0]))
    for c, d in pairs:
        if not d["tables"]:
            cross.append({"csv": c["file"], "db": d["file"], "verdict": "db_empty",
                          "rows_csv": c["n_rows"], "rows_db": 0, "rows_equal": False,
                          "mapping_method": "none", "compare_scope": "none",
                          "n_value_mismatch": -1, "mapping": []})
            continue
        t = d["tables"][0]
        mapping, method = map_columns(c["header"], t["columns"], c["n_cols"])
        rows_equal = c["n_rows"] == t["n_rows"]
        if rows_equal:
            cmp_res = compare_values(c["rows"], mapping, t["_rows"], t["columns"])
            n_mm = cmp_res["n_value_mismatch_sampled"]
            if n_mm == 0:
                verdict = "consistent"
            else:
                verdict = f"value_mismatch({n_mm} 处示例内)"
        else:
            cmp_res = {"compare_scope": "skipped（行数不一致）",
                       "n_cells_compared": 0, "n_value_mismatch_sampled": -1,
                       "mismatch_examples": []}
            verdict = "row_count_mismatch"
        nit_cols = [col["name"] for col in t["columns"] if col.get("numeric_in_text")]
        if verdict == "consistent" and nit_cols:
            verdict = "consistent_with_type_coercion"
        cross.append({"csv": c["file"], "db": d["file"], "db_table": t["name"],
                      "rows_csv": c["n_rows"], "rows_db": t["n_rows"],
                      "rows_equal": rows_equal, "mapping_method": method,
                      "mapping": mapping, "numeric_in_text_cols": nit_cols,
                      "n_value_mismatch": cmp_res["n_value_mismatch_sampled"],
                      **{k: v for k, v in cmp_res.items()
                         if k != "n_value_mismatch_sampled"},
                      "verdict": verdict})
        if not rows_equal:
            warnings.append(f"跨源行数不一致：{c['file']}({c['n_rows']}) vs "
                            f"{d['file']}({t['n_rows']})")
        elif cmp_res["n_value_mismatch_sampled"] > 0:
            warnings.append(f"跨源值不一致：{c['file']} ↔ {d['file']} 采样内 "
                            f"{cmp_res['n_value_mismatch_sampled']} 处（示例已记录）")

    shapes = set()
    for c in csvs:
        shapes.add((c["n_rows"], c["n_cols"]))
    for d in dbs:
        for t in d["tables"]:
            shapes.add((t["n_rows"], t["n_cols"]))
    fps = fingerprint_check(shapes, task_text)
    for f in fps:
        if f["verdict"] == "warning":
            warnings.append("fingerprint: " + f["note"])

    # 去掉内部字段
    for d in dbs:
        for t in d["tables"]:
            t.pop("_rows", None)
    for c in csvs:
        c.pop("rows", None)

    return {"audit_utc": pa.utc_now(), "input_dir": input_dir,
            "inventory": inventory, "csvs": csvs, "dbs": dbs,
            "cross_source": cross, "fingerprints": fps, "warnings": warnings}


def main():
    ap = argparse.ArgumentParser(prog="source_audit.py",
                                 description="上游数据真实性与跨源一致性审计")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--input-dir", required=True)
    pr.add_argument("--work-dir", required=True)
    args = ap.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"[source_audit] FAIL: 输入目录不存在: {args.input_dir}")
        sys.exit(1)
    os.makedirs(args.work_dir, exist_ok=True)
    try:
        audit = audit_input(args.input_dir)
    except Exception as e:  # noqa
        print(f"[source_audit] FAIL: {e}")
        sys.exit(1)
    out = os.path.join(args.work_dir, "source_audit.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[source_audit] 完成 → {out}")
    print(f"  文件清点: {len(audit['inventory'])} 个；CSV: {len(audit['csvs'])}；"
          f"SQLite: {len(audit['dbs'])}")
    for c in audit["csvs"]:
        print(f"  CSV {c['file']}: enc={c['encoding']} delim={repr(c['delimiter'])} "
              f"header={c['has_header']} rows={c['n_rows']} cols={c['n_cols']}")
    for d in audit["dbs"]:
        for t in d["tables"]:
            nit = [c["name"] for c in t["columns"] if c.get("numeric_in_text")]
            print(f"  DB {d['file']}:{t['name']} rows={t['n_rows']} "
                  f"numeric-in-text={nit or '无'}")
    for cs in audit["cross_source"]:
        print(f"  跨源 {cs['csv']} ↔ {cs['db']}: verdict={cs['verdict']} "
              f"(rows {cs['rows_csv']}/{cs['rows_db']}, mapping={cs['mapping_method']})")
    for w in audit["warnings"]:
        print(f"  ⚠ {w}")
    sys.exit(0)


if __name__ == "__main__":
    main()
