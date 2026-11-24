#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline_a — dataset-veritas-gate 一键 baseline 管线（仅标准库）。

子命令：
  run      --input-dir /input --work-dir /app/work --output-dir /app/output
             全流程：来源审计 → 清洗（确定性账本）→ 描述 → 假设门控推断 →
             效应量+CI → 解释草稿 → result.json + report.md + digest.md
  decide   --work-dir W --output-dir O --key K --value V --reason R
             记录一条人工裁决（覆盖 digest.md 中的默认值）
  finalize --work-dir W --output-dir O
             应用全部裁决，确定性重跑并重写交付物

设计铁律：
  * 任何失败都写出诚实的 result.json（status=partial/failed + exceptions），绝不静默。
  * 不预制答案：所有数字均由本进程从原始输入真实计算。
"""
import argparse
import csv
import datetime
import hashlib
import itertools
import json
import math
import os
import platform
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_a as sc

MISSING_TOKENS = ("", "na", "n/a", "nan", "null", "-", "none")
ENCODING_CANDIDATES = ("utf-8-sig", "gbk", "latin-1")
DELIMITER_CANDIDATES = (",", ";", "\t", "|")
GROUP_NAME_HINTS = ("group", "class", "species", "cultivar", "treatment",
                    "condition", "cohort", "arm", "age", "sex", "gender",
                    "category", "label", "batch", "组", "类别")
ID_NAME_HINTS = ("id", "index", "idx", "no", "num", "编号", "序号")

# 已知数据集指纹（软核对：只做提示，绝不硬拒绝）
FINGERPRINTS = {
    (1030, 9): {
        "dataset": "UCI Concrete Compressive Strength",
        "keywords": ["concrete", "混凝土"],
        "columns": ["cement", "slag", "ash", "water", "superplastic",
                    "coarseagg", "fineagg", "age", "strength"],
        "units": {"cement": "kg/m3", "slag": "kg/m3", "ash": "kg/m3",
                  "water": "kg/m3", "superplastic": "kg/m3",
                  "coarseagg": "kg/m3", "fineagg": "kg/m3",
                  "age": "天", "strength": "MPa"},
    },
    (150, 5): {
        "dataset": "Iris (Fisher 1936 / Bezdek)",
        "keywords": ["iris", "鸢尾"],
        "columns": ["sepal_length", "sepal_width", "petal_length",
                    "petal_width", "class"],
        "units": {"sepal_length": "cm", "sepal_width": "cm",
                  "petal_length": "cm", "petal_width": "cm"},
    },
    (178, 14): {
        "dataset": "UCI Wine",
        "keywords": ["wine", "葡萄"],
        "columns": ["class", "alcohol", "malic_acid", "ash",
                    "alcalinity_of_ash", "magnesium", "total_phenols",
                    "flavanoids", "nonflavanoid_phenols", "proanthocyanins",
                    "color_intensity", "hue", "od280_od315", "proline"],
        "units": {},
    },
}


# ==================================================================
# 通用工具
# ==================================================================

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_missing(cell):
    if cell is None:
        return True
    return str(cell).strip().lower() in MISSING_TOKENS


def try_float(cell):
    if cell is None:
        return None
    s = str(cell).strip()
    if is_missing(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_p(p):
    if p is None or p != p:
        return "NA"
    if p < 0.0001:
        return "<0.0001"
    return f"{p:.4f}"


def fmt_num(x, nd=4):
    if x is None or (isinstance(x, float) and x != x):
        return "NA"
    return f"{x:.{nd}f}"


def row_hash(cells):
    """清洗后单行内容哈希（单元格用 \\x1f 连接，避免分隔符歧义）。"""
    return hashlib.sha256("\x1f".join(cells).encode("utf-8")).hexdigest()


# ==================================================================
# CSV / SQLite 数据接入
# ==================================================================

def sniff_encoding(raw):
    for enc in ENCODING_CANDIDATES:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1"


def sniff_delimiter(text):
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(DELIMITER_CANDIDATES))
        return dialect.delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: first.count(d) for d in DELIMITER_CANDIDATES}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def detect_header(rows):
    """有表头判定：存在至少一列——首行不可解析为数值、而 ≥90% 数据行可解析。"""
    if len(rows) < 2:
        return False
    first, rest = rows[0], rows[1:]
    ncols = max(len(r) for r in rows)
    for j in range(min(len(first), ncols)):
        col = [r[j] for r in rest if j < len(r) and not is_missing(r[j])]
        if not col:
            continue
        n_num = sum(1 for c in col if try_float(c) is not None)
        if n_num >= 0.9 * len(col) and try_float(first[j]) is None:
            return True
    return False


def read_csv_table(path):
    """读取 CSV，返回 dict(encoding, delimiter, has_header, header, rows)。
    rows 为原始字符串矩阵（不含表头），缺失 token 原样保留。"""
    with open(path, "rb") as f:
        raw = f.read()
    enc = sniff_encoding(raw)
    text = raw.decode(enc)
    delim = sniff_delimiter(text)
    rows = [r for r in csv.reader(text.splitlines(), delimiter=delim)]
    rows = [r for r in rows if any(not is_missing(c) for c in r)]
    has_header = detect_header(rows)
    header = None
    if has_header and rows:
        header = [c.strip() for c in rows[0]]
        rows = rows[1:]
    return {"encoding": enc, "delimiter": delim, "has_header": has_header,
            "header": header, "rows": rows}


def sqlite_affinity(decl_type):
    """SQLite 列 affinity 规则（官方文档 §3.1）。"""
    t = (decl_type or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in t or t == "":
        return "BLOB"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def normalize_db_cell(v):
    """SQLite 值规范化成字符串（与 CSV 口径对齐）。"""
    if v is None:
        return ""
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return repr(v)
    return str(v)


def read_sqlite_table(path):
    """读取 SQLite 第一个用户表。返回 dict(table, columns, rows)。
    columns: [{name, decl_type, affinity}]；rows 为规范化字符串矩阵。"""
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if not tables:
            return {"table": None, "columns": [], "rows": [], "all_tables": []}
        tname = tables[0]
        cols = []
        for cid, name, decl, notnull, dflt, pk in cur.execute(f'PRAGMA table_info("{tname}")'):
            cols.append({"name": name, "decl_type": decl or "", "affinity": sqlite_affinity(decl)})
        raw_rows = cur.execute(f'SELECT * FROM "{tname}"').fetchall()
        rows = [[normalize_db_cell(v) for v in r] for r in raw_rows]
        return {"table": tname, "columns": cols, "rows": rows, "all_tables": tables}
    finally:
        conn.close()


def assign_column_names(n_cols, n_rows, header, task_text):
    """列名解析：表头 > 已知指纹（仅无表头且形状唯一匹配）> c0..cN。"""
    if header:
        return header, "csv_header"
    hits = [fp for shape, fp in FINGERPRINTS.items() if shape == (n_rows, n_cols)]
    if len(hits) == 1:
        return list(hits[0]["columns"]), "fingerprint_hint"
    return [f"c{j}" for j in range(n_cols)], "positional"


# ==================================================================
# 清洗（确定性规则，供 ledger_gate 重放）
# ==================================================================

def dedupe_keep_first(rows):
    """完全重复剔除（keep-first）。返回 (kept[(raw_idx, row)], dropped[raw_idx])。
    raw_idx 为 0 起的数据行号。"""
    seen = {}
    kept, dropped = [], []
    for i, r in enumerate(rows):
        key = tuple((c.strip() if isinstance(c, str) else c) for c in r)
        if key in seen:
            dropped.append(i)
        else:
            seen[key] = i
            kept.append((i, r))
    return kept, dropped


def iqr_fences(values):
    q1 = sc.vquantile(values, 0.25)
    q3 = sc.vquantile(values, 0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def flag_outliers(rows, col_specs):
    """对数值列做 1.5×IQR 栅栏标记（只标记不删除）。
    返回 {col_name: {"fences":[lo,hi], "flagged_rows":[cleaned_row_idx,...]}}"""
    out = {}
    for j, spec in enumerate(col_specs):
        if not spec["is_numeric"]:
            continue
        vals = []
        for i, r in enumerate(rows):
            v = try_float(r[j]) if j < len(r) else None
            vals.append(v)
        valid = [v for v in vals if v is not None]
        if len(valid) < 4:
            continue
        lo, hi = iqr_fences(valid)
        flagged = [i for i, v in enumerate(vals) if v is not None and (v < lo or v > hi)]
        out[spec["name"]] = {"fences": [lo, hi], "flagged_rows": flagged}
    return out


# ==================================================================
# 列画像与分组列选择
# ==================================================================

def profile_columns(header, rows):
    specs = []
    n = len(rows)
    for j, name in enumerate(header):
        cells = [(r[j] if j < len(r) else "") for r in rows]
        valid = [c for c in cells if not is_missing(c)]
        n_missing = n - len(valid)
        nums = [try_float(c) for c in valid]
        nums_ok = [v for v in nums if v is not None]
        is_numeric = bool(valid) and len(nums_ok) >= 0.9 * len(valid)
        distinct = sorted(set(c.strip() for c in valid))
        name_l = name.strip().lower()
        id_like = (name_l in ID_NAME_HINTS or
                   (is_numeric and len(distinct) == len(valid) and len(valid) > 10 and
                    all(v == int(v) for v in nums_ok)))
        specs.append({"name": name, "index": j, "is_numeric": is_numeric,
                      "n_valid": len(valid), "n_missing": n_missing,
                      "n_distinct": len(distinct), "distinct": distinct[:25],
                      "id_like": id_like})
    return specs


def pick_group_column(specs, n_rows, override=None):
    """分组列选择。返回 (spec, reason)。"""
    if override:
        for s in specs:
            if s["name"] == override:
                return s, f"agent_override(决定: group_column={override})"
        return None, f"agent_override 指定的分组列 '{override}' 不存在"
    cands = []
    for s in specs:
        if s["id_like"] or s["n_distinct"] < 2 or s["n_distinct"] > max(20, n_rows // 2):
            continue
        name_l = s["name"].strip().lower()
        score = 0
        reasons = []
        if any(h in name_l for h in GROUP_NAME_HINTS):
            score += 4
            reasons.append("列名命中分组提示词")
        if not s["is_numeric"]:
            score += 2
            reasons.append("文本列")
        if s["n_distinct"] <= 10:
            score += 1
            reasons.append(f"唯一值数={s['n_distinct']}≤10")
        if score > 0:
            cands.append((score, -s["index"], s, "+".join(reasons)))
    if not cands:
        return None, "未找到可用分组列（唯一值数 2..20 或列名提示均未命中）"
    cands.sort(key=lambda t: (-t[0], -t[1]))
    best = cands[0]
    return best[2], f"auto(score={best[0]}: {best[3]})"


def label_sort_key(x):
    v = try_float(x)
    return (0, v, "") if v is not None else (1, 0.0, x)


# ==================================================================
# 假设门控推断
# ==================================================================

ROUTE_NAMES = {
    "GATE_2_T_STUDENT": "Student 独立样本 t（两组·正态·方差齐）",
    "GATE_2_T_WELCH": "Welch t（两组·正态·方差不齐）",
    "GATE_2_MANN_WHITNEY": "Mann-Whitney U（两组·非正态保守路线）",
    "GATE_K_ANOVA": "单因素 ANOVA（k 组·全正态·方差齐）",
    "GATE_K_WELCH_ANOVA": "Welch ANOVA（k 组·全正态·方差不齐）",
    "GATE_K_KRUSKAL": "Kruskal-Wallis（k 组·存在非正态/小样本组）",
}


def infer_variable(var_name, groups_map, alpha, raw_groups_map=None):
    """groups_map: {label: [values]}。返回推断结果 dict。"""
    labels = sorted(groups_map, key=label_sort_key)
    skipped = {lb: len(v) for lb, v in groups_map.items() if len(sc.clean(v)) < 2}
    labels = [lb for lb in labels if len(sc.clean(groups_map[lb])) >= 2]
    if len(labels) < 2:
        return {"variable": var_name, "status": "insufficient_groups",
                "note": "有效组数<2，无法做组间比较", "skipped_groups": skipped}
    groups = [sc.clean(groups_map[lb]) for lb in labels]

    # 假设检验：逐组正态性 + Levene
    normality = {}
    for lb, g in zip(labels, groups):
        if len(g) < 8:
            normality[lb] = {"n": len(g), "K2": None, "p": None,
                             "normal": False, "note": "n<8，保守按非正态处理"}
        else:
            k2, p = sc.dagostino_k2(g)
            normality[lb] = {"n": len(g), "K2": k2, "p": p,
                             "normal": bool(p is not None and p >= alpha)}
    all_normal = all(v["normal"] for v in normality.values())
    lev = None
    homogeneous = None
    if all_normal:
        w, ld1, ld2, lp = sc.levene_median(groups)
        lev = {"W": w, "df1": ld1, "df2": ld2, "p": lp}
        homogeneous = bool(lp is not None and lp >= alpha)

    k = len(labels)
    if k == 2:
        if all_normal and homogeneous:
            route = "GATE_2_T_STUDENT"
        elif all_normal:
            route = "GATE_2_T_WELCH"
        else:
            route = "GATE_2_MANN_WHITNEY"
    else:
        if all_normal and homogeneous:
            route = "GATE_K_ANOVA"
        elif all_normal:
            route = "GATE_K_WELCH_ANOVA"
        else:
            route = "GATE_K_KRUSKAL"

    res = {"variable": var_name, "status": "ok", "route": route,
           "route_name": ROUTE_NAMES[route], "alpha": alpha,
           "groups": labels, "skipped_groups": skipped,
           "assumptions": {"normality": normality, "levene": lev,
                           "all_normal": all_normal, "homogeneous": homogeneous}}

    pair_effect_kind = None
    if route == "GATE_2_T_STUDENT":
        t, df, p = sc.ttest_pooled(groups[0], groups[1])
        res.update(statistic=t, df=df, p=p, statistic_name="t")
    elif route == "GATE_2_T_WELCH":
        t, df, p = sc.ttest_welch(groups[0], groups[1])
        res.update(statistic=t, df=df, p=p, statistic_name="t")
    elif route == "GATE_2_MANN_WHITNEY":
        mw = sc.mannwhitney(groups[0], groups[1])
        res.update(statistic=mw["U"], z=mw["z"], p=mw["p"], statistic_name="U")
    elif route == "GATE_K_ANOVA":
        f, d1, d2, p, ssb, ssw = sc.anova_classic(groups)
        res.update(statistic=f, df=[d1, d2], p=p, statistic_name="F")
    elif route == "GATE_K_WELCH_ANOVA":
        f, d1, d2, p = sc.anova_welch(groups)
        res.update(statistic=f, df=[d1, d2], p=p, statistic_name="F'")
    else:
        h, df, p = sc.kruskal(groups)
        res.update(statistic=h, df=df, p=p, statistic_name="H")

    # 原始数据（未去重）经典参照：仅用于与文献/外部口径对照，不作决策依据
    if raw_groups_map is not None:
        rlabels = sorted(raw_groups_map, key=label_sort_key)
        rgroups = [sc.clean(raw_groups_map[lb]) for lb in rlabels]
        rgroups = [g for g in rgroups if len(g) >= 2]
        if len(rgroups) >= 3:
            f, d1, d2, p, _, _ = sc.anova_classic(rgroups)
            res["raw_data_reference"] = {
                "test": "classic ANOVA on RAW data（未去重，仅外部对照用，非决策依据）",
                "F": f, "df": [d1, d2], "p": p,
                "n_raw": sum(len(g) for g in rgroups)}
        elif len(rgroups) == 2:
            t, df, p = sc.ttest_pooled(rgroups[0], rgroups[1])
            res["raw_data_reference"] = {
                "test": "Student t on RAW data（未去重，仅外部对照用，非决策依据）",
                "t": t, "df": df, "p": p,
                "n_raw": sum(len(g) for g in rgroups)}

    # 非门控路线时附经典参照统计量（明确标注，不作为决策依据）
    if k >= 3 and route != "GATE_K_ANOVA":
        f, d1, d2, p, _, _ = sc.anova_classic(groups)
        res["classical_reference"] = {
            "test": "classic ANOVA (ungated reference, 非决策依据)",
            "F": f, "df": [d1, d2], "p": p}
    if k == 2 and route != "GATE_2_T_STUDENT":
        t, df, p = sc.ttest_pooled(groups[0], groups[1])
        res["classical_reference"] = {
            "test": "Student t (ungated reference, 非决策依据)",
            "t": t, "df": df, "p": p}

    # 效应量 + CI
    eff = {}
    ci = {}
    if k == 2:
        g = sc.hedges_g(groups[0], groups[1])
        eff["hedges_g"] = g
        blo, bhi, bused = sc.ci_bootstrap(sc.hedges_g, (groups[0], groups[1]))
        ci["hedges_g_bootstrap95"] = {"lo": blo, "hi": bhi, "B": bused,
                                      "seed": sc.BOOTSTRAP_SEED, "method": "percentile"}
        if route in ("GATE_2_T_STUDENT", "GATE_2_T_WELCH"):
            lo, hi, df, diff = sc.ci_welch_diff(groups[0], groups[1], alpha)
            ci["mean_diff_welch95"] = {"lo": lo, "hi": hi, "df": df, "diff": diff,
                                       "group_order": labels}
        else:
            est, lo, hi = sc.hodges_lehmann(groups[0], groups[1], alpha)
            ci["hodges_lehmann95"] = {"estimate": est, "lo": lo, "hi": hi,
                                      "group_order": labels}
            eff["rank_biserial_r"] = sc.rank_biserial(groups[0], groups[1])
    else:
        if route == "GATE_K_KRUSKAL":
            h = res.get("statistic")
            eff["epsilon_squared"] = sc.epsilon_squared_kw(h, sum(len(g) for g in groups), k)
        else:
            eff["eta_squared"] = sc.eta_squared(groups)
            eff["omega_squared"] = sc.omega_squared(groups)
        # 事后两两比较（与主检验同路线）+ Holm 校正
        pairs = []
        for a, b in itertools.combinations(range(k), 2):
            ga, gb = groups[a], groups[b]
            if route == "GATE_K_ANOVA":
                t, df, p = sc.ttest_pooled(ga, gb)
                stat_name, stat = "t", t
                e = sc.hedges_g(ga, gb)
                ename = "hedges_g"
            elif route == "GATE_K_WELCH_ANOVA":
                t, df, p = sc.ttest_welch(ga, gb)
                stat_name, stat = "t", t
                e = sc.hedges_g(ga, gb)
                ename = "hedges_g"
            else:
                mw = sc.mannwhitney(ga, gb)
                stat_name, stat, p = "U", mw["U"], mw["p"]
                e = sc.rank_biserial(ga, gb)
                ename = "rank_biserial_r"
            pairs.append({"pair": [labels[a], labels[b]], "statistic_name": stat_name,
                          "statistic": stat, "p": p, ename: e,
                          "means": [sc.vmean(ga), sc.vmean(gb)],
                          "medians": [sc.vmedian(ga), sc.vmedian(gb)]})
        adj = sc.holm([pp["p"] for pp in pairs])
        for pp, pa in zip(pairs, adj):
            pp["p_holm"] = pa
        res["pairwise"] = pairs
        res["pairwise_note"] = "与主检验同路线的两两比较，Holm 校正"
    res["effect_size"] = eff
    res["confidence_interval"] = ci
    return res


# ==================================================================
# 单位解析
# ==================================================================

def parse_units(task_text, header, fingerprint):
    """单位口径：task.md 的 name（unit）/name (unit) 模式 > 指纹提示 > unknown。"""
    units = {}
    if task_text:
        for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)[（(]([^)）]{1,20})[)）]", task_text):
            units[m.group(1)] = m.group(2).strip()
        m = re.search(r"单位[：: ]*([A-Za-zμ%/³0-9]+)", task_text)
        global_unit = m.group(1) if m else None
    else:
        global_unit = None
    out = {}
    for name in header:
        if name in units:
            out[name] = {"unit": units[name], "source": "task.md"}
        elif fingerprint and name in fingerprint.get("units", {}):
            out[name] = {"unit": fingerprint["units"][name], "source": "fingerprint_hint"}
        elif global_unit:
            out[name] = {"unit": global_unit, "source": "task.md(global)"}
        else:
            out[name] = {"unit": "unknown", "source": "none"}
    return out


# ==================================================================
# 主流程
# ==================================================================

def load_case(input_dir):
    case, task_text = {}, ""
    cj = os.path.join(input_dir, "case.json")
    if os.path.isfile(cj):
        with open(cj, "r", encoding="utf-8", errors="replace") as f:
            case = json.load(f)
    tm = os.path.join(input_dir, "task.md")
    if os.path.isfile(tm):
        with open(tm, "r", encoding="utf-8", errors="replace") as f:
            task_text = f.read()
    return case, task_text


def choose_primary(input_dir, case, overrides):
    """主数据源：默认 CSV 优先；overrides['primary_source']='db' 可覆盖。"""
    files = case.get("data_files") or sorted(os.listdir(input_dir))
    csvs = [f for f in files if f.lower().endswith((".csv", ".tsv"))
            and os.path.isfile(os.path.join(input_dir, f))]
    dbs = [f for f in files if f.lower().endswith((".db", ".sqlite", ".sqlite3"))
           and os.path.isfile(os.path.join(input_dir, f))]
    prefer_db = (overrides or {}).get("primary_source") == "db"
    if prefer_db and dbs:
        return os.path.join(input_dir, dbs[0]), "sqlite"
    if csvs:
        return os.path.join(input_dir, csvs[0]), "csv"
    if dbs:
        return os.path.join(input_dir, dbs[0]), "sqlite"
    return None, None


def build_table(path, kind, task_text):
    """把主数据源统一成 (header, rows, meta)。"""
    meta = {"source_path": path, "source_kind": kind,
            "source_sha256": sha256_file(path)}
    if kind == "csv":
        info = read_csv_table(path)
        meta.update({"encoding": info["encoding"], "delimiter": info["delimiter"],
                     "has_header": info["has_header"]})
        rows = info["rows"]
        n_cols = max((len(r) for r in rows), default=0)
        header, name_src = assign_column_names(n_cols, len(rows), info["header"], task_text)
        rows = [r + [""] * (n_cols - len(r)) for r in rows]
    else:
        info = read_sqlite_table(path)
        meta.update({"db_table": info["table"], "db_columns": info["columns"],
                     "encoding": "n/a(sqlite)", "delimiter": "n/a",
                     "has_header": True})
        rows = info["rows"]
        header = [c["name"] for c in info["columns"]]
        name_src = "sqlite_schema"
        # DB 列名为 c0..cN 这类占位名时，若形状唯一命中已知指纹则用指纹列名
        if header and all(re.fullmatch(r"c\d+", h) for h in header):
            hits = [fp for shape, fp in FINGERPRINTS.items()
                    if shape == (len(rows), len(header))]
            if len(hits) == 1:
                header = list(hits[0]["columns"])
                name_src = "fingerprint_hint"
    meta["column_name_source"] = name_src
    return header, rows, meta


def get_fingerprint(n_rows, n_cols, task_text):
    fp = FINGERPRINTS.get((n_rows, n_cols))
    if not fp:
        return None
    kw_hit = any(k in task_text for k in fp["keywords"]) if task_text else False
    out = dict(fp)
    out["keyword_hit"] = kw_hit
    return out


def clean_and_ledger(header, rows, specs, source_meta, outlier_action="flag"):
    """执行清洗并生成账本。返回 (cleaned_rows, ledger)。"""
    kept, dup_dropped = dedupe_keep_first(rows)
    post_rows = [r for _, r in kept]
    flags = flag_outliers(post_rows, specs)

    rules = [{"id": "R1", "name": "dedupe_exact_keep_first",
              "semantics": "drop", "dropped_raw_rows": dup_dropped,
              "count": len(dup_dropped)}]
    miss_per_col = {}
    for s in specs:
        j = s["index"]
        cnt = sum(1 for _, r in kept if j >= len(r) or is_missing(r[j]))
        if cnt:
            miss_per_col[s["name"]] = cnt
    rules.append({"id": "R2", "name": "missing_report_and_exclude",
                  "semantics": "per-variable exclude（不删行、不插补）",
                  "tokens": list(MISSING_TOKENS),
                  "per_column_missing": miss_per_col, "rows_dropped": 0})
    rules.append({"id": "R3", "name": "outlier_iqr_flag_only",
                  "semantics": "flag", "fence": "1.5*IQR",
                  "per_column": {k: {"fences": v["fences"],
                                     "n_flagged": len(v["flagged_rows"]),
                                     "flagged_rows": v["flagged_rows"]}
                                 for k, v in flags.items()},
                  "rows_dropped": 0})

    final_rows = post_rows
    out_dropped = []
    if outlier_action == "drop":
        flagged_set = sorted({i for v in flags.values() for i in v["flagged_rows"]})
        out_dropped = [kept[i][0] for i in flagged_set]
        final_rows = [r for i, r in enumerate(post_rows) if i not in set(flagged_set)]
        rules.append({"id": "R4", "name": "outlier_drop_by_decision",
                      "semantics": "drop", "dropped_raw_rows": out_dropped,
                      "count": len(out_dropped)})

    kept_raw = [i for i, _ in kept] if outlier_action != "drop" else \
        [kept[i][0] for i in range(len(kept)) if i not in
         {x for v in flags.values() for x in v["flagged_rows"]}]
    rows_dropped = len(rows) - len(final_rows)
    ledger = {
        "version": 1,
        "created_utc": utc_now(),
        "source_file": os.path.basename(source_meta["source_path"]),
        "source_sha256": source_meta["source_sha256"],
        "source_kind": source_meta["source_kind"],
        "rules": rules,
        "rows_raw": len(rows),
        "rows_dropped": rows_dropped,
        "rows_kept": len(final_rows),
        "closure_law": "rows_raw == rows_kept + rows_dropped",
        "kept_raw_rows": kept_raw,
        "cleaned_file": "cleaned_table.csv",
    }
    return final_rows, ledger


def write_cleaned_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if is_missing(c) else str(c).strip() for c in r])


def finalize_ledger_hashes(ledger, cleaned_path, header, rows):
    ledger["cleaned_sha256"] = sha256_file(cleaned_path)
    ledger["row_hashes"] = []
    with open(cleaned_path, "r", encoding="utf-8", newline="") as f:
        rdr = csv.reader(f)
        next(rdr, None)
        for r in rdr:
            ledger["row_hashes"].append(row_hash(r))
    return ledger


# ==================================================================
# 解释草稿（规则模板，禁止“证明”措辞）
# ==================================================================

def g_magnitude(g):
    a = abs(g)
    if a < 0.2:
        return "微小"
    if a < 0.5:
        return "小"
    if a < 0.8:
        return "中等"
    return "大"


def eta_magnitude(e):
    if e is None:
        return "NA"
    if e < 0.01:
        return "微小"
    if e < 0.06:
        return "小"
    if e < 0.14:
        return "中等"
    return "大"


def draft_interpretation(var, res, units, alpha):
    if res.get("status") != "ok":
        return f"{var}：{res.get('note', '无法推断')}。"
    p = res.get("p")
    sig = p is not None and p < alpha
    unit = units.get(var, {}).get("unit", "unknown")
    route_name = res["route_name"]
    lines = [f"【{var}】（单位：{unit}）采用 {route_name}（理由码 {res['route']}）。"]
    if sig:
        lines.append(f"组间差异在 α={alpha} 水平统计显著（p={fmt_p(p)}）。")
    else:
        lines.append(f"未观察到统计显著的组间差异（p={fmt_p(p)}，α={alpha}）；这不等于各组相同。")
    eff = res.get("effect_size", {})
    if "hedges_g" in eff and eff["hedges_g"] is not None:
        lines.append(f"Hedges g={fmt_num(eff['hedges_g'])}（{g_magnitude(eff['hedges_g'])}效应）；"
                     f"实际意义须结合单位与领域背景判断，统计显著不代表实际重要。")
    if "eta_squared" in eff and eff["eta_squared"] is not None:
        lines.append(f"η²={fmt_num(eff['eta_squared'])}（{eta_magnitude(eff['eta_squared'])}），"
                     f"ω²={fmt_num(eff.get('omega_squared'))}。")
    if "epsilon_squared" in eff and eff["epsilon_squared"] is not None:
        lines.append(f"ε²={fmt_num(eff['epsilon_squared'])}（秩方差解释比例）。")
    pairs = res.get("pairwise") or []
    sig_pairs = [pp for pp in pairs if pp.get("p_holm") is not None and pp["p_holm"] < alpha]
    if pairs:
        lines.append(f"两两比较 {len(pairs)} 对（Holm 校正后显著 {len(sig_pairs)} 对）。")
        if sig_pairs:
            big = max(sig_pairs, key=lambda pp: abs(pp["means"][0] - pp["means"][1]))
            hi, lo = (big["pair"][0], big["pair"][1]) if big["means"][0] >= big["means"][1] \
                else (big["pair"][1], big["pair"][0])
            lines.append(f"均值差最大且显著的对比：{hi} > {lo}"
                         f"（均值 {fmt_num(max(big['means']))} vs {fmt_num(min(big['means']))} {unit}）。")
    lines.append("结论为关联性证据，非因果证明。")
    return " ".join(lines)


# ==================================================================
# report / digest / result 写出
# ==================================================================

def write_report(path, ctx):
    L = []
    L.append(f"# 统计分析报告 — {ctx['case_id']}\n")
    L.append(f"生成时间（UTC）：{ctx['utc']} ｜ 状态：{ctx['status']}\n")
    L.append("## 1. 数据来源审计（source_audit 摘要）")
    audit = ctx.get("audit") or {}
    for inv in audit.get("inventory", []):
        L.append(f"- `{inv['file']}`：{inv['size']} B，sha256={inv['sha256'][:16]}…")
    for c in audit.get("csvs", []):
        L.append(f"- CSV `{c['file']}`：编码 {c['encoding']}，分隔符 {repr(c['delimiter'])}，"
                 f"表头={'有' if c['has_header'] else '无'}，数据行 {c['n_rows']}，列 {c['n_cols']}")
    for d in audit.get("dbs", []):
        for t in d.get("tables", []):
            nit = [c["name"] for c in t["columns"] if c.get("numeric_in_text")]
            L.append(f"- SQLite `{d['file']}` 表 `{t['name']}`：{t['n_rows']} 行；"
                     f"numeric-in-text 列：{', '.join(nit) if nit else '无'}")
    for cs in audit.get("cross_source", []):
        L.append(f"- 跨源一致性（{cs['csv']} ↔ {cs['db']}）：行数 {cs['rows_csv']}/{cs['rows_db']}"
                 f"（{'一致' if cs['rows_equal'] else '不一致'}），列映射 {cs['mapping_method']}，"
                 f"比对口径 {cs['compare_scope']}，值不一致单元格 {cs['n_value_mismatch']}，"
                 f"结论：**{cs['verdict']}**")
    for fp in audit.get("fingerprints", []):
        L.append(f"- 指纹软核对：{fp['dataset']}（形状命中={fp['shape_hit']}，"
                 f"关键词命中={fp['keyword_hit']}）→ {fp['verdict']}：{fp['note']}")
    for w in audit.get("warnings", []):
        L.append(f"- ⚠ {w}")
    L.append("\n## 2. 清洗账本与闭合律")
    led = ctx["ledger"]
    L.append(f"- 闭合律：rows_raw({led['rows_raw']}) == rows_kept({led['rows_kept']}) "
             f"+ rows_dropped({led['rows_dropped']}) → **{'成立' if led['rows_raw'] == led['rows_kept'] + led['rows_dropped'] else '不成立'}**")
    for r in led["rules"]:
        if r["id"] == "R1":
            L.append(f"- R1 完全重复剔除（keep-first）：剔除 {r['count']} 行")
        elif r["id"] == "R2":
            L.append(f"- R2 缺失 report_and_exclude：{r['per_column_missing'] or '无缺失'}")
        elif r["id"] == "R3":
            fl = {k: v["n_flagged"] for k, v in r["per_column"].items() if v["n_flagged"]}
            L.append(f"- R3 异常值 1.5×IQR 只标记不删除：{fl or '无标记'}")
        else:
            L.append(f"- {r['id']} {r['name']}：剔除 {r.get('count', 0)} 行（裁决触发）")
    L.append(f"- 清洗产物哈希：cleaned_table.csv sha256={led.get('cleaned_sha256', '')[:16]}…"
             f"（{len(led.get('row_hashes', []))} 行逐行哈希已入账，可被 ledger_gate 重放核验）")
    L.append(f"- ledger_gate 自检：{ctx.get('self_gate', '未运行')}")
    L.append("\n## 3. 描述统计")
    desc = ctx["result"]["descriptive"]
    L.append("| 变量 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max | 偏度 | 单位 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, d in desc.items():
        if not isinstance(d, dict) or d.get("n") is None:
            continue
        L.append(f"| {name} | {d['n']} | {fmt_num(d['mean'])} | {fmt_num(d['sd'])} | "
                 f"{fmt_num(d['median'])} | {fmt_num(d['q1'])} | {fmt_num(d['q3'])} | "
                 f"{fmt_num(d['min'])} | {fmt_num(d['max'])} | {fmt_num(d.get('skewness'))} | "
                 f"{d.get('unit', 'unknown')} |")
    L.append("\n## 4. 假设门控与推断")
    L.append(f"分组列：**{ctx['result'].get('group_column')}**（选择依据：{ctx['result'].get('group_column_reason')}）")
    ht = ctx["result"]["hypothesis_test"]
    for var, res in ht.items():
        if not isinstance(res, dict) or res.get("status") != "ok":
            L.append(f"- {var}：{(res or {}).get('note', '跳过')}")
            continue
        L.append(f"### {var}")
        L.append(f"- 路线：{res['route_name']}（理由码 `{res['route']}`）")
        L.append(f"- 统计量 {res['statistic_name']}={fmt_num(res.get('statistic'))}，"
                 f"df={res.get('df')}，p={fmt_p(res.get('p'))}，α={res['alpha']}")
        asm = res["assumptions"]
        norm_str = "；".join(f"{k}: n={v['n']} p={fmt_p(v['p'])}"
                             f"{'(正态)' if v['normal'] else '(非正态/保守)'}"
                             for k, v in asm["normality"].items())
        L.append(f"- 正态性：{norm_str}")
        if asm["levene"]:
            L.append(f"- Levene(median)：W={fmt_num(asm['levene']['W'])}，p={fmt_p(asm['levene']['p'])}")
        cr = res.get("classical_reference")
        if cr:
            stat = cr.get("F", cr.get("t"))
            L.append(f"- 非门控参照（不作决策依据）：{cr['test']} = {fmt_num(stat)}，p={fmt_p(cr['p'])}")
        rr = res.get("raw_data_reference")
        if rr:
            stat = rr.get("F", rr.get("t"))
            L.append(f"- 原始数据参照（未去重 n={rr['n_raw']}，仅外部对照）：{rr['test']} = "
                     f"{fmt_num(stat)}，p={fmt_p(rr['p'])}")
        eff = res.get("effect_size", {})
        ci = res.get("confidence_interval", {})
        eff_bits = []
        if eff.get("hedges_g") is not None:
            b = ci.get("hedges_g_bootstrap95", {})
            eff_bits.append(f"Hedges g={fmt_num(eff['hedges_g'])}"
                            f"（bootstrap95 CI [{fmt_num(b.get('lo'))}, {fmt_num(b.get('hi'))}], B={b.get('B')}）")
        if eff.get("eta_squared") is not None:
            eff_bits.append(f"η²={fmt_num(eff['eta_squared'])}，ω²={fmt_num(eff.get('omega_squared'))}")
        if eff.get("epsilon_squared") is not None:
            eff_bits.append(f"ε²={fmt_num(eff['epsilon_squared'])}")
        if eff.get("rank_biserial_r") is not None:
            eff_bits.append(f"rank-biserial r={fmt_num(eff['rank_biserial_r'])}")
        if eff_bits:
            L.append(f"- 效应量：{'；'.join(eff_bits)}")
        md = ci.get("mean_diff_welch95")
        hl = ci.get("hodges_lehmann95")
        if md:
            L.append(f"- 均值差 Welch 95%CI：[{fmt_num(md['lo'])}, {fmt_num(md['hi'])}]"
                     f"（{md['group_order'][0]}−{md['group_order'][1]}）")
        if hl:
            L.append(f"- Hodges-Lehmann 中位数差={fmt_num(hl['estimate'])}"
                     f" 95%CI [{fmt_num(hl['lo'])}, {fmt_num(hl['hi'])}]")
        if res.get("pairwise"):
            n_sig = sum(1 for pp in res["pairwise"]
                        if pp.get("p_holm") is not None and pp["p_holm"] < res["alpha"])
            L.append(f"- 两两比较 {len(res['pairwise'])} 对，Holm 校正后显著 {n_sig} 对"
                     f"（明细见 result.json）")
    L.append("\n## 5. 结果解释（草稿）")
    for var, txt in ctx["result"]["interpretation"].items():
        L.append(f"- {txt}")
    L.append("\n## 6. 不确定性、例外与限制")
    for u in ctx["result"].get("uncertainty", []):
        L.append(f"- 不确定性：{u}")
    for e in ctx["result"].get("exceptions", []):
        L.append(f"- 例外：{e}")
    for lim in ctx["result"].get("limitations", []):
        L.append(f"- 限制：{lim}")
    L.append("\n## 7. 复现信息")
    L.append(f"```json\n{json.dumps(ctx['result']['reproducibility'], ensure_ascii=False, indent=2)}\n```")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def write_digest(path, ctx, pending):
    L = [f"# digest — {ctx['case_id']}（agent 只需读本文件）", ""]
    L.append("## 发现了什么")
    led = ctx["ledger"]
    audit = ctx.get("audit") or {}
    L.append(f"- 主数据源：`{led['source_file']}`（{led['source_kind']}），"
             f"行数 {led['rows_raw']} → 清洗后 {led['rows_kept']}（重复剔除 {led['rows_dropped']} 行）")
    r2 = next((r for r in led["rules"] if r["id"] == "R2"), {})
    L.append(f"- 缺失（report_and_exclude，按变量有效 n）：{r2.get('per_column_missing') or '无'}")
    r3 = next((r for r in led["rules"] if r["id"] == "R3"), {})
    fl = {k: v["n_flagged"] for k, v in (r3.get("per_column") or {}).items() if v["n_flagged"]}
    L.append(f"- 异常值（1.5×IQR，只标记）：{fl or '无'}")
    for cs in audit.get("cross_source", []):
        L.append(f"- 跨源一致性：{cs['verdict']}（{cs['csv']} ↔ {cs['db']}，"
                 f"值不一致 {cs['n_value_mismatch']} 处）")
    nit_all = []
    for d in audit.get("dbs", []):
        for t in d.get("tables", []):
            nit_all += [c["name"] for c in t["columns"] if c.get("numeric_in_text")]
    if nit_all:
        L.append(f"- ⚠ SQLite numeric-in-text 列（TEXT affinity 存数值）：{', '.join(nit_all)}")
    for fp in audit.get("fingerprints", []):
        if fp["verdict"] != "consistent":
            L.append(f"- ⚠ 指纹软核对：{fp['note']}")
    L.append(f"- 分组列默认：{ctx['result'].get('group_column')}；推断变量数："
             f"{len(ctx['result']['hypothesis_test'])}")
    L.append("")
    L.append(f"## 待确认裁决（{len(pending)} 项；确认默认值则无需任何操作）")
    for p in pending:
        L.append(f"- **{p['key']}**：{p['topic']} ｜ 默认：`{p['default']}` ｜ 理由：{p['why']}")
        L.append(f"  - 覆盖命令：`python3 ${{SKILL_DIR}}/scripts/pipeline_a.py decide "
                 f"--work-dir /app/work --output-dir /app/output --key {p['key']} "
                 f"--value <新值> --reason \"理由\"`")
    L.append("")
    L.append("覆盖后执行：`python3 ${SKILL_DIR}/scripts/pipeline_a.py finalize "
             "--work-dir /app/work --output-dir /app/output`")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ==================================================================
# 主 run
# ==================================================================

REQUIRED_FIELDS = ["case_id", "status", "cleaning", "descriptive", "hypothesis_test",
                   "effect_size", "confidence_interval", "interpretation", "limitations"]


def run_pipeline(input_dir, work_dir, output_dir, overrides=None, agent_decisions=None):
    overrides = overrides or {}
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    exceptions = []
    uncertainty = []
    result = {k: None for k in REQUIRED_FIELDS}
    case, task_text = {}, ""
    try:
        case, task_text = load_case(input_dir)
    except Exception as e:  # noqa
        exceptions.append(f"case.json/task.md 读取失败: {e}")
    result["case_id"] = case.get("case_id", "unknown-case")

    constraints = case.get("constraints", {}) or {}
    alpha = float(overrides.get("alpha", constraints.get("alpha", 0.05)))

    # ---- 来源审计（重心 1，调用 source_audit 模块）
    audit = None
    try:
        import source_audit
        audit = source_audit.audit_input(input_dir, task_text=task_text)
        with open(os.path.join(work_dir, "source_audit.json"), "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa
        exceptions.append(f"source_audit 失败: {e}")

    # ---- 主数据源
    primary, kind = choose_primary(input_dir, case, overrides)
    if not primary:
        result["status"] = "failed"
        exceptions.append("输入目录中找不到 CSV 或 SQLite 数据文件")
        return _emit(result, exceptions, uncertainty, case, input_dir, work_dir, output_dir, None, None, [])

    try:
        header, rows, meta = build_table(primary, kind, task_text)
    except Exception as e:  # noqa
        result["status"] = "failed"
        exceptions.append(f"数据读取失败({os.path.basename(primary)}): {e}")
        return _emit(result, exceptions, uncertainty, case, input_dir, work_dir, output_dir, None, None, [])

    fingerprint = get_fingerprint(len(rows), len(header), task_text)
    if meta.get("column_name_source") == "fingerprint_hint":
        uncertainty.append("CSV 无表头，列名来自已知数据集指纹软匹配（形状唯一命中），"
                           "属提示性命名，已在 digest 中列为待确认项")

    # ---- 清洗
    specs = profile_columns(header, rows)
    outlier_action = overrides.get("outlier_action", "flag")
    final_rows, ledger = clean_and_ledger(header, rows, specs, meta, outlier_action)
    cleaned_path = os.path.join(work_dir, "cleaned_table.csv")
    write_cleaned_csv(cleaned_path, header, final_rows)
    finalize_ledger_hashes(ledger, cleaned_path, header, final_rows)
    with open(os.path.join(work_dir, "cleaning_ledger.json"), "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)

    # ---- ledger_gate 自检
    self_gate = "未运行"
    try:
        import ledger_gate
        ok, lines, violations = ledger_gate.check(input_dir, work_dir)
        self_gate = "PASS" if ok else "FAIL: " + ",".join(violations)
        if not ok:
            exceptions.append("ledger_gate 自检未通过: " + ",".join(violations))
    except Exception as e:  # noqa
        exceptions.append(f"ledger_gate 自检异常: {e}")

    # ---- 分组列与变量
    specs = profile_columns(header, final_rows)
    gspec, greason = pick_group_column(specs, len(final_rows),
                                       overrides.get("group_column"))
    units = parse_units(task_text, header, fingerprint)
    var_filter = overrides.get("variables")
    var_whitelist = set(var_filter.split(",")) if var_filter else None
    var_excl = set((overrides.get("exclude_variables") or "").split(",")) - {""}

    numeric_vars = [s for s in specs if s["is_numeric"] and not s["id_like"]
                    and (gspec is None or s["name"] != gspec["name"])]
    if var_whitelist:
        numeric_vars = [s for s in numeric_vars if s["name"] in var_whitelist]
    numeric_vars = [s for s in numeric_vars if s["name"] not in var_excl]

    # ---- 描述统计
    desc = {}
    for s in numeric_vars:
        j = s["index"]
        vals = [try_float(r[j]) for r in final_rows]
        d = sc.summarize(vals)
        if d:
            d["unit"] = units.get(s["name"], {}).get("unit", "unknown")
            d["n_missing"] = s["n_missing"]
            desc[s["name"]] = d
    result["descriptive"] = desc

    # ---- 推断
    ht, eff_all, ci_all, interp = {}, {}, {}, {}
    if gspec is None:
        ht["_global"] = {"status": "no_grouping_variable", "note": greason}
        exceptions.append(f"未识别分组列：{greason}")
        uncertainty.append("未做组间推断；可用 decide --key group_column 指定分组列后 finalize")
    else:
        gj = gspec["index"]
        for s in numeric_vars:
            j = s["index"]
            groups_map = {}
            raw_groups_map = {}
            for r in rows:  # 原始未去重数据（仅用于 raw_data_reference 外部对照）
                lb = r[gj] if gj < len(r) else ""
                if is_missing(lb):
                    continue
                v = try_float(r[j]) if j < len(r) else None
                if v is None:
                    continue
                raw_groups_map.setdefault(lb.strip(), []).append(v)
            for r in final_rows:
                lb = r[gj] if gj < len(r) else ""
                if is_missing(lb):
                    continue
                v = try_float(r[j]) if j < len(r) else None
                if v is None:
                    continue
                groups_map.setdefault(lb.strip(), []).append(v)
            try:
                res = infer_variable(s["name"], groups_map, alpha,
                                     raw_groups_map=raw_groups_map)
                ht[s["name"]] = res
                if res.get("status") == "ok":
                    eff_all[s["name"]] = res.get("effect_size", {})
                    ci_all[s["name"]] = res.get("confidence_interval", {})
                    interp[s["name"]] = draft_interpretation(s["name"], res, units, alpha)
            except Exception as e:  # noqa
                ht[s["name"]] = {"status": "error", "note": str(e)}
                exceptions.append(f"变量 {s['name']} 推断失败: {e}")
    result["group_column"] = gspec["name"] if gspec else None
    result["group_column_reason"] = greason
    result["hypothesis_test"] = ht
    result["effect_size"] = eff_all
    result["confidence_interval"] = ci_all
    result["interpretation"] = interp

    # ---- cleaning 字段
    r1 = next(r for r in ledger["rules"] if r["id"] == "R1")
    r2 = next(r for r in ledger["rules"] if r["id"] == "R2")
    r3 = next(r for r in ledger["rules"] if r["id"] == "R3")
    result["cleaning"] = {
        "rules_applied": ledger["rules"],
        "rows_raw": ledger["rows_raw"], "rows_kept": ledger["rows_kept"],
        "rows_dropped": ledger["rows_dropped"],
        "duplicates_removed": r1["count"],
        "missing_per_column": r2["per_column_missing"],
        "outliers_flagged": {k: v["n_flagged"] for k, v in r3["per_column"].items()},
        "closure_law": f"rows_raw({ledger['rows_raw']}) == rows_kept({ledger['rows_kept']}) "
                       f"+ rows_dropped({ledger['rows_dropped']})",
        "closure_holds": ledger["rows_raw"] == ledger["rows_kept"] + ledger["rows_dropped"],
        "ledger_file": "cleaning_ledger.json",
        "cleaned_sha256": ledger.get("cleaned_sha256"),
    }

    result["limitations"] = [
        "缺失按 report_and_exclude 处理（各变量有效 n 不同），未插补；若缺失非随机，结果可能有偏。",
        "异常值仅按 1.5×IQR 标记未删除（除非裁决 outlier_action=drop），重尾分布下标记率会偏高。",
        "跨源一致性为记录级核对，不构成对上游采集过程真实性的证明。",
        "推断结论为关联性证据；未控制的混杂因素不在本分析范围内。",
    ]
    if fingerprint and not fingerprint.get("keyword_hit"):
        uncertainty.append(f"数据形状像 {fingerprint['dataset']} 但 task.md 未命中关键词，请人工确认数据集身份")
    if any("numeric-in-text" in w for w in (audit or {}).get("warnings", [])):
        uncertainty.append("SQLite 存在 TEXT affinity 存数值列，已按数值解析；若原口径为字符编码需人工确认")

    return _emit(result, exceptions, uncertainty, case, input_dir, work_dir, output_dir,
                 audit, ledger, agent_decisions, meta=meta, gspec=gspec,
                 self_gate=self_gate)


def _emit(result, exceptions, uncertainty, case, input_dir, work_dir, output_dir,
          audit, ledger, agent_decisions, meta=None, gspec=None, self_gate="未运行"):
    result["exceptions"] = exceptions
    result["uncertainty"] = uncertainty
    result["status"] = "failed" if result["status"] == "failed" else \
        ("partial" if exceptions else "ok")
    # sources
    sources = []
    if audit:
        for inv in audit.get("inventory", []):
            sources.append({"file": inv["file"], "sha256": inv["sha256"],
                            "size_bytes": inv["size"]})
    elif meta:
        sources.append({"file": os.path.basename(meta["source_path"]),
                        "sha256": meta["source_sha256"]})
    result["sources"] = sources
    result["reproducibility"] = {
        "seed": sc.BOOTSTRAP_SEED, "bootstrap_B": sc.BOOTSTRAP_B,
        "python": platform.python_version(), "platform": platform.platform(),
        "generated_utc": utc_now(),
        "pipeline": "pipeline_a.py (dataset-veritas-gate, stdlib-only)",
    }
    decisions = []
    if gspec is not None:
        decisions.append({"key": "group_column", "value": gspec["name"],
                          "source": "auto", "reason": result.get("group_column_reason")})
    for d in (agent_decisions or []):
        decisions.append({"key": d["key"], "value": d["value"],
                          "source": "agent", "reason": d.get("reason", "")})
    result["decisions"] = decisions
    if audit is not None:
        result["source_audit"] = {
            "cross_source": audit.get("cross_source", []),
            "warnings": audit.get("warnings", []),
            "fingerprints": [{k: v for k, v in f.items() if k != "columns"}
                             for f in audit.get("fingerprints", [])],
        }
    # 校验 9 字段
    missing_fields = [k for k in REQUIRED_FIELDS if result.get(k) is None]
    for k in missing_fields:
        result[k] = {"status": "not_available", "note": "流程提前终止"}
    if missing_fields and result["status"] == "ok":
        result["status"] = "partial"

    with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ctx = {"case_id": result["case_id"], "utc": result["reproducibility"]["generated_utc"],
           "status": result["status"], "audit": audit, "ledger": ledger or
           {"rows_raw": 0, "rows_kept": 0, "rows_dropped": 0, "rules": []},
           "result": result, "self_gate": self_gate}
    write_report(os.path.join(output_dir, "report.md"), ctx)
    if audit:
        with open(os.path.join(output_dir, "source_audit.json"), "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
    if ledger:
        import shutil
        shutil.copyfile(os.path.join(work_dir, "cleaned_table.csv"),
                        os.path.join(output_dir, "cleaned_table.csv"))
        with open(os.path.join(output_dir, "cleaning_ledger.json"), "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)

    # 待确认裁决（≤5 项）
    pending = build_pending(result, meta, gspec)
    write_digest(os.path.join(work_dir, "digest.md"), ctx, pending)

    # 状态文件供 finalize 使用
    with open(os.path.join(work_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"input_dir": input_dir, "work_dir": work_dir,
                   "output_dir": output_dir, "case_id": result["case_id"]},
                  f, ensure_ascii=False, indent=2)
    print(f"[pipeline_a] status={result['status']} case={result['case_id']} "
          f"rows={result['cleaning'].get('rows_raw') if isinstance(result['cleaning'], dict) else '?'} "
          f"self_gate={self_gate}")
    print(f"[pipeline_a] 产物: {output_dir}/result.json, report.md; "
          f"{work_dir}/digest.md, cleaning_ledger.json, cleaned_table.csv, source_audit.json")
    print("NEXT: 阅读 /app/work/digest.md，必要时用 decide 覆盖默认裁决，然后 finalize；"
          "交付前跑 ledger_gate.py check 自检。")
    return result


def build_pending(result, meta, gspec):
    pending = []
    pending.append({"key": "group_column", "topic": "分组列选择",
                    "default": result.get("group_column"),
                    "why": result.get("group_column_reason", "")})
    pending.append({"key": "alpha", "topic": "显著性水平",
                    "default": "见 constraints（默认 0.05）",
                    "why": "来自 case.json constraints；任务另有约定时覆盖"})
    pending.append({"key": "primary_source", "topic": "主数据源（csv/db）",
                    "default": (meta or {}).get("source_kind", "csv"),
                    "why": "默认 CSV 优先；跨源不一致时可切换为 db 重跑"})
    pending.append({"key": "outlier_action", "topic": "异常值处置（flag/drop）",
                    "default": "flag",
                    "why": "默认只标记不删除；确认录入错误才可 drop 并必须写理由"})
    pending.append({"key": "variables", "topic": "推断变量白名单（逗号分隔）",
                    "default": "全部数值变量",
                    "why": "task.md 聚焦特定指标时可收窄，减少无关比较"})
    return pending[:5]


# ==================================================================
# CLI
# ==================================================================

def load_decisions(work_dir):
    p = os.path.join(work_dir, "decisions.json")
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def main():
    ap = argparse.ArgumentParser(prog="pipeline_a.py",
                                 description="dataset-veritas-gate 一键 baseline 管线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--input-dir", required=True)
    pr.add_argument("--work-dir", required=True)
    pr.add_argument("--output-dir", required=True)
    pd_ = sub.add_parser("decide")
    pd_.add_argument("--work-dir", required=True)
    pd_.add_argument("--output-dir", required=True)
    pd_.add_argument("--key", required=True)
    pd_.add_argument("--value", required=True)
    pd_.add_argument("--reason", required=True)
    pf = sub.add_parser("finalize")
    pf.add_argument("--work-dir", required=True)
    pf.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    if args.cmd == "run":
        res = run_pipeline(args.input_dir, args.work_dir, args.output_dir)
        sys.exit(0 if res.get("status") in ("ok", "partial") else 1)
    if args.cmd == "decide":
        allowed = {"group_column", "alpha", "primary_source", "outlier_action",
                   "variables", "exclude_variables"}
        if args.key not in allowed:
            print(f"[decide] 拒绝：key 必须为 {sorted(allowed)} 之一")
            sys.exit(1)
        os.makedirs(args.work_dir, exist_ok=True)
        ds = load_decisions(args.work_dir)
        ds = [d for d in ds if d["key"] != args.key]
        ds.append({"key": args.key, "value": args.value,
                   "reason": args.reason, "utc": utc_now()})
        with open(os.path.join(args.work_dir, "decisions.json"), "w", encoding="utf-8") as f:
            json.dump(ds, f, ensure_ascii=False, indent=2)
        print(f"[decide] 已记录 {args.key}={args.value}（{args.reason}）；"
              f"执行 finalize 后生效")
        sys.exit(0)
    if args.cmd == "finalize":
        st_path = os.path.join(args.work_dir, "state.json")
        if not os.path.isfile(st_path):
            print("[finalize] 缺少 state.json，请先运行 run")
            sys.exit(1)
        with open(st_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        ds = load_decisions(args.work_dir)
        overrides = {d["key"]: d["value"] for d in ds}
        res = run_pipeline(state["input_dir"], args.work_dir, args.output_dir,
                           overrides=overrides, agent_decisions=ds)
        print(f"[finalize] 已应用 {len(ds)} 条裁决并重写交付物；status={res.get('status')}")
        sys.exit(0 if res.get("status") in ("ok", "partial") else 1)


if __name__ == "__main__":
    main()
