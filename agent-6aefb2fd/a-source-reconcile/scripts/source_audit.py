#!/usr/bin/env python3
"""source_audit.py — 上游数据真实性审计（双源/多源对账 + 字段字典核验 + 哈希存证）。

在任何清洗、统计或绘图之前运行本脚本，回答三个问题：
1. /input 里到底有哪些数据文件，各自的内容哈希、表结构、字段语义类型是什么？
2. 同一数据集的多个来源（如 CSV 快照与 SQLite 库）是否逐单元格一致？
   不一致时差异精确到哪张表、哪一列、哪些行？
3. case.json 声明的 materials 是否全部存在？哪个来源应被裁决为分析主源，依据是什么？

输出（写入 --out 目录）：
  source_audit.json   机器可读的完整审计结果（供后续步骤与 result.json 引用）
  source_audit.md     人读摘要（可直接并入最终报告的"数据来源与一致性"一节）

退出码：0=审计完成（不代表一致；一致与否看 JSON 中 verdict）；2=输入目录无可读表。

仅依赖 pandas/numpy（评测环境 scientific-python 提供）。全部为确定性操作。
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

DATA_EXTS = {".csv", ".tsv", ".tab", ".sqlite", ".sqlite3", ".db", ".xlsx", ".xls"}
ENCODINGS = ["utf-8", "utf-8-sig", "gb18030", "latin-1"]
FLOAT_RTOL = 1e-9
FLOAT_ATOL = 1e-12
MAX_DIFF_CELLS = 50  # 每列最多记录的差异单元格数（防爆炸，总量在 diff_cell_count 中）


def sha256_file(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_csv_robust(path):
    last = None
    for enc in ENCODINGS:
        try:
            sep = "\t" if path.lower().endswith((".tsv", ".tab")) else ","
            return pd.read_csv(path, encoding=enc, sep=sep), enc
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"无法以常见编码读取 {path}: {last}")


def semantic_type(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_integer_dtype(s):
        return "integer"
    if pd.api.types.is_float_dtype(s):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if s.dtype == object:
        nonnull = s.dropna()
        if len(nonnull) == 0:
            return "empty"
        uniq = nonnull.nunique()
        if uniq <= max(20, int(0.05 * len(nonnull))):
            return "categorical"
        return "text"
    return "other"


def profile_frame(df: pd.DataFrame, origin: str) -> dict:
    cols = {}
    for c in df.columns:
        s = df[c]
        cols[str(c)] = {
            "dtype": str(s.dtype),
            "semantic_type": semantic_type(s),
            "missing": int(s.isna().sum()),
            "distinct": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            cols[str(c)]["min"] = float(s.min())
            cols[str(c)]["max"] = float(s.max())
    return {
        "origin": origin,
        "rows": int(len(df)),
        "columns": list(map(str, df.columns)),
        "column_profile": cols,
        "exact_duplicate_rows": int(df.duplicated().sum()),
    }


def load_tables(input_dir):
    """返回 {table_id: {"frame": df, "file": path, "encoding": enc|None}} 与文件清单。"""
    tables, files = {}, []
    for root, _dirs, names in os.walk(input_dir):
        for name in sorted(names):
            path = os.path.join(root, name)
            ext = os.path.splitext(name)[1].lower()
            if ext not in DATA_EXTS:
                continue
            rel = os.path.relpath(path, input_dir)
            entry = {"path": rel, "bytes": os.path.getsize(path), "sha256": sha256_file(path)}
            files.append(entry)
            try:
                if ext in {".sqlite", ".sqlite3", ".db"}:
                    con = sqlite3.connect(path)
                    names_t = [r[0] for r in con.execute(
                        "select name from sqlite_master where type='table' order by name")]
                    for t in names_t:
                        df = pd.read_sql_query(f'SELECT * FROM "{t}"', con)
                        tables[f"{rel}::{t}"] = {"frame": df, "file": rel, "encoding": None}
                    con.close()
                    entry["tables"] = names_t
                elif ext in {".xlsx", ".xls"}:
                    sheets = pd.read_excel(path, sheet_name=None)
                    for t, df in sheets.items():
                        tables[f"{rel}::{t}"] = {"frame": df, "file": rel, "encoding": None}
                    entry["tables"] = list(sheets.keys())
                else:
                    df, enc = read_csv_robust(path)
                    tables[rel] = {"frame": df, "file": rel, "encoding": enc}
                    entry["encoding"] = enc
            except Exception as e:  # noqa: BLE001
                entry["read_error"] = str(e)
    return tables, files


def reconcile_pair(id_a, ta, id_b, tb):
    """逐单元格对账两张表，返回裁决与差异定位。"""
    a, b = ta["frame"], tb["frame"]
    rec = {"pair": [id_a, id_b]}
    ca, cb = list(map(str, a.columns)), list(map(str, b.columns))
    rec["columns_only_in_a"] = sorted(set(ca) - set(cb))
    rec["columns_only_in_b"] = sorted(set(cb) - set(ca))
    rec["row_count"] = {"a": len(a), "b": len(b)}
    common = [c for c in ca if c in set(cb)]
    if rec["columns_only_in_a"] or rec["columns_only_in_b"]:
        rec["verdict"] = "schema_divergent"
        return rec
    diffs, total_diff = {}, 0
    rown = min(len(a), len(b))
    for c in common:
        sa, sb = a[c].iloc[:rown], b[c].iloc[:rown]
        na, nb = sa.isna(), sb.isna()
        mask_na_mismatch = (na != nb)
        both = ~(na | nb)
        if pd.api.types.is_numeric_dtype(sa) and pd.api.types.is_numeric_dtype(sb):
            eq = np.isclose(sa[both].to_numpy(dtype=float, na_value=np.nan),
                            sb[both].to_numpy(dtype=float, na_value=np.nan),
                            rtol=FLOAT_RTOL, atol=FLOAT_ATOL, equal_nan=True)
            val_mismatch_idx = np.flatnonzero(~eq)
        else:
            ca_str = sa[both].astype(str).str.strip()
            cb_str = sb[both].astype(str).str.strip()
            val_mismatch_idx = np.flatnonzero((ca_str != cb_str).to_numpy())
        na_idx = np.flatnonzero(mask_na_mismatch.to_numpy())
        all_idx = sorted(set(val_mismatch_idx.tolist()) | set(na_idx.tolist()))
        if all_idx:
            total_diff += len(all_idx)
            diffs[c] = {
                "diff_cell_count": len(all_idx),
                "examples": [
                    {"row": int(i),
                     "a": None if pd.isna(a[c].iloc[i]) else repr(a[c].iloc[i]),
                     "b": None if pd.isna(b[c].iloc[i]) else repr(b[c].iloc[i])}
                    for i in all_idx[:MAX_DIFF_CELLS]
                ],
            }
    rec["diff_cells_total"] = int(total_diff)
    rec["diff_by_column"] = diffs
    if len(a) != len(b):
        rec["verdict"] = "row_count_divergent"
    elif total_diff == 0:
        rec["verdict"] = "content_identical"
    else:
        rec["verdict"] = "content_divergent"
    return rec


def adjudicate_primary(tables, reconciliations):
    """主源裁决规则（详见 references/reconciliation_rules.md）。"""
    scores = {}
    for tid, t in tables.items():
        df = t["frame"]
        s = 0
        s += 2 if t["file"].lower().endswith((".csv", ".tsv", ".tab")) else 1  # 快照文件优先（可 diff、可 git 存证）
        s -= int(df.isna().sum().sum() > 0)  # 含缺失扣分
        s -= int(df.duplicated().sum() > 0)  # 含完全重复扣分
        scores[tid] = s
    divergent = any(r.get("verdict") not in ("content_identical",)
                    for r in reconciliations)
    # 确定性裁决：得分降序，平局取表 ID 字典序靠前者（与文件遍历顺序无关）
    primary = sorted(scores, key=lambda t: (-scores[t], t))[0] if scores else None
    rule = ("选择得分最高者：快照文件(2)>数据库(1)；含缺失−1；含完全重复−1；"
            "平局取表 ID 字典序靠前者。"
            "任何对账不一致时必须在报告与 result.json 中显式声明主源及理由。")
    return {"primary": primary, "scores": scores, "rule": rule,
            "any_divergence": divergent}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--case", default=None, help="/input/case.json（可选，用于 materials 核验）")
    ap.add_argument("--out", required=True, help="审计输出目录（建议 /app/work 或 /app/output）")
    args = ap.parse_args()

    tables, files = load_tables(args.input)
    if not tables:
        print("SOURCE_AUDIT_STATUS: no_readable_tables", file=sys.stderr)
        sys.exit(2)

    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_dir": os.path.abspath(args.input),
        "files": files,
        "tables": {tid: profile_frame(t["frame"], t["file"]) for tid, t in tables.items()},
        "materials_check": None,
        "reconciliations": [],
        "adjudication": None,
    }

    if args.case and os.path.exists(args.case):
        try:
            case = json.load(open(args.case, encoding="utf-8"))
            declared = [m.get("path") for m in case.get("materials", []) if isinstance(m, dict)]
            present = {f["path"] for f in files}
            audit["case_id"] = case.get("case_id")
            audit["materials_check"] = {
                "declared": declared,
                "missing": [d for d in declared if d not in present],
                "undeclared": sorted(p for p in present
                                     if not any(p.endswith(d) for d in declared)),
            }
        except Exception as e:  # noqa: BLE001
            audit["materials_check"] = {"error": str(e)}

    # 同名/高重叠表两两对账：按列名集合 Jaccard ≥ 0.8 配对
    ids = sorted(tables)
    done = set()
    for i, ia in enumerate(ids):
        for ib in ids[i + 1:]:
            sa, sb = set(map(str, tables[ia]["frame"].columns)), set(map(str, tables[ib]["frame"].columns))
            jac = len(sa & sb) / max(1, len(sa | sb))
            if jac >= 0.8 and (ia, ib) not in done:
                audit["reconciliations"].append(
                    reconcile_pair(ia, tables[ia], ib, tables[ib]))
                done.add((ia, ib))
    audit["adjudication"] = adjudicate_primary(tables, audit["reconciliations"])

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "source_audit.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    lines = ["# 数据来源与一致性审计（source_audit 自动生成）", ""]
    for fl in files:
        lines.append(f"- `{fl['path']}`：{fl['bytes']} bytes，sha256={fl['sha256'][:16]}…"
                     + (f"，读取错误：{fl['read_error']}" if "read_error" in fl else ""))
    for tid, prof in audit["tables"].items():
        lines.append(f"- 表 `{tid}`：{prof['rows']} 行 × {len(prof['columns'])} 列，"
                     f"完全重复行 {prof['exact_duplicate_rows']}")
    for r in audit["reconciliations"]:
        lines.append(f"- 对账 `{r['pair'][0]}` vs `{r['pair'][1]}`："
                     f"**{r['verdict']}**（差异单元格 {r.get('diff_cells_total', 0)}）")
    adj = audit["adjudication"]
    lines.append(f"- 主源裁决：`{adj['primary']}`；依据：{adj['rule']}")
    if audit.get("materials_check"):
        mc = audit["materials_check"]
        lines.append(f"- materials 核验：声明 {mc.get('declared')}；缺失 {mc.get('missing')}")
    with open(os.path.join(args.out, "source_audit.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    n_div = sum(1 for r in audit["reconciliations"]
                if r["verdict"] != "content_identical")
    print(f"SOURCE_AUDIT_STATUS: ok tables={len(tables)} pairs={len(audit['reconciliations'])} "
          f"divergent_pairs={n_div} primary={adj['primary']}")


if __name__ == "__main__":
    main()
