#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline_c.py — bundle C 一键 baseline 流水线（run / decide / finalize）。

用法：
  python3 pipeline_c.py run      --input /input --work /app/work --output /app/output
  python3 pipeline_c.py decide   --work /app/work --set group_by=age --set outcomes=strength
  python3 pipeline_c.py finalize --work /app/work --output /app/output

run/finalize 产出：result.json（9 契约字段 + sources + reproducibility + uncertainty +
exceptions + decisions + figures）、report.md、work/digest.md、work/analysis_data.json。
诚实 partial：任何步骤失败写入 exceptions 与 status，绝不静默。
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_c as sc

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "-"}
ENCODINGS = ("utf-8-sig", "gbk", "latin-1")
MAX_KGROUP_LEVELS = 8        # k 组检验自动执行的水平数上限
MAX_OUTCOMES = 20            # 自动分析的结局变量数上限


# ================================================================ 数据接入

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_enc(path):
    raw = open(path, "rb").read()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def _is_missing(tok):
    return tok.strip().lower() in MISSING_TOKENS


def _to_float(tok):
    try:
        return float(tok)
    except (TypeError, ValueError):
        return None


def load_csv(path):
    """CSV 加载：编码嗅探、表头嗅探、缺失 token、列类型判定。"""
    text, enc = read_text_enc(path)
    rows = [r for r in csv.reader(text.splitlines()) if r and any(c.strip() for c in r)]
    meta = {"encoding": enc, "header": False, "malformed_rows": 0, "path": path}
    if not rows:
        raise ValueError("空 CSV: %s" % path)
    ncol = max(len(r) for r in rows)
    good, bad = [], 0
    for r in rows:
        if len(r) == ncol:
            good.append(r)
        else:
            bad += 1
    meta["malformed_rows"] = bad
    # 表头嗅探：存在某列，其首行非数值而其余行 >=80% 数值 → 有表头
    header = False
    if len(good) > 1:
        for j in range(ncol):
            first = good[0][j].strip()
            rest = [g[j].strip() for g in good[1:]]
            if _to_float(first) is None and not _is_missing(first):
                numfrac = sum(1 for v in rest if _to_float(v) is not None or _is_missing(v)) / len(rest)
                if numfrac >= 0.8:
                    header = True
                    break
    meta["header"] = header
    if header:
        names = [c.strip() or "col%d" % (j + 1) for j, c in enumerate(good[0])]
        body = good[1:]
    else:
        names = ["col%d" % (j + 1) for j in range(ncol)]
        body = good
    columns = {}
    for j, name in enumerate(names):
        cells = [r[j].strip() for r in body]
        parsed, nmiss, nnum = [], 0, 0
        for c in cells:
            if _is_missing(c):
                parsed.append(None)
                nmiss += 1
            else:
                f = _to_float(c)
                if f is not None:
                    nnum += 1
                parsed.append(f if f is not None else c)
        nvalid = len(cells) - nmiss
        kind = "numeric" if (nvalid > 0 and nnum / nvalid >= 0.9) else "categorical"
        if kind == "numeric":
            parsed = [v if (v is None or isinstance(v, float)) else None for v in parsed]
        columns[name] = {"kind": kind, "values": parsed, "n_missing": nmiss}
    return {"names": names, "columns": columns, "n_rows": len(body), "meta": meta,
            "raw_rows": [[c.strip() for c in r] for r in body]}


def load_sqlite(path):
    """SQLite 加载：第一个用户表；TEXT 数值强制转换并记录。"""
    con = sqlite3.connect(path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if not tables:
            raise ValueError("SQLite 无用户表: %s" % path)
        table = tables[0]
        info = con.execute("PRAGMA table_info(%s)" % table).fetchall()
        names = [r[1] for r in info]
        declared = {r[1]: (r[2] or "").upper() for r in info}
        rows = con.execute("SELECT * FROM %s" % table).fetchall()
    finally:
        con.close()
    columns = {}
    coercion_note = []
    for j, name in enumerate(names):
        vals = [r[j] for r in rows]
        parsed, nmiss, nnum, ncoerced = [], 0, 0, 0
        for v in vals:
            if v is None or (isinstance(v, str) and _is_missing(v)):
                parsed.append(None)
                nmiss += 1
            elif isinstance(v, (int, float)):
                parsed.append(float(v))
                nnum += 1
            else:
                f = _to_float(str(v).strip())
                if f is not None:
                    parsed.append(f)
                    nnum += 1
                    ncoerced += 1
                else:
                    parsed.append(str(v))
        nvalid = len(vals) - nmiss
        kind = "numeric" if (nvalid > 0 and nnum / nvalid >= 0.9) else "categorical"
        if kind == "numeric":
            parsed = [v if (v is None or isinstance(v, float)) else None for v in parsed]
        if ncoerced:
            coercion_note.append("%s: 声明类型 %s，%d 个 TEXT 值强制转数值" % (name, declared[name], ncoerced))
        columns[name] = {"kind": kind, "values": parsed, "n_missing": nmiss,
                         "declared_type": declared[name]}
    meta = {"path": path, "table": table, "declared_types": declared,
            "coercions": coercion_note, "encoding": "sqlite", "header": True,
            "malformed_rows": 0}
    raw_rows = [[("" if v is None else str(v)) for v in r] for r in rows]
    return {"names": names, "columns": columns, "n_rows": len(rows), "meta": meta,
            "raw_rows": raw_rows}


# ================================================================ task.md 解析

def parse_task(task_text, ncols):
    """从 task.md 提取单位映射、全局单位、列序命名（无表头时）。"""
    units = {}
    for m in re.finditer(r"([A-Za-z_][\w/]*)[（(]([^（）()]{1,24})[）)]", task_text):
        key, unit = m.group(1), m.group(2).strip()
        for part in key.split("/"):
            part = part.strip()
            if part:
                units[part] = unit
    gmu = re.search(r"单位[：:为]?\s*([A-Za-zμ°/%\^0-9.]{1,12})", task_text)
    global_unit = gmu.group(1) if gmu else None
    seq = None
    ms = re.search(r"列序[：:]([^\n。；;]+)", task_text)
    if ms:
        toks = [t.strip() for t in re.split(r"[,，、/]", ms.group(1)) if t.strip()]
        toks = [re.split(r"单位|（|\(", t)[0].strip() for t in toks]
        toks = [t for t in toks if t]
        if len(toks) == ncols:
            seq = toks
    return {"units": units, "global_unit": global_unit, "col_seq": seq}


def unit_of(col, task_info):
    if col in task_info["units"]:
        return task_info["units"][col]
    if task_info["global_unit"]:
        return task_info["global_unit"]
    return None


# ================================================================ 清洗

def dedupe_frame(frame):
    """完全重复行 dedupe_keep_first，返回保留掩码与删除数。"""
    seen, keep = set(), []
    cols = [frame["columns"][n]["values"] for n in frame["names"]]
    nrows = frame["n_rows"]
    for i in range(nrows):
        key = tuple(c[i] for c in cols)
        if key in seen:
            continue
        seen.add(key)
        keep.append(i)
    return keep, nrows - len(keep)


def apply_keep(frame, keep):
    for n in frame["names"]:
        col = frame["columns"][n]
        col["values"] = [col["values"][i] for i in keep]
    frame["n_rows"] = len(keep)


def outlier_counts(frame):
    out = {}
    for n in frame["names"]:
        col = frame["columns"][n]
        if col["kind"] != "numeric":
            continue
        vals = [v for v in col["values"] if v is not None]
        if len(vals) < 4:
            out[n] = 0
            continue
        s = sorted(vals)
        q1, q3 = sc.percentile(s, 25.0), sc.percentile(s, 75.0)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out[n] = sum(1 for v in vals if v < lo or v > hi)
    return out


def consistency_check(fa, fb, name_a, name_b):
    """CSV 与 SQLite 一致性：行数、数值列均值最大差、分类列取值集合差。"""
    res = {"a": name_a, "b": name_b, "consistent": True, "details": []}
    if fa["n_rows"] != fb["n_rows"]:
        res["consistent"] = False
        res["details"].append("行数不一致: %s=%d vs %s=%d" % (name_a, fa["n_rows"], name_b, fb["n_rows"]))
    if len(fa["names"]) != len(fb["names"]):
        res["consistent"] = False
        res["details"].append("列数不一致: %d vs %d" % (len(fa["names"]), len(fb["names"])))
        return res
    for ja, jb in zip(fa["names"], fb["names"]):
        ca, cb = fa["columns"][ja], fb["columns"][jb]
        if ca["kind"] == "numeric" and cb["kind"] == "numeric":
            va = sorted(v for v in ca["values"] if v is not None)
            vb = sorted(v for v in cb["values"] if v is not None)
            if len(va) != len(vb):
                res["consistent"] = False
                res["details"].append("列 %s/%s 有效值数不同: %d vs %d" % (ja, jb, len(va), len(vb)))
                continue
            md = max((abs(x - y) for x, y in zip(va, vb)), default=0.0)
            if md > 1e-9:
                res["consistent"] = False
                res["details"].append("列 %s/%s 最大单元格差 %.3g" % (ja, jb, md))
        else:
            sa = sorted(str(v) for v in ca["values"] if v is not None)
            sb = sorted(str(v) for v in cb["values"] if v is not None)
            if sa != sb:
                res["consistent"] = False
                res["details"].append("列 %s/%s 分类取值不一致" % (ja, jb))
    if not res["details"]:
        res["details"].append("行数、列数、逐列取值完全一致（数值容差 1e-9）")
    return res


# ================================================================ 分析计划

def _distinct(vals):
    seen = []
    for v in vals:
        if v is not None and v not in seen:
            seen.append(v)
    return seen


def detect_grouping(frame, task_text, decisions, notes):
    override = decisions.get("group_by")
    cands = []
    for n in frame["names"]:
        col = frame["columns"][n]
        vals = [v for v in col["values"] if v is not None]
        dv = _distinct(vals)
        if col["kind"] == "categorical" and 2 <= len(dv) <= 10:
            cands.append({"name": n, "kind": "cat", "k": len(dv), "values": dv, "score": 1})
        elif col["kind"] == "numeric" and 2 <= len(dv) <= 20 \
                and all(float(v) == int(v) for v in dv):
            cands.append({"name": n, "kind": "int", "k": len(dv), "values": dv, "score": 0})
    tl = task_text.lower()
    for c in cands:
        name_l = c["name"].lower()
        if name_l in tl:
            c["score"] += 1
            idx = tl.find(name_l)
            window = tl[max(0, idx - 12):idx + len(name_l) + 12]
            if re.search(r"分组|分群|group|by", window):
                c["score"] += 3
        hits = sum(1 for v in c["values"]
                   if len(str(v)) >= 3 and (str(v).lower() in tl or tl in str(v).lower()
                                            or any(len(p) >= 3 and p in tl for p in re.split(r"[-_ ]", str(v).lower()))))
        if c["k"] > 0 and hits / c["k"] >= 0.5:
            c["score"] += 2
    if override:
        for c in cands:
            if c["name"] == override:
                notes.append("分组变量由 decide 覆盖为 %s" % override)
                return c
        raise ValueError("decide 指定的 group_by=%s 不是合法分组候选" % override)
    if not cands:
        return None
    cands.sort(key=lambda c: (-c["score"], 0 if c["kind"] == "cat" else 1, c["name"]))
    return cands[0]


def detect_focus_values(group, task_text, decisions):
    if decisions.get("focus"):
        return [float(v) if group["kind"] == "int" else v
                for v in str(decisions["focus"]).split(",")]
    if group["kind"] != "int":
        return []
    nums = set()
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", task_text):
        nums.add(float(m.group(1)))
    return sorted(v for v in group["values"] if float(v) in nums)


def grouped_samples(frame, gname, oname, keep_levels=None):
    gcol, ocol = frame["columns"][gname], frame["columns"][oname]
    out = {}
    for gv, ov in zip(gcol["values"], ocol["values"]):
        if gv is None or ov is None:
            continue
        label = ("%s" % gv).rstrip("0").rstrip(".") if isinstance(gv, float) else str(gv)
        if keep_levels is not None and gv not in keep_levels:
            continue
        out.setdefault(label, []).append(ov)
    return out


# ================================================================ 假设检验

def _normality(groups, alpha):
    res = {}
    for label, vals in groups.items():
        r = sc.dagostino_k2(vals)
        if r is None:
            res[label] = {"normal": False, "note": "n=%d<8，保守按非正态" % len(vals)}
        else:
            res[label] = {"K2": r["K2"], "p": r["p"], "normal": r["p"] >= alpha}
    return res


def analyze_two_group(aid, outcome, gvar, unit, samples, labels, alpha, seed):
    g1, g2 = samples[labels[0]], samples[labels[1]]
    norm = _normality({labels[0]: g1, labels[1]: g2}, alpha)
    lev = sc.levene_median([g1, g2])
    all_normal = all(v["normal"] for v in norm.values())
    homo = lev["p"] >= alpha
    if all_normal and homo:
        method, reason = "Student t", "ALL_NORMAL+HOMOGENEOUS->STUDENT_T"
        main = sc.t_student(g1, g2)
        stat, df = main["t"], [main["df"]]
        p = main["p"]
    elif all_normal:
        method, reason = "Welch t", "ALL_NORMAL+HETEROGENEOUS->WELCH_T"
        main = sc.t_welch(g1, g2)
        stat, df, p = main["t"], [main["df"]], main["p"]
    else:
        method, reason = "Mann-Whitney U", "NON_NORMAL_OR_SMALL_N->MANN_WHITNEY_U"
        main = sc.mann_whitney_u(g1, g2)
        stat, df, p = main["U1"], [], main["p"]
    ref_welch = sc.t_welch(g1, g2)
    g_ci = sc.hedges_g_bootstrap_ci(g1, g2, alpha=alpha, seed=seed)
    mean_ci = sc.welch_ci_mean_diff(g1, g2, alpha=alpha)
    eff = {"hedges_g": g_ci}
    cis = {"mean_diff_welch": mean_ci, "hedges_g": g_ci}
    if method == "Mann-Whitney U":
        hl = sc.hodges_lehmann(g1, g2, alpha=alpha, seed=seed)
        eff["hodges_lehmann"] = {"estimate": hl["estimate"]}
        cis["hodges_lehmann"] = hl
    return {
        "id": aid, "design": "two_group", "outcome": outcome, "group_var": gvar,
        "unit": unit, "k": 2, "method": method, "reason_code": reason,
        "statistic": stat, "stat_name": {"Student t": "t", "Welch t": "t",
                                         "Mann-Whitney U": "U"}[method],
        "df": df, "p": p, "p_fmt": sc.p_fmt(p), "alpha": alpha,
        "significant": p < alpha,
        "groups": {lab: {"n": len(samples[lab]), "mean": sc.mean(samples[lab]),
                         "sd": sc.sd(samples[lab]), "median": sc.median(samples[lab]),
                         "q1": sc.percentile(sorted(samples[lab]), 25.0),
                         "q3": sc.percentile(sorted(samples[lab]), 75.0)} for lab in labels},
        "assumptions": {"normality": norm,
                        "levene": {"W": lev["W"], "df1": lev["df1"], "df2": lev["df2"], "p": lev["p"]}},
        "reference_welch_t": {"t": ref_welch["t"], "df": ref_welch["df"], "p": ref_welch["p"],
                              "p_fmt": sc.p_fmt(ref_welch["p"]), "mean_diff": ref_welch["mean_diff"]},
        "effect_size": eff, "confidence_interval": cis,
    }


def analyze_k_group(aid, outcome, gvar, unit, samples, labels, alpha, seed):
    groups = [samples[lab] for lab in labels]
    k = len(groups)
    N = sum(len(g) for g in groups)
    norm = _normality(samples, alpha)
    lev = sc.levene_median(groups)
    all_normal = all(v["normal"] for v in norm.values())
    homo = lev["p"] >= alpha
    classic = sc.anova_oneway(groups)
    welch = sc.welch_anova(groups)
    kw = sc.kruskal_wallis(groups)
    if all_normal and homo:
        method, reason = "one-way ANOVA", "ALL_NORMAL+HOMOGENEOUS->ONEWAY_ANOVA"
        stat, stat_name, df, p = classic["F"], "F", [classic["df1"], classic["df2"]], classic["p"]
    elif all_normal:
        method, reason = "Welch ANOVA", "ALL_NORMAL+HETEROGENEOUS->WELCH_ANOVA"
        stat, stat_name, df, p = welch["F"], "F", [welch["df1"], welch["df2"]], welch["p"]
    else:
        method, reason = "Kruskal-Wallis", "NON_NORMAL_OR_SMALL_N->KRUSKAL_WALLIS"
        stat, stat_name, df, p = kw["H"], "H", [kw["df"]], kw["p"]
    if method == "Kruskal-Wallis":
        eff = {"epsilon_squared": sc.epsilon_squared_kw(kw["H"], N, k)}
    else:
        eff = {"eta_squared": sc.eta_squared(classic), "omega_squared": sc.omega_squared(classic, k)}
    # 事后两两比较：与主检验同路线 + Holm
    pairs = []
    for i in range(k):
        for j in range(i + 1, k):
            if method == "one-way ANOVA":
                r = sc.t_student(groups[i], groups[j])
                pm, ps = r["p"], r["t"]
            elif method == "Welch ANOVA":
                r = sc.t_welch(groups[i], groups[j])
                pm, ps = r["p"], r["t"]
            else:
                r = sc.mann_whitney_u(groups[i], groups[j])
                pm, ps = r["p"], r["U1"]
            pairs.append({"pair": [labels[i], labels[j]],
                          "method": {"one-way ANOVA": "Student t", "Welch ANOVA": "Welch t",
                                     "Kruskal-Wallis": "Mann-Whitney U"}[method],
                          "statistic": ps, "p": pm})
    adj = sc.holm_adjust([x["p"] for x in pairs])
    for x, pa in zip(pairs, adj):
        x["p_holm"] = pa
        x["significant_holm"] = pa < alpha
    return {
        "id": aid, "design": "k_group", "outcome": outcome, "group_var": gvar,
        "unit": unit, "k": k, "method": method, "reason_code": reason,
        "statistic": stat, "stat_name": stat_name, "df": df, "p": p,
        "p_fmt": sc.p_fmt(p), "alpha": alpha, "significant": p < alpha,
        "groups": {lab: {"n": len(samples[lab]), "mean": sc.mean(samples[lab]),
                         "sd": sc.sd(samples[lab]), "median": sc.median(samples[lab]),
                         "q1": sc.percentile(sorted(samples[lab]), 25.0),
                         "q3": sc.percentile(sorted(samples[lab]), 75.0)} for lab in labels},
        "assumptions": {"normality": norm,
                        "levene": {"W": lev["W"], "df1": lev["df1"], "df2": lev["df2"], "p": lev["p"]}},
        "reference_classic_anova": {"F": classic["F"], "df1": classic["df1"],
                                    "df2": classic["df2"], "p": classic["p"],
                                    "p_fmt": sc.p_fmt(classic["p"])},
        "reference_welch_anova": {"F": welch["F"], "df1": welch["df1"],
                                  "df2": welch["df2"], "p": welch["p"]},
        "reference_kruskal_wallis": {"H": kw["H"], "df": kw["df"], "p": kw["p"]},
        "effect_size": eff, "posthoc": pairs,
    }


# ================================================================ 解释

def _mag_g(g):
    g = abs(g)
    return "可忽略" if g < 0.2 else ("小" if g < 0.5 else ("中" if g < 0.8 else "大"))


def _mag_eta(e):
    return "可忽略" if e < 0.01 else ("小" if e < 0.06 else ("中" if e < 0.14 else "大"))


def interpret_analysis(a):
    unit = a["unit"] or "单位未注明"
    seg = ["【%s】按 %s 比较（%d 组，%s）：%s（依据 %s），%s=%.4g，df=%s，%s，α=%.3g → 统计上%s。"
           % (a["outcome"], a["group_var"], a["k"], unit, a["method"], a["reason_code"],
              a["stat_name"], a["statistic"],
              ",".join("%.4g" % d for d in a["df"]) if a["df"] else "-",
              a["p_fmt"], a["alpha"], "显著" if a["significant"] else "不显著")]
    if a["design"] == "two_group":
        labs = list(a["groups"].keys())
        g1, g2 = a["groups"][labs[0]], a["groups"][labs[1]]
        g = a["effect_size"]["hedges_g"]
        seg.append("均值差（%s-%s）=%.4g %s，Hedges g=%.3f（效应%s，95%%CI [%.3f, %.3f]）。"
                   % (labs[0], labs[1], g1["mean"] - g2["mean"], unit,
                      g["estimate"], _mag_g(g["estimate"]), g["lo"], g["hi"]))
        if "hodges_lehmann" in a["effect_size"]:
            hl = a["effect_size"]["hodges_lehmann"]
            seg.append("Hodges-Lehmann 中位数差=%.4g %s。" % (hl["estimate"], unit))
    else:
        if "eta_squared" in a["effect_size"]:
            e2, o2 = a["effect_size"]["eta_squared"], a["effect_size"]["omega_squared"]
            seg.append("η²=%.4f、ω²=%.4f（效应%s）。" % (e2, o2, _mag_eta(o2)))
        else:
            seg.append("ε²=%.4f（效应%s）。" % (a["effect_size"]["epsilon_squared"],
                                              _mag_eta(max(0.0, a["effect_size"]["epsilon_squared"]))))
        sig_pairs = [x for x in a.get("posthoc", []) if x["significant_holm"]]
        seg.append("事后两两比较（同路线 + Holm 校正）：%d/%d 对显著。"
                   % (len(sig_pairs), len(a.get("posthoc", []))))
    seg.append("注意：统计显著不等于实际意义，结论不能被表述为“证明”；单位=%s。" % unit)
    return "".join(seg)


# ================================================================ 主构建

def build_all(input_dir, work_dir, output_dir, decisions, seed=sc.SEED):
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    exceptions, uncertainty, limitations, notes = [], [], [], []

    case_path = os.path.join(input_dir, "case.json")
    task_path = os.path.join(input_dir, "task.md")
    case = json.load(open(case_path, encoding="utf-8"))
    task_text = open(task_path, encoding="utf-8").read()
    alpha = float(decisions.get("alpha", case.get("constraints", {}).get("alpha", 0.05)))

    # ---- 数据接入
    frames, sources = {}, {}
    for fn in case.get("data_files", []):
        p = os.path.join(input_dir, fn)
        if not os.path.exists(p):
            exceptions.append("数据文件缺失: %s" % fn)
            continue
        try:
            if fn.lower().endswith(".csv"):
                fr = load_csv(p)
            elif fn.lower().endswith((".db", ".sqlite", ".sqlite3")):
                fr = load_sqlite(p)
            else:
                exceptions.append("不支持的文件类型: %s" % fn)
                continue
        except Exception as e:  # 诚实 partial
            exceptions.append("加载 %s 失败: %s" % (fn, e))
            continue
        frames[fn] = fr
        sources[fn] = {"sha256": sha256_of(p), "rows": fr["n_rows"],
                       "cols": len(fr["names"]),
                       "encoding": fr["meta"].get("encoding")}
        if fr["meta"].get("coercions"):
            for c in fr["meta"]["coercions"]:
                notes.append("类型转换: " + c)
        if fr["meta"].get("malformed_rows"):
            notes.append("%s: 跳过 %d 行列数不符记录" % (fn, fr["meta"]["malformed_rows"]))
    if not frames:
        raise RuntimeError("无可用数据文件")
    primary_name = sorted(frames.keys(), key=lambda f: (not f.lower().endswith(".csv"), f))[0]
    frame = frames[primary_name]
    for n in frame["names"]:
        if frame["columns"][n]["n_missing"] == frame["n_rows"]:
            frame["columns"][n]["kind"] = "categorical"

    # ---- 跨源一致性（在清洗前的原始帧上核对）
    consistency = None
    if len(frames) >= 2:
        names2 = sorted(frames.keys())
        consistency = consistency_check(frames[names2[0]], frames[names2[1]],
                                        names2[0], names2[1])
        if not consistency["consistent"]:
            uncertainty.append("CSV 与 SQLite 不完全一致，详见 cleaning.consistency")

    # 无表头时按 task.md 列序命名
    task_info = parse_task(task_text, len(frame["names"]))
    if not frame["meta"].get("header") and task_info["col_seq"]:
        new_names = task_info["col_seq"]
        frame["columns"] = {new_names[i]: frame["columns"][frame["names"][i]]
                            for i in range(len(new_names))}
        frame["names"] = new_names
        notes.append("无表头：按 task.md 列序命名列为 %s" % ", ".join(new_names))
    for old, new in [(k[len("rename."):], v) for k, v in decisions.items()
                     if k.startswith("rename.")]:
        if old in frame["columns"]:
            frame["columns"][new] = frame["columns"].pop(old)
            frame["names"] = [new if x == old else x for x in frame["names"]]
            notes.append("列重命名: %s -> %s（decide）" % (old, new))

    # ---- 清洗
    # 重复行策略：constraints.duplicate_policy（如 concrete 案例显式指定
    # dedupe_exact_keep_first）> decide 覆盖 > 默认 report_only_keep。
    # 默认保留的理由：低精度测量数据的完全重复多为合法巧合（如 iris 0.1cm 分辨率），
    # 静默删除会改变可核验基准数字；无论是否删除都报告影响行数。
    constraints = case.get("constraints", {})
    dup_policy = str(decisions.get("duplicate_policy",
                                   constraints.get("duplicate_policy", "report_only_keep")))
    rows_in = frame["n_rows"]
    keep, ndup = dedupe_frame(frame)
    if dup_policy in ("dedupe_exact_keep_first", "dedupe_keep_first"):
        apply_keep(frame, keep)
        removed = ndup
    else:
        removed = 0
        if ndup:
            notes.append("检测到 %d 行完全重复，按策略 %s 保留（可用 "
                         "--set duplicate_policy=dedupe_exact_keep_first 覆盖）" % (ndup, dup_policy))
    miss_report = {n: frame["columns"][n]["n_missing"] for n in frame["names"]
                   if frame["columns"][n]["n_missing"] > 0}
    outliers = outlier_counts(frame)
    cleaning = {
        "missing": {"policy": "report_and_exclude（按变量有效 n，不零填不插补）",
                    "counts": miss_report},
        "duplicates": {"policy_requested": dup_policy,
                       "detected_rows": ndup, "removed_rows": removed},
        "outliers": {"policy": "1.5×IQR 栅栏只标记不删除", "flagged_per_column": outliers},
        "rows_in": rows_in, "rows_used": frame["n_rows"],
        "type_coercion": [n.split(": ", 1)[1] for n in notes if n.startswith("类型转换")],
        "rules_applied": ["missing=report_and_exclude", "duplicates=%s" % dup_policy,
                          "outliers=1.5xIQR_flag_only"],
    }
    if consistency is not None:
        cleaning["consistency"] = consistency

    # ---- 分析计划
    group = detect_grouping(frame, task_text, decisions, notes)
    analyses, analysis_data = [], []
    descriptive = {"by_outcome": {}}
    if group is None:
        exceptions.append("未检测到分组变量（无 2-10 水平分类列、无 2-20 水平整值列）")
    else:
        gname = group["name"]
        if decisions.get("outcomes"):
            outcomes = [o for o in str(decisions["outcomes"]).split(",") if o in frame["columns"]]
        else:
            outcomes = [n for n in frame["names"]
                        if n != gname and frame["columns"][n]["kind"] == "numeric"][:MAX_OUTCOMES]
        focus = detect_focus_values(group, task_text, decisions)
        designs = []
        if group["kind"] == "int" and len(focus) == 2 and group["k"] > 2:
            designs.append(("two_group", focus))
            if group["k"] <= MAX_KGROUP_LEVELS:
                designs.append(("k_group", None))
            else:
                limitations.append("分组变量 %s 有 %d 个水平（>%d），未自动执行全水平 k 组检验；"
                                   "按 task.md 聚焦 %s 两组比较。"
                                   % (gname, group["k"], MAX_KGROUP_LEVELS, focus))
        elif group["k"] >= 2:
            if group["k"] == 2:
                designs.append(("two_group", group["values"]))
            elif group["k"] <= MAX_KGROUP_LEVELS:
                designs.append(("k_group", None))
            else:
                exceptions.append("分组变量 %s 水平数 %d 超限且 task.md 未给出两个焦点水平"
                                  % (gname, group["k"]))
        aid_seq = 0
        for design, fvals in designs:
            for outcome in outcomes:
                unit = unit_of(outcome, task_info)
                if design == "two_group":
                    samples_all = grouped_samples(frame, gname, outcome, keep_levels=set(fvals))
                    labels = [("%s" % v).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
                              for v in fvals]
                    labels = [lab for lab in labels if lab in samples_all]
                else:
                    samples_all = grouped_samples(frame, gname, outcome)
                    labels = sorted(samples_all.keys(),
                                    key=lambda s: (0, float(s)) if _to_float(s) is not None else (1, s))
                samples = {lab: samples_all.get(lab, []) for lab in labels}
                if len(labels) < 2 or any(len(samples[lab]) < 2 for lab in labels):
                    exceptions.append("分析跳过 %s by %s：组数或组内 n 不足" % (outcome, gname))
                    continue
                aid_seq += 1
                aid = "a%d" % aid_seq
                try:
                    if design == "two_group":
                        a = analyze_two_group(aid, outcome, gname, unit, samples, labels,
                                              alpha, seed + aid_seq * 7919)
                    else:
                        a = analyze_k_group(aid, outcome, gname, unit, samples, labels,
                                            alpha, seed + aid_seq * 7919)
                except Exception as e:
                    exceptions.append("分析 %s by %s 失败: %s" % (outcome, gname, e))
                    continue
                analyses.append(a)
                analysis_data.append({
                    "id": aid, "design": design, "outcome": outcome, "group_var": gname,
                    "unit": unit, "method": a["method"], "reason_code": a["reason_code"],
                    "stat_name": a["stat_name"], "statistic": a["statistic"], "df": a["df"],
                    "p_fmt": a["p_fmt"], "alpha": alpha,
                    "route_nonparametric": a["method"] in ("Mann-Whitney U", "Kruskal-Wallis"),
                    "groups": [{"label": lab, "n": len(samples[lab]),
                                "values": samples[lab]} for lab in labels],
                })
                descriptive["by_outcome"][outcome] = {
                    "unit": unit,
                    "by_group": {lab: sc.descriptive(samples[lab]) for lab in labels},
                }
        if not analyses:
            exceptions.append("无任何可执行的组间分析")

    # ---- 组装 result.json
    waivers = {k[len("figure_waiver."):]: v for k, v in decisions.items()
               if k.startswith("figure_waiver.")}
    status = "ok" if analyses and not exceptions else ("partial" if analyses else "failed")
    result = {
        "case_id": case.get("case_id"),
        "status": status,
        "cleaning": cleaning,
        "descriptive": descriptive,
        "hypothesis_test": {"alpha": alpha, "analyses": analyses},
        "effect_size": {a["id"]: a["effect_size"] for a in analyses},
        "confidence_interval": {a["id"]: a.get("confidence_interval", {})
                                for a in analyses if a["design"] == "two_group"},
        "interpretation": "\n".join(interpret_analysis(a) for a in analyses) or "无可解释的分析。",
        "limitations": limitations + [
            "推断基于报告数据的假设门控路线；非参路线统计量为渐近近似。",
            "未注明确认单位的变量在图注中标记“单位未注明”。",
        ],
        "sources": sources,
        "reproducibility": {"seed": seed, "python": sys.version.split()[0],
                            "platform": platform.platform(),
                            "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
        "uncertainty": uncertainty + notes,
        "exceptions": exceptions,
        "decisions": {k: v for k, v in decisions.items()},
        "figures": {"generated": [], "waivers": waivers,
                    "policy": "每个做过假设检验的结局变量至少一张图或显式 waiver（见 figures.md）"},
    }

    # ---- 写出
    with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(work_dir, "analysis_data.json"), "w", encoding="utf-8") as f:
        json.dump({"case_id": case.get("case_id"), "seed": seed,
                   "analyses": analysis_data}, f, ensure_ascii=False)
    with open(os.path.join(work_dir, "session.json"), "w", encoding="utf-8") as f:
        json.dump({"input_dir": os.path.abspath(input_dir),
                   "output_dir": os.path.abspath(output_dir),
                   "decisions": decisions, "seed": seed}, f, ensure_ascii=False, indent=2)
    _write_report(output_dir, result, frame, primary_name)
    _write_digest(work_dir, result, frame, group, decisions)
    return result


# ================================================================ 报告与摘要

def _write_report(output_dir, result, frame, primary_name):
    L = []
    L.append("# 统计分析报告 — %s" % result["case_id"])
    L.append("")
    L.append("- 状态: **%s** | 主数据源: %s | 行数: %d→%d（清洗后）"
             % (result["status"], primary_name,
                result["cleaning"]["rows_in"], result["cleaning"]["rows_used"]))
    L.append("- 可复现: seed=%s, python=%s, %s" % (result["reproducibility"]["seed"],
                                                 result["reproducibility"]["python"],
                                                 result["reproducibility"]["utc"]))
    L.append("")
    L.append("## 1. 数据质量与清洗")
    c = result["cleaning"]
    L.append("- 缺失: %s；计数: %s" % (c["missing"]["policy"], c["missing"]["counts"] or "无"))
    L.append("- 重复: 策略 %s；检测 %d 行，删除 %d 行" % (c["duplicates"]["policy_requested"],
                                                         c["duplicates"]["detected_rows"],
                                                         c["duplicates"]["removed_rows"]))
    L.append("- 异常值: %s；标记: %s" % (c["outliers"]["policy"],
                                         {k: v for k, v in c["outliers"]["flagged_per_column"].items() if v} or "无"))
    if c.get("type_coercion"):
        L.append("- 类型转换: %s" % "; ".join(c["type_coercion"]))
    if "consistency" in c:
        L.append("- 跨源一致性（%s vs %s）: %s；%s"
                 % (c["consistency"]["a"], c["consistency"]["b"],
                    "一致" if c["consistency"]["consistent"] else "不一致",
                    "; ".join(c["consistency"]["details"])))
    L.append("")
    L.append("## 2. 描述统计（按组）")
    for outcome, blk in result["descriptive"]["by_outcome"].items():
        L.append("### %s（单位：%s）" % (outcome, blk["unit"] or "未注明"))
        L.append("| 组 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max | 偏度 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for lab, d in blk["by_group"].items():
            L.append("| %s | %d | %.4g | %.4g | %.4g | %.4g | %.4g | %.4g | %.4g | %.3f |"
                     % (lab, d["n"], d["mean"], d["sd"], d["median"], d["q1"],
                        d["q3"], d["min"], d["max"], d["skew"]))
        L.append("")
    L.append("## 3. 假设检验")
    L.append("| id | 结局 | 设计 | 方法 | 依据码 | 统计量 | df | p | 显著 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for a in result["hypothesis_test"]["analyses"]:
        L.append("| %s | %s | %s | %s | %s | %s=%.4g | %s | %s | %s |"
                 % (a["id"], a["outcome"], a["design"], a["method"], a["reason_code"],
                    a["stat_name"], a["statistic"],
                    ",".join("%.4g" % d for d in a["df"]) if a["df"] else "-",
                    a["p_fmt"], "是" if a["significant"] else "否"))
    L.append("")
    L.append("## 4. 效应量与 95% 置信区间")
    for a in result["hypothesis_test"]["analyses"]:
        L.append("- **%s** (%s, %s): %s" % (a["id"], a["outcome"], a["method"],
                                            json.dumps({"effect": result["effect_size"].get(a["id"]),
                                                        "ci": result["confidence_interval"].get(a["id"], {})},
                                                       ensure_ascii=False, default=str)[:600]))
    L.append("")
    L.append("## 5. 结果解释")
    L.append(result["interpretation"])
    L.append("")
    L.append("## 6. 局限性")
    for x in result["limitations"]:
        L.append("- " + x)
    L.append("")
    L.append("## 7. 图表")
    L.append("<!-- FIGURES:BEGIN -->")
    L.append("（图表清单由 figure_forge.py 写入；详见 figures.md）")
    L.append("<!-- FIGURES:END -->")
    L.append("")
    L.append("## 8. 来源与复现")
    for fn, s in result["sources"].items():
        L.append("- %s: sha256=%s, %d 行 × %d 列" % (fn, s["sha256"], s["rows"], s["cols"]))
    if result["exceptions"]:
        L.append("")
        L.append("## 异常记录")
        for x in result["exceptions"]:
            L.append("- " + x)
    with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def _write_digest(work_dir, result, frame, group, decisions):
    L = ["# digest.md — 待确认裁决（≤5 项，确认或 decide 覆盖后 finalize）", ""]
    analyses = result["hypothesis_test"]["analyses"]
    if group:
        L.append("1. **分组变量**: `%s`（%d 个水平，自动评分选出）。覆盖：`python3 pipeline_c.py decide --work <work> --set group_by=<列名>`"
                 % (group["name"], group["k"]))
        outs = sorted({a["outcome"] for a in analyses})
        L.append("2. **结局变量**（%d 个）: %s。覆盖：`--set outcomes=a,b,c`"
                 % (len(outs), ", ".join(outs[:12]) + (" ..." if len(outs) > 12 else "")))
    else:
        L.append("1. **分组变量**: 未检测到！必须 `--set group_by=<列名>` 后 finalize。")
    L.append("3. **检验路线**:")
    for a in analyses:
        L.append("   - %s: %s by %s → %s（%s），%s"
                 % (a["id"], a["outcome"], a["group_var"], a["method"], a["reason_code"], a["p_fmt"]))
    warns = []
    for a in analyses:
        for lab, nr in a["assumptions"]["normality"].items():
            if not nr["normal"]:
                warns.append("%s/%s 非正态（%s）" % (a["outcome"], lab,
                                                     nr.get("note", "K2 p=%.4g" % nr.get("p", float("nan")))))
    L.append("4. **假设警告**: " + ("；".join(warns[:10]) if warns else "无（全部通过）"))
    L.append("5. **alpha** = %.4g；单位映射见 report.md。覆盖：`--set alpha=0.01`"
             % result["hypothesis_test"]["alpha"])
    L.append("")
    L.append("确认无误后直接 finalize；任何覆盖后必须重新 finalize + figure_forge + figure_audit。")
    L.append("其他 decide 键：`focus=28,90`、`rename.<列>=<新名>`、`duplicate_policy=dedupe_exact_keep_first`、"
             "`figure_waiver.<分析id>=<理由>`、`max_figures=N`。")
    with open(os.path.join(work_dir, "digest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ================================================================ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="bundle C 一键 baseline 流水线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--input", required=True)
    pr.add_argument("--work", required=True)
    pr.add_argument("--output", required=True)
    pr.add_argument("--seed", type=int, default=sc.SEED)
    pd = sub.add_parser("decide")
    pd.add_argument("--work", required=True)
    pd.add_argument("--set", dest="sets", action="append", default=[])
    pd.add_argument("--unset", dest="unsets", action="append", default=[])
    pf = sub.add_parser("finalize")
    pf.add_argument("--work", required=True)
    pf.add_argument("--output", default=None)
    args = ap.parse_args(argv)

    if args.cmd == "run":
        res = build_all(args.input, args.work, args.output, {}, seed=args.seed)
        print("pipeline run 完成: status=%s, 分析数=%d, 输出=%s"
              % (res["status"], len(res["hypothesis_test"]["analyses"]), args.output))
        return 0 if res["status"] != "failed" else 2

    if args.cmd == "decide":
        sess_path = os.path.join(args.work, "session.json")
        if not os.path.exists(sess_path):
            print("session.json 不存在，先 run", file=sys.stderr)
            return 2
        sess = json.load(open(sess_path, encoding="utf-8"))
        dec = sess.get("decisions", {})
        for kv in args.sets:
            if "=" not in kv:
                print("--set 需要 key=value: %s" % kv, file=sys.stderr)
                return 2
            k, v = kv.split("=", 1)
            dec[k.strip()] = v.strip()
        for k in args.unsets:
            dec.pop(k, None)
        sess["decisions"] = dec
        with open(sess_path, "w", encoding="utf-8") as f:
            json.dump(sess, f, ensure_ascii=False, indent=2)
        print("decisions 已更新: %s" % json.dumps(dec, ensure_ascii=False))
        print("下一步: python3 pipeline_c.py finalize --work %s --output %s"
              % (args.work, sess["output_dir"]))
        return 0

    if args.cmd == "finalize":
        sess = json.load(open(os.path.join(args.work, "session.json"), encoding="utf-8"))
        output_dir = args.output or sess["output_dir"]
        res = build_all(sess["input_dir"], args.work, output_dir,
                        sess.get("decisions", {}), seed=sess.get("seed", sc.SEED))
        print("finalize 完成: status=%s, 分析数=%d, 输出=%s"
              % (res["status"], len(res["hypothesis_test"]["analyses"]), output_dir))
        print("提醒: 需重新运行 figure_forge.py 与 figure_audit.py 再交付")
        return 0 if res["status"] != "failed" else 2


if __name__ == "__main__":
    sys.exit(main())
