#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_engine.py — 端到端确定性科研数据分析引擎（stdlib-only）。

子命令：
  run    --input DIR --work DIR --output DIR [--rules rules.json] [--sql file.sql]
  verify --input DIR --work DIR --output DIR

设计原则：
  * 确定性：不使用任何随机数；同一输入必得同一输出。
  * 诚实降级：任何缺失的输入片段只记录 anomaly 并继续，绝不伪造数值；
    仅当 --input 目录本身不存在时以退出码 2 终止。
  * 不静默丢数据：缺失标记置 null 且保留该行；精确重复行按规则删除并计数；
    离群值只标记计数、绝不删除。
  * 双通道复核：verify 用与 run 不同的代码路径（纯 csv.reader 循环）独立重算
    n / mean / std(ddof=1)，容差 1e-9，并校验 result.json 契约完整性与产物哈希。

Python 3.9+，仅标准库；matplotlib 可选（缺失时降级为图形规格 JSON + 绘图数据 CSV）。
所有错误信息写 stderr，前缀 [case_engine]。
"""

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import statistics
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ENGINE_VERSION = "1.0.0"

DEFAULT_MISSING_TOKENS = ["", "NA", "N/A", "NaN", "nan", "null", "None", "-"]

DEFAULT_RULES = {
    "missing_tokens": list(DEFAULT_MISSING_TOKENS),
    "drop_duplicates": True,          # 删除精确重复行（记录删除条数）
    "listwise_delete_missing": False,  # 默认保留含缺失的行（置 null），不整行删除
    "coerce_numeric": True,           # 数值列强制转型；失败值置 null 并记录
    "numeric_majority": 0.9,          # 非缺失值中 >=90% 可解析为数值即判为数值列
    "outlier_iqr_factor": 1.5,        # IQR 离群标记系数（只标记不删除）
    "groupby_max_levels": 50,         # 目标列水平数上限，超过则跳过 group-by 并记录
}

# 目标列（分组/直方图）识别模式
TARGET_PATTERN = re.compile(r"(class|target|label|类别|强度|strength)", re.IGNORECASE)

# 契约字段名归一化后的映射表（键 -> result.json 内部产物名）
CONTRACT_MAP = [
    ("caseid", "case_id"),
    ("cleanedtable", "cleaned_table"),
    ("cleaneddata", "cleaned_table"),
    ("cleaned", "cleaned_table"),
    ("descriptivestatistics", "statistics"),
    ("statistics", "statistics"),
    ("stats", "statistics"),
    ("figures", "figures"),
    ("figure", "figures"),
    ("plots", "figures"),
    ("plot", "figures"),
    ("queries", "queries"),
    ("query", "queries"),
    ("sql", "queries"),
    ("provenance", "provenance"),
    ("anomalies", "anomalies"),
    ("anomaly", "anomalies"),
    ("rowreconciliation", "row_reconciliation"),
    ("reconciliation", "row_reconciliation"),
    ("runlog", "run_log"),
    ("log", "run_log"),
    ("status", "status"),
]

UNIT_HINTS = re.compile(
    r"(kg|mpa|pa\b|mm\b|cm\b|m\b|g\b|mg|days?|hours?|%|percent|°c|k\b|mol|hz|v\b|a\b|w\b|j\b)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def log_err(msg):
    print(f"[case_engine] {msg}", file=sys.stderr)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_name(s):
    """归一化名称：NFKC、小写、去空白/下划线/连字符。用于契约字段与列名匹配。"""
    s = unicodedata.normalize("NFKC", str(s)).strip().lower()
    s = re.sub(r"[\s_\-]+", "", s)
    return s


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def parse_number(v):
    """返回 ('int'|'float'|'other', value)。"""
    s = v.strip()
    if re.fullmatch(r"[+-]?\d+", s):
        try:
            return "int", int(s)
        except ValueError:
            pass
    try:
        f = float(s)
        if math.isnan(f) or math.isinf(f):
            return "other", None
        return "float", f
    except ValueError:
        return "other", None


def quantile_type7(sorted_vals, p):
    """线性插值分位数（type-7，与 numpy 默认一致）。sorted_vals 须已排序非空。"""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * p  # 0 基位置
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


# --------------------------------------------------------------------------- #
# 输入清点与 case.json / task.md
# --------------------------------------------------------------------------- #
def inventory(input_dir, anomalies):
    files = {}
    for p in sorted(Path(input_dir).rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(input_dir))
            try:
                files[rel] = {"sha256": sha256_file(p), "size_bytes": p.stat().st_size}
            except OSError as e:
                anomalies.append({"kind": "inventory_error", "detail": f"{rel}: {e}"})
                log_err(f"inventory error on {rel}: {e}")
    return files


def read_case_json(input_dir, anomalies):
    """容忍 contract 为列表或字典。返回 (case_id, contract_fields list[str])。"""
    path = Path(input_dir) / "case.json"
    case_id, contract = None, []
    if not path.exists():
        anomalies.append({"kind": "missing_file", "detail": "case.json 不存在，case_id 置 null，契约字段为空"})
        log_err("case.json not found; continuing with empty contract")
        return case_id, contract
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        anomalies.append({"kind": "undecodable_json", "detail": f"case.json 解析失败: {e}"})
        log_err(f"case.json parse error: {e}")
        return case_id, contract
    case_id = data.get("case_id")
    oc = data.get("output_contract", [])
    if isinstance(oc, dict):
        contract = [str(k) for k in oc.keys()]
    elif isinstance(oc, list):
        contract = [str(x) for x in oc]
    else:
        anomalies.append({"kind": "contract_shape_unknown",
                          "detail": f"output_contract 类型无法识别: {type(oc).__name__}"})
        contract = []
    return case_id, contract


def read_task_md(input_dir, anomalies, max_lines=200):
    path = Path(input_dir) / "task.md"
    if not path.exists():
        anomalies.append({"kind": "missing_file", "detail": "task.md 不存在"})
        log_err("task.md not found; continuing")
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        anomalies.append({"kind": "missing_file", "detail": f"task.md 读取失败: {e}"})
        return ""
    return "\n".join(lines[:max_lines])


# --------------------------------------------------------------------------- #
# CSV 读取 / 画像 / 清洗
# --------------------------------------------------------------------------- #
def read_csv_tolerant(path, anomalies):
    """返回 (header, rows, meta)；失败返回 (None, None, meta)。"""
    raw = Path(path).read_bytes()
    text, encoding = None, None
    for enc in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        anomalies.append({"kind": "undecodable_csv",
                          "detail": f"{Path(path).name}: utf-8-sig 与 gb18030 均解码失败"})
        log_err(f"undecodable csv: {path}")
        return None, None, {"encoding": None, "delimiter": None}
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    if not rows:
        return [], [], {"encoding": encoding, "delimiter": delimiter}
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any(c.strip() for c in r)]  # 跳过全空行
    return header, body, {"encoding": encoding, "delimiter": delimiter}


def profile_columns(header, rows, missing_tokens, rules):
    """对原始行做列画像：类型推断、缺失计数、distinct、数值 min/max/mean。"""
    majority = float(rules.get("numeric_majority", 0.9))
    profiles = []
    for j, name in enumerate(header):
        vals = [(r[j] if j < len(r) else "") for r in rows]
        missing = [v.strip() in missing_tokens for v in vals]
        n_missing = sum(missing)
        observed = [v for k, v in enumerate(vals) if not missing[k]]
        distinct = len(set(observed))
        n_int = n_float = n_other = 0
        nums = []
        for v in observed:
            kind, num = parse_number(v)
            if kind == "int":
                n_int += 1
                nums.append(float(num))
            elif kind == "float":
                n_float += 1
                nums.append(num)
            else:
                n_other += 1
        n_obs = len(observed)
        if n_obs > 0 and n_other == 0:
            ctype = "int" if n_float == 0 else "float"
        elif n_obs >= 5 and (n_int + n_float) / n_obs >= majority:
            ctype = "float"  # 多数可解析为数值：判为数值列，余者记 coercion failure
        else:
            ctype = "text"
        prof = {
            "name": name, "type": ctype,
            "n_observed": n_obs, "n_missing": n_missing,
            "distinct": distinct, "n_coercion_failures": n_other if ctype != "text" else 0,
        }
        if ctype in ("int", "float") and nums:
            prof.update({"min": min(nums), "max": max(nums),
                         "mean": sum(nums) / len(nums)})
        profiles.append(prof)
    return profiles


def clean_rows(header, rows, profiles, missing_tokens, rules, anomalies, fname):
    """按规则清洗。返回 (cleaned_header, cleaned_rows[list[list[str]]], n_dup_removed,
    coercion_failures[list])。"""
    coerce = bool(rules.get("coerce_numeric", True))
    cleaned = []
    coercion_failures = []
    for i, r in enumerate(rows):
        out = []
        for j, prof in enumerate(profiles):
            v = r[j] if j < len(r) else ""
            if v.strip() in missing_tokens:
                out.append("")  # null，绝不当作 0
                continue
            if coerce and prof["type"] in ("int", "float"):
                kind, num = parse_number(v)
                if kind == "other":
                    coercion_failures.append({"row": i + 2, "column": prof["name"], "value": v})
                    out.append("")
                elif prof["type"] == "int" and kind == "int":
                    out.append(str(num))
                else:
                    out.append(repr(float(num)))  # repr 保证 round-trip 精确
            else:
                out.append(v)
        cleaned.append(out)

    n_dup = 0
    if rules.get("drop_duplicates", True):
        seen = set()
        deduped = []
        for row in cleaned:
            key = tuple(row)
            if key in seen:
                n_dup += 1
            else:
                seen.add(key)
                deduped.append(row)
        cleaned = deduped
        if n_dup:
            anomalies.append({"kind": "duplicate_rows",
                              "detail": f"{fname}: 删除精确重复行 {n_dup} 条"})

    if rules.get("listwise_delete_missing", False):
        before = len(cleaned)
        cleaned = [row for row in cleaned if all(c != "" for c in row)]
        dropped = before - len(cleaned)
        if dropped:
            anomalies.append({"kind": "listwise_deletion",
                              "detail": f"{fname}: 按 rules 整行删除含缺失行 {dropped} 条"})

    if coercion_failures:
        sample = coercion_failures[:5]
        anomalies.append({"kind": "type_coercion_failure",
                          "detail": f"{fname}: {len(coercion_failures)} 个值无法转为数值，已置 null；"
                                    f"示例 {sample}"})
    return header, cleaned, n_dup, coercion_failures


def write_cleaned_csv(path, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
def column_values(cleaned_rows, j):
    """从清洗后行提取第 j 列：返回 (numeric_vals[float], text_vals[str])。"""
    nums, texts = [], []
    for row in cleaned_rows:
        v = row[j] if j < len(row) else ""
        if v == "":
            continue
        kind, num = parse_number(v)
        if kind in ("int", "float"):
            nums.append(float(num))
        else:
            texts.append(v)
    return nums, texts


def numeric_stats(vals, iqr_factor):
    """n/mean/std(ddof=1)/median/q1/q3(type-7)/min/max/离群计数。"""
    n = len(vals)
    if n == 0:
        return {"type": "float", "n": 0}
    s = sorted(vals)
    mean = sum(vals) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in vals) / (n - 1)) if n > 1 else 0.0
    q1 = quantile_type7(s, 0.25)
    q3 = quantile_type7(s, 0.75)
    iqr = q3 - q1
    lo, hi = q1 - iqr_factor * iqr, q3 + iqr_factor * iqr
    outliers = sum(1 for x in vals if x < lo or x > hi)
    return {
        "type": "float", "n": n, "mean": mean, "std_ddof1": std,
        "median": quantile_type7(s, 0.5), "q1": q1, "q3": q3,
        "min": s[0], "max": s[-1], "outliers_iqr": outliers,
    }


def text_stats(vals):
    from collections import Counter
    c = Counter(vals)
    return {"type": "text", "n": len(vals), "distinct": len(c),
            "top5": [[v, k] for v, k in c.most_common(5)]}


def compute_statistics(cleaned_name, source_name, header, cleaned_rows, profiles, rules):
    """生成单个清洗后 CSV 的统计结构。"""
    iqr_factor = float(rules.get("outlier_iqr_factor", 1.5))
    cols = {}
    for j, prof in enumerate(profiles):
        nums, texts = column_values(cleaned_rows, j)
        if prof["type"] in ("int", "float"):
            st = numeric_stats(nums, iqr_factor)
            st["type"] = prof["type"]
            cols[prof["name"]] = st
        else:
            cols[prof["name"]] = text_stats(texts)

    # 目标列 group-by
    groupby = None
    target_col = None
    for prof in profiles:
        if TARGET_PATTERN.search(prof["name"]):
            target_col = prof["name"]
            break
    if target_col is not None:
        tj = next(p for p in profiles if p["name"] == target_col)
        j = profiles.index(tj)
        levels = {}
        for row in cleaned_rows:
            lv = row[j] if j < len(row) else ""
            if lv == "":
                continue
            levels.setdefault(lv, 0)
            levels[lv] += 1
        max_levels = int(rules.get("groupby_max_levels", 50))
        if len(levels) <= max_levels:
            groupby = {"target_column": target_col, "levels": {}}
            for lv in sorted(levels):
                idx = [k for k, row in enumerate(cleaned_rows)
                       if (row[j] if j < len(row) else "") == lv]
                sub = {}
                for cj, prof in enumerate(profiles):
                    if prof["type"] not in ("int", "float") or cj == j:
                        continue
                    vals = []
                    for k in idx:
                        v = cleaned_rows[k][cj] if cj < len(cleaned_rows[k]) else ""
                        if v == "":
                            continue
                        kind, num = parse_number(v)
                        if kind in ("int", "float"):
                            vals.append(float(num))
                    if vals:
                        n = len(vals)
                        mean = sum(vals) / n
                        std = (math.sqrt(sum((x - mean) ** 2 for x in vals) / (n - 1))
                               if n > 1 else 0.0)
                        sub[prof["name"]] = {"n": n, "mean": mean, "std_ddof1": std,
                                             "min": min(vals), "max": max(vals)}
                groupby["levels"][lv] = {"count": levels[lv], "numeric": sub}
        else:
            groupby = {"target_column": target_col, "skipped": True,
                       "reason": f"目标列水平数 {len(levels)} 超过上限 {max_levels}，"
                                 f"疑似连续数值目标，跳过逐水平 group-by"}
    return {
        "source": source_name,
        "rows": len(cleaned_rows),
        "columns": cols,
        "target_column_guess": target_col,
        "groupby": groupby,
    }


def stats_to_markdown(stats_obj):
    lines = ["# statistics 摘要", "",
             f"生成时间(UTC)：{stats_obj['generated_utc']}",
             f"std 口径：样本标准差 ddof=1；分位数方法：type-7 线性插值。", ""]
    for fname, fs in stats_obj["files"].items():
        lines += [f"## {fname}（来源 {fs['source']}，{fs['rows']} 行）", "",
                  "| column | type | n | mean | std_ddof1 | median | q1 | q3 | min | max | outliers_iqr |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for cname, st in fs["columns"].items():
            if st.get("type") in ("int", "float") and st.get("n", 0) > 0:
                lines.append(
                    f"| {cname} | {st['type']} | {st['n']} | {st['mean']:.6g} | "
                    f"{st['std_ddof1']:.6g} | {st['median']:.6g} | {st['q1']:.6g} | "
                    f"{st['q3']:.6g} | {st['min']:.6g} | {st['max']:.6g} | {st['outliers_iqr']} |")
            elif st.get("type") == "text":
                top = "; ".join(f"{v}×{c}" for v, c in st.get("top5", []))
                lines.append(f"| {cname} | text | {st.get('n', 0)} | — | — | — | — | — | "
                             f"top5: {top} | | |")
            else:
                lines.append(f"| {cname} | {st.get('type')} | 0 | — | — | — | — | — | — | — | — |")
        lines.append("")
        if fs.get("groupby") and not fs["groupby"].get("skipped"):
            gb = fs["groupby"]
            lines.append(f"### group-by（目标列：{gb['target_column']}）")
            for lv, info in gb["levels"].items():
                lines.append(f"- 水平 `{lv}`（n={info['count']}）：" +
                             "；".join(f"{c}: mean={v['mean']:.4g}, std={v['std_ddof1']:.4g}"
                                       for c, v in info["numeric"].items()))
            lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# SQLite
# --------------------------------------------------------------------------- #
def survey_sqlite(db_path, anomalies):
    out = {"file": str(db_path), "tables": []}
    try:
        uri = f"file:{Path(db_path).resolve()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
    except Exception as e:
        anomalies.append({"kind": "db_error", "detail": f"{Path(db_path).name}: 打开失败 {e}"})
        log_err(f"sqlite open failed: {db_path}: {e}")
        return out
    try:
        cur = con.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            try:
                n = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                cols = [{"name": r[1], "decl_type": r[2], "notnull": r[3], "pk": r[5]}
                        for r in cur.execute(f'PRAGMA table_info("{t}")')]
                for c in cols:
                    c["null_count"] = cur.execute(
                        f'SELECT COUNT(*) FROM "{t}" WHERE "{c["name"]}" IS NULL').fetchone()[0]
                out["tables"].append({"name": t, "row_count": n, "columns": cols})
            except Exception as e:
                anomalies.append({"kind": "db_error", "detail": f"表 {t} 调查失败: {e}"})
    finally:
        con.close()
    return out


def run_sql_file(sql_path, db_files, output_dir, anomalies, run_log):
    """对第一个可用数据库逐条执行 SQL（按 ; 切分），捕获 EXPLAIN QUERY PLAN。"""
    results = []
    if not db_files:
        anomalies.append({"kind": "missing_file",
                          "detail": "提供了 --sql 但未发现 SQLite 数据库文件"})
        return results
    stmts = [s.strip() for s in Path(sql_path).read_text(encoding="utf-8").split(";")]
    stmts = [s for s in stmts if s]
    db = db_files[0]
    uri = f"file:{db.resolve()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except Exception as e:
        anomalies.append({"kind": "db_error", "detail": f"{db.name}: 打开失败 {e}"})
        return results
    try:
        cur = con.cursor()
        for i, stmt in enumerate(stmts, 1):
            meta = {"index": i, "statement": stmt, "database": db.name}
            t0 = datetime.now(timezone.utc)
            try:
                plan = [tuple(r) for r in cur.execute("EXPLAIN QUERY PLAN " + stmt)]
                meta["explain_query_plan"] = [str(p) for p in plan]
                cur.execute(stmt)
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
                meta["rows_returned"] = len(rows)
                csv_path = Path(output_dir) / f"query_result_{i}.csv"
                with open(csv_path, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    if cols:
                        w.writerow(cols)
                    w.writerows(rows)
                meta["csv"] = str(csv_path)
                meta["csv_sha256"] = sha256_file(csv_path)
                if len(rows) == 0:
                    anomalies.append({"kind": "empty_result",
                                      "detail": f"SQL #{i} 返回 0 行（记为 empty_result，非错误）"})
            except Exception as e:
                meta["error"] = str(e)
                anomalies.append({"kind": "sql_error", "detail": f"SQL #{i}: {e}"})
                log_err(f"sql #{i} failed: {e}")
            t1 = datetime.now(timezone.utc)
            meta["duration_ms"] = round((t1 - t0).total_seconds() * 1000, 3)
            results.append(meta)
            run_log.append(f"sql #{i}: rows_returned={meta.get('rows_returned', 'error')}")
    finally:
        con.close()
    return results


# --------------------------------------------------------------------------- #
# 图形
# --------------------------------------------------------------------------- #
def make_figures(first_csv_name, header, cleaned_rows, profiles, output_dir,
                 anomalies, run_log):
    """最多 2 张图：目标/首个数值列直方图；前两个数值列散点。始终写 figure_data CSV。"""
    out_dir = Path(output_dir)
    numeric_cols = [p for p in profiles if p["type"] in ("int", "float")]
    target = None
    for p in profiles:
        if TARGET_PATTERN.search(p["name"]) and p["type"] in ("int", "float"):
            target = p["name"]
            break
    if target is None and numeric_cols:
        target = numeric_cols[0]["name"]

    manifest = {"source_csv": first_csv_name, "figures": []}
    if not numeric_cols:
        anomalies.append({"kind": "figure_degraded",
                          "detail": "无数值列可绘图，跳过图形生成"})
        write_json(out_dir / "figures_manifest.json", manifest)
        return manifest

    # 图 1 数据：直方图列
    j1 = next(i for i, p in enumerate(profiles) if p["name"] == target)
    v1, _ = column_values(cleaned_rows, j1)
    data1 = out_dir / "figure_data_1.csv"
    with open(data1, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([target])
        for x in v1:
            w.writerow([repr(x)])

    # 图 2 数据：前两个数值列散点（两列均非缺失的行）
    v2x, v2y, names2 = [], [], None
    if len(numeric_cols) >= 2:
        c1, c2 = numeric_cols[0], numeric_cols[1]
        jx = profiles.index(c1)
        jy = profiles.index(c2)
        names2 = (c1["name"], c2["name"])
        for row in cleaned_rows:
            a = row[jx] if jx < len(row) else ""
            b = row[jy] if jy < len(row) else ""
            if a == "" or b == "":
                continue
            ka, va = parse_number(a)
            kb, vb = parse_number(b)
            if ka in ("int", "float") and kb in ("int", "float"):
                v2x.append(float(va))
                v2y.append(float(vb))
        data2 = out_dir / "figure_data_2.csv"
        with open(data2, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(names2))
            for a, b in zip(v2x, v2y):
                w.writerow([repr(a), repr(b)])

    fig_entries = [
        {"index": 1, "kind": "histogram", "column": target,
         "data_csv": str(data1), "data_rows": len(v1),
         "title": f"Histogram of {target}"},
    ]
    if names2:
        fig_entries.append(
            {"index": 2, "kind": "scatter", "x": names2[0], "y": names2[1],
             "data_csv": str(out_dir / "figure_data_2.csv"), "data_rows": len(v2x),
             "title": f"{names2[1]} vs {names2[0]}"})

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        have_mpl = True
    except Exception:
        have_mpl = False

    if have_mpl:
        for fe in fig_entries:
            png = out_dir / f"figure_{fe['index']}.png"
            if fe["kind"] == "histogram":
                plt.figure()
                plt.hist(v1, bins="auto", edgecolor="black")
                plt.xlabel(fe["column"])
                plt.ylabel("count")
                plt.title(fe["title"])
            else:
                plt.figure()
                plt.scatter(v2x, v2y, s=12, alpha=0.7)
                plt.xlabel(fe["x"])
                plt.ylabel(fe["y"])
                plt.title(fe["title"])
            plt.tight_layout()
            plt.savefig(png, dpi=110)
            plt.close()
            fe["png"] = str(png)
            run_log.append(f"figure_{fe['index']}.png written ({fe['data_rows']} points)")
    else:
        anomalies.append({"kind": "figure_degraded",
                          "detail": "matplotlib 不可用：未生成 PNG，已输出 figures_spec.json "
                                    "与 figure_data CSV（绘图值完整保留）"})
        log_err("matplotlib unavailable; degraded to figure spec JSON")
        write_json(out_dir / "figures_spec.json", {"figures": fig_entries,
                                                   "note": "matplotlib 不可用时的降级图形规格"})
        run_log.append("figures degraded: spec+json only")

    manifest["figures"] = fig_entries
    write_json(out_dir / "figures_manifest.json", manifest)
    return manifest


# --------------------------------------------------------------------------- #
# 契约字段映射
# --------------------------------------------------------------------------- #
def map_contract_field(field):
    """归一化匹配契约字段到内部产物名；失败返回 None。"""
    norm = normalize_name(field)
    if not norm:
        return None
    for key, artifact in CONTRACT_MAP:
        if norm == key:
            return artifact
    for key, artifact in CONTRACT_MAP:
        if len(key) >= 3 and (norm.startswith(key) or key in norm or norm in key):
            return artifact
    return None


# --------------------------------------------------------------------------- #
# run 子命令
# --------------------------------------------------------------------------- #
def cmd_run(args):
    started = utcnow()
    anomalies = []
    run_log = [f"engine {ENGINE_VERSION} run started {started}"]
    input_dir, work_dir, output_dir = Path(args.input), Path(args.work), Path(args.output)
    if not input_dir.is_dir():
        log_err(f"--input 目录不存在: {input_dir}")
        return 2
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 规则
    rules = dict(DEFAULT_RULES)
    if args.rules:
        try:
            user_rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
            rules.update(user_rules)
            run_log.append(f"rules loaded from {args.rules}")
        except Exception as e:
            anomalies.append({"kind": "rules_error", "detail": f"rules 文件解析失败，使用默认规则: {e}"})
            log_err(f"rules file error: {e}")
    missing_tokens = set(rules.get("missing_tokens", DEFAULT_MISSING_TOKENS))

    artifacts = []  # {path, sha256, kind} 供 verify 复核

    # a. 清点 + case.json + task.md
    inv = inventory(input_dir, anomalies)
    case_id, contract = read_case_json(input_dir, anomalies)
    task_text = read_task_md(input_dir, anomalies)
    run_log.append(f"inventory: {len(inv)} files; contract fields: {len(contract)}")

    # b/c/d. CSV 处理
    csv_files = sorted([p for p in input_dir.rglob("*")
                        if p.is_file() and p.suffix.lower() == ".csv"])
    if not csv_files:
        anomalies.append({"kind": "no_csv_found", "detail": "输入中未发现 CSV 文件"})
        run_log.append("no csv found")
    stats_obj = {
        "generated_utc": utcnow(),
        "std_label": "std_ddof1 (sample standard deviation)",
        "quantile_method": "type-7 linear interpolation (numpy default)",
        "missing_policy": ("listwise_delete" if rules.get("listwise_delete_missing")
                           else "rows_with_missing_kept_as_null"),
        "files": {},
    }
    row_reconciliation = {}
    cleaned_infos = []
    profiles_by_file = {}
    for path in csv_files:
        fname = path.name
        header, rows, meta = read_csv_tolerant(path, anomalies)
        if header is None:
            continue
        profiles = profile_columns(header, rows, missing_tokens, rules)
        profiles_by_file[fname] = {"header": header, "profiles": profiles,
                                   "raw_rows": len(rows), "meta": meta}
        n_missing_total = sum(p["n_missing"] for p in profiles)
        if n_missing_total:
            miss_detail = {p["name"]: p["n_missing"] for p in profiles if p["n_missing"]}
            anomalies.append({"kind": "missing_token",
                              "detail": f"{fname}: 缺失标记计数（置 null，行保留）{miss_detail}"})
        c_header, c_rows, n_dup, _cf = clean_rows(
            header, rows, profiles, missing_tokens, rules, anomalies, fname)
        cleaned_path = work_dir / f"cleaned_{fname}"
        write_cleaned_csv(cleaned_path, c_header, c_rows)
        artifacts.append({"path": str(cleaned_path), "sha256": sha256_file(cleaned_path),
                          "kind": "cleaned_csv"})
        row_reconciliation[fname] = {
            "raw_rows": len(rows),
            "after_missing_rows_kept": len(rows),
            "duplicates_removed": n_dup,
            "final_rows": len(c_rows),
            "missing_policy": stats_obj["missing_policy"],
        }
        fs = compute_statistics(f"cleaned_{fname}", fname, c_header, c_rows, profiles, rules)
        stats_obj["files"][f"cleaned_{fname}"] = fs
        cleaned_infos.append({"source": fname, "path": str(cleaned_path),
                              "sha256": sha256_file(cleaned_path), "rows": len(c_rows),
                              "header": c_header, "rows_data": c_rows, "profiles": profiles})
        run_log.append(f"csv {fname}: raw={len(rows)} dup_removed={n_dup} final={len(c_rows)}")

    stats_json_path = output_dir / "statistics.json"
    write_json(stats_json_path, stats_obj)
    artifacts.append({"path": str(stats_json_path), "sha256": sha256_file(stats_json_path),
                      "kind": "statistics"})
    stats_md_path = output_dir / "statistics.md"
    write_text(stats_md_path, stats_to_markdown(stats_obj))
    artifacts.append({"path": str(stats_md_path), "sha256": sha256_file(stats_md_path),
                      "kind": "statistics_md"})

    # e. SQLite
    db_files = sorted([p for p in input_dir.rglob("*")
                       if p.is_file() and p.suffix.lower() in (".db", ".sqlite", ".sqlite3")])
    db_survey = {}
    for db in db_files:
        db_survey[db.name] = survey_sqlite(db, anomalies)
        run_log.append(f"db {db.name}: {len(db_survey[db.name]['tables'])} tables")
    if not db_files:
        run_log.append("no sqlite database found")
    query_results = []
    if args.sql:
        query_results = run_sql_file(args.sql, db_files, output_dir, anomalies, run_log)
        for qm in query_results:
            if "csv" in qm:
                artifacts.append({"path": qm["csv"], "sha256": qm["csv_sha256"],
                                  "kind": "query_result"})

    # f. 图形（仅第一个 CSV）
    figures_manifest = None
    if cleaned_infos:
        first = cleaned_infos[0]
        figures_manifest = make_figures(first["source"], first["header"],
                                        first["rows_data"], first["profiles"],
                                        output_dir, anomalies, run_log)
        for fe in figures_manifest.get("figures", []):
            artifacts.append({"path": fe["data_csv"], "sha256": sha256_file(fe["data_csv"]),
                              "kind": "figure_data"})
            if "png" in fe:
                artifacts.append({"path": fe["png"], "sha256": sha256_file(fe["png"]),
                                  "kind": "figure_png"})
        artifacts.append({"path": str(output_dir / "figures_manifest.json"),
                          "sha256": sha256_file(output_dir / "figures_manifest.json"),
                          "kind": "figures_manifest"})
        spec_path = output_dir / "figures_spec.json"
        if spec_path.exists():
            artifacts.append({"path": str(spec_path), "sha256": sha256_file(spec_path),
                              "kind": "figures_spec"})

    finished = utcnow()
    provenance = {
        "input_hashes": inv,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "started_utc": started,
        "finished_utc": finished,
        "engine_version": ENGINE_VERSION,
        "rules_used": rules,
        "deterministic": True,
        "rng_used": False,
    }

    # g. result.json（契约字段映射 + 诚实 partial）
    field_values = {
        "case_id": case_id,
        "cleaned_table": {"files": [{k: ci[k] for k in ("source", "path", "sha256", "rows")}
                                    for ci in cleaned_infos],
                          "note": "清洗后 CSV 位于 work 目录；缺失为 null（空字符串）"},
        "statistics": {"path": str(stats_json_path),
                       "sha256": sha256_file(stats_json_path),
                       "md_path": str(stats_md_path)},
        "figures": (figures_manifest or {"figures": []}),
        "queries": query_results,
        "provenance": provenance,
        "anomalies": anomalies,
        "row_reconciliation": row_reconciliation,
        "run_log": run_log,
        "status": None,  # 下方填充
    }
    result = {"case_id": case_id, "status": None}
    missing_fields = []
    for field in contract:
        artifact = map_contract_field(field)
        if artifact is None:
            result[field] = None
            missing_fields.append({
                "field": field,
                "reason": "engine 无法将该契约字段映射到任何已生成产物；"
                          "需人工裁决后补充（勿伪造数值）"})
            anomalies.append({"kind": "unmapped_contract_field",
                              "detail": f"契约字段 '{field}' 无法自动映射"})
        else:
            result[field] = field_values[artifact]
    status = "complete" if not missing_fields else "partial"
    result["status"] = status
    if "status" in [normalize_name(f) for f in contract]:
        for field in contract:
            if map_contract_field(field) == "status":
                result[field] = status
    result["anomalies"] = anomalies
    result["missing_fields"] = missing_fields
    result["provenance"] = provenance
    result["change_records"] = [{
        "record_id": 1, "action": "engine_initial_fill", "timestamp_utc": finished,
        "detail": "引擎一次性生成全部可推断产物与 result.json 骨架；"
                  "后续人工裁决请以追加 change_records 的方式记录"}]
    result["artifacts"] = artifacts
    result["db_survey"] = db_survey
    result["row_reconciliation"] = row_reconciliation
    result["run_log"] = run_log

    result_path = output_dir / "result.json"
    write_json(result_path, result)
    run_log.append(f"result.json written: status={status}, "
                   f"missing_fields={[m['field'] for m in missing_fields]}")
    write_json(result_path, result)  # 重写以含最终 run_log
    write_text(work_dir / "run_log.txt", "\n".join(run_log) + "\n")

    # h. engine_report.md
    report = build_report(case_id, status, inv, task_text, profiles_by_file,
                          row_reconciliation, stats_obj, db_survey, query_results,
                          figures_manifest, contract, missing_fields, anomalies,
                          provenance, args)
    write_text(work_dir / "engine_report.md", report)

    print(f"[case_engine] run finished: status={status}, "
          f"anomalies={len(anomalies)}, missing_fields={len(missing_fields)}")
    return 0


def build_report(case_id, status, inv, task_text, profiles_by_file, row_recon,
                 stats_obj, db_survey, query_results, figures_manifest, contract,
                 missing_fields, anomalies, provenance, args):
    L = []
    L.append("# engine_report — 引擎执行报告")
    L.append("")
    L.append(f"- case_id: `{case_id}`")
    L.append(f"- status: **{status}**（complete = 契约字段全部可填充；partial = 存在待人工裁决字段）")
    L.append(f"- engine_version: {ENGINE_VERSION}；python: {provenance['python_version']}；"
             f"时间(UTC): {provenance['started_utc']} → {provenance['finished_utc']}")
    L.append("")
    L.append("## 1. 输入清点（sha256）")
    L.append("")
    L.append("| file | size_bytes | sha256(前16) |")
    L.append("|---|---|---|")
    for rel, meta in inv.items():
        L.append(f"| {rel} | {meta['size_bytes']} | {meta['sha256'][:16]}… |")
    L.append("")
    L.append("## 2. 任务文本（前 200 行已读入）")
    L.append("")
    L.append("```")
    L.append(task_text[:2000] if task_text else "（task.md 缺失）")
    L.append("```")
    L.append("")
    L.append("## 3. 数据画像与清洗")
    for fname, info in profiles_by_file.items():
        L.append("")
        L.append(f"### {fname}（编码 {info['meta']['encoding']}，分隔符 "
                 f"`{info['meta']['delimiter']}`，原始 {info['raw_rows']} 行）")
        L.append("")
        L.append("| column | type | n_observed | n_missing | distinct | coercion_failures |")
        L.append("|---|---|---|---|---|---|")
        for p in info["profiles"]:
            L.append(f"| {p['name']} | {p['type']} | {p['n_observed']} | "
                     f"{p['n_missing']} | {p['distinct']} | {p['n_coercion_failures']} |")
        rr = row_recon.get(fname, {})
        L.append("")
        L.append(f"行对账：raw_rows={rr.get('raw_rows')} → "
                 f"after_missing_rows_kept={rr.get('after_missing_rows_kept')} → "
                 f"duplicates_removed={rr.get('duplicates_removed')} → "
                 f"final_rows={rr.get('final_rows')}（缺失策略：{rr.get('missing_policy')}）")
    L.append("")
    L.append("## 4. 统计要点（全量见 output/statistics.json 与 statistics.md）")
    for fname, fs in stats_obj["files"].items():
        L.append(f"- `{fname}`：{fs['rows']} 行；目标列猜测 = "
                 f"`{fs['target_column_guess']}`；"
                 f"std 口径 ddof=1；分位数 type-7。")
        for cname, st in list(fs["columns"].items())[:6]:
            if st.get("type") in ("int", "float") and st.get("n", 0) > 0:
                L.append(f"  - {cname}: n={st['n']}, mean={st['mean']:.6g}, "
                         f"std={st['std_ddof1']:.6g}, range=[{st['min']:.6g}, {st['max']:.6g}], "
                         f"outliers_iqr={st['outliers_iqr']}")
        gb = fs.get("groupby")
        if gb and gb.get("skipped"):
            L.append(f"  - group-by 跳过：{gb['reason']}")
    L.append("")
    if db_survey:
        L.append("## 5. 数据库调查与查询")
        for dbn, sv in db_survey.items():
            L.append(f"- `{dbn}`：" +
                     "；".join(f"{t['name']}({t['row_count']}行)" for t in sv["tables"]))
        for qm in query_results:
            L.append(f"- SQL #{qm['index']}: rows_returned={qm.get('rows_returned')}, "
                     f"duration_ms={qm.get('duration_ms')}, csv={qm.get('csv')}"
                     + (f", ERROR={qm['error']}" if "error" in qm else ""))
        L.append("")
    L.append("## 6. 图形")
    if figures_manifest:
        for fe in figures_manifest.get("figures", []):
            L.append(f"- figure_{fe['index']}（{fe['kind']}）：data={fe['data_csv']} "
                     f"({fe['data_rows']} 行)，png={fe.get('png', '未生成（见 figures_spec.json）')}")
    else:
        L.append("- 无 CSV，未生成图形。")
    L.append("")
    L.append("## 7. 待人工裁决的歧义（必须逐条处理）")
    L.append("")
    if missing_fields:
        for m in missing_fields:
            L.append(f"- [ ] 契约字段 `{m['field']}`：{m['reason']}")
    else:
        L.append("- 契约字段全部映射成功，无 missing_fields。")
    for fname, fs in stats_obj["files"].items():
        tg = fs.get("target_column_guess")
        if tg:
            L.append(f"- [ ] 目标列猜测 `{tg}`（{fname}）：请对照 task.md 确认是否为任务所指目标；"
                     f"若错误，group-by 与直方图需重判。")
        else:
            L.append(f"- [ ] {fname}：未找到 class|target|label|类别|强度|strength 模式的目标列。")
        for p in profiles_by_file.get(fs["source"], {}).get("profiles", []):
            if p["type"] in ("int", "float") and TARGET_PATTERN.search(p["name"]) \
                    and not UNIT_HINTS.search(p["name"]):
                L.append(f"- [ ] 单位存疑：列 `{p['name']}` 疑似强度/目标列但列名未含单位，"
                         f"请核对数据字典。")
    L.append("")
    L.append("## 8. 异常清单（anomalies）")
    L.append("")
    if anomalies:
        for a in anomalies:
            L.append(f"- `{a['kind']}`: {a['detail']}")
    else:
        L.append("- 无异常。")
    L.append("")
    L.append("## 9. Agent 下一步清单")
    L.append("")
    L.append("1. 逐条裁决第 7 节歧义；对 `missing_fields` 中的字段，"
             "从 task.md 与数据字典推断或明确标注无法推断的原因，"
             "并将裁决追加到 result.json 的 `change_records`。")
    L.append("2. 若 task.md 指定了具体 SQL/统计口径而引擎未执行，"
             "补充后以 `--sql file.sql` 或 `--rules rules.json` 重跑引擎。")
    L.append("3. 运行 `python3 /skills/weekly-skill/scripts/case_engine.py verify "
             "--input /input --work /app/work --output /app/output` 做双通道复核，"
             "必须全部 PASS。")
    L.append("4. 确认 result.json 含 case_id、全部契约字段、status、anomalies、"
             "provenance（含输入 sha256）、change_records。")
    L.append("5. 交付前不得改动已核验数值；任何手工修改须记录并重新 verify。")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# verify 子命令（独立代码路径：纯 csv.reader 循环重算）
# --------------------------------------------------------------------------- #
def cmd_verify(args):
    input_dir, work_dir, output_dir = Path(args.input), Path(args.work), Path(args.output)
    if not input_dir.is_dir():
        log_err(f"--input 目录不存在: {input_dir}")
        return 2
    checks = []  # (name, ok, detail)

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))

    stats_path = output_dir / "statistics.json"
    stats_obj = None
    if stats_path.exists():
        try:
            stats_obj = json.loads(stats_path.read_text(encoding="utf-8"))
            check("statistics.json 可解析", True)
        except Exception as e:
            check("statistics.json 可解析", False, str(e))
    else:
        check("statistics.json 存在", False, f"{stats_path} 不存在")

    # 1. 双通道重算 n/mean/std（纯 python 循环，不调用 run 的统计函数）
    if stats_obj:
        for cleaned_name, fs in stats_obj.get("files", {}).items():
            cpath = work_dir / cleaned_name
            if not cpath.exists():
                check(f"{cleaned_name} 存在", False, "cleaned CSV 缺失")
                continue
            with open(cpath, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            header = rows[0] if rows else []
            body = rows[1:] if len(rows) > 1 else []
            for cname, st in fs.get("columns", {}).items():
                if st.get("type") not in ("int", "float") or st.get("n", 0) == 0:
                    continue
                if cname not in header:
                    check(f"{cleaned_name}:{cname} 列存在", False)
                    continue
                j = header.index(cname)
                vals = []
                bad = 0
                for r in body:
                    cell = r[j] if j < len(r) else ""
                    if cell == "":
                        continue
                    try:
                        vals.append(float(cell))
                    except ValueError:
                        bad += 1
                n2 = len(vals)
                mean2 = (sum(vals) / n2) if n2 else None
                if n2 and n2 > 1:
                    var = 0.0
                    for x in vals:
                        var += (x - mean2) * (x - mean2)
                    std2 = math.sqrt(var / (n2 - 1))
                else:
                    std2 = 0.0 if n2 == 1 else None
                ok_n = (n2 == st["n"])
                check(f"{cleaned_name}:{cname} n", ok_n,
                      f"verify={n2} recorded={st['n']}" + (f" unparsed={bad}" if bad else ""))
                for key, v2 in (("mean", mean2), ("std_ddof1", std2)):
                    v1 = st.get(key)
                    if v1 is None or v2 is None:
                        check(f"{cleaned_name}:{cname} {key}", v1 == v2,
                              f"verify={v2} recorded={v1}")
                        continue
                    tol = 1e-9 + 1e-9 * max(abs(v1), abs(v2))
                    check(f"{cleaned_name}:{cname} {key}", abs(v1 - v2) <= tol,
                          f"verify={v2!r} recorded={v1!r}")

    # 2. 图形数据行数与 manifest 一致
    manifest_path = output_dir / "figures_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for fe in manifest.get("figures", []):
                dpath = Path(fe["data_csv"])
                if not dpath.exists():
                    check(f"figure_data_{fe['index']} 存在", False)
                    continue
                with open(dpath, newline="", encoding="utf-8") as f:
                    n_rows = max(0, len(list(csv.reader(f))) - 1)
                check(f"figure_data_{fe['index']} 行数",
                      n_rows == fe["data_rows"],
                      f"csv={n_rows} manifest={fe['data_rows']}")
        except Exception as e:
            check("figures_manifest.json 可解析", False, str(e))

    # 3. result.json 契约完整性 + 产物哈希
    result_path = output_dir / "result.json"
    if not result_path.exists():
        check("result.json 存在", False)
        print_summary(checks)
        return 1
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        check("result.json 可解析", True)
    except Exception as e:
        check("result.json 可解析", False, str(e))
        print_summary(checks)
        return 1

    case_id = result.get("case_id")
    check("result.json 含 case_id", case_id is not None, f"case_id={case_id}")
    case_json = input_dir / "case.json"
    contract = []
    if case_json.exists():
        try:
            cj = json.loads(case_json.read_text(encoding="utf-8"))
            oc = cj.get("output_contract", [])
            contract = [str(k) for k in (oc.keys() if isinstance(oc, dict) else oc)]
            if cj.get("case_id") is not None:
                check("case_id 与 case.json 一致", case_id == cj.get("case_id"),
                      f"result={case_id} case.json={cj.get('case_id')}")
        except Exception as e:
            check("case.json 可解析", False, str(e))
    for field in contract:
        check(f"契约字段 '{field}' 存在", field in result,
              "缺失" if field not in result else
              ("值为 null（须见 missing_fields 说明）" if result[field] is None else "已填充"))
    for mf in result.get("missing_fields", []):
        check(f"missing_fields['{mf.get('field')}'] 有原因说明",
              bool(mf.get("reason")), mf.get("reason", ""))

    for art in result.get("artifacts", []):
        p = Path(art["path"])
        if not p.exists():
            check(f"产物存在 {p.name}", False, art["path"])
            continue
        h = sha256_file(p)
        check(f"产物哈希 {p.name}", h == art["sha256"],
              "" if h == art["sha256"] else f"recorded={art['sha256'][:16]} actual={h[:16]}")

    # 4. 输入哈希一致（若输入仍可访问）
    for rel, meta in result.get("provenance", {}).get("input_hashes", {}).items():
        p = input_dir / rel
        if p.exists():
            check(f"输入哈希未变 {rel}", sha256_file(p) == meta["sha256"])
        else:
            check(f"输入文件仍存在 {rel}", False, "verify 时输入缺失")

    return print_summary(checks)


def print_summary(checks):
    n_fail = sum(1 for _, ok, _ in checks if not ok)
    print(f"[case_engine] verify summary: {len(checks) - n_fail}/{len(checks)} PASS, "
          f"{n_fail} FAIL")
    return 0 if n_fail == 0 else 1


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(prog="case_engine",
                                 description="确定性科研数据分析引擎（stdlib-only）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("--input", required=True)
        sp.add_argument("--work", required=True)
        sp.add_argument("--output", required=True)
        if name == "run":
            sp.add_argument("--rules", default=None, help="可选 rules.json 覆盖默认清洗规则")
            sp.add_argument("--sql", default=None, help="可选 SQL 文件（按 ; 切分逐条执行）")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "run":
            return cmd_run(args)
        return cmd_verify(args)
    except Exception as e:  # 兜底：任何未预期异常都诚实报告但不静默
        log_err(f"未预期异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
