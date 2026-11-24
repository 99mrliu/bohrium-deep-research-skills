#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline_e — stats-run-gates 一键 baseline（run / decide / finalize）。

特征：分阶段落盘确定性中间产物（stage_01..stage_05），先写契约骨架再填数，
崩溃也在 /app/output/result.json 留下诚实 partial；除 reproducibility.timestamp_utc
（与 manifest.generated_at_utc）外全部产物字节级确定，可由 replay_diff 影子复跑验证。

子命令：
  run       从原始数据到 result.json + report.md + figure.svg + manifest.json
  decide    确认/覆盖 digest.md 中的裁决（写 work/decisions.json）
  finalize  应用 decisions.json 完整复跑并重写交付物（等价于 decisions.json 存在时的 run）
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_e as st
import run_manifest as rm

STAGE1, STAGE2, STAGE3, STAGE4, STAGE5 = (
    "stage_01_ingest.json", "stage_02_clean.json", "stage_03_descriptive.json",
    "stage_04_inference.json", "stage_05_result_draft.json")
GROUP_HINTS = ("group", "class", "species", "cultivar", "age", "batch", "condition", "treatment", "arm")
MAX_DISTINCT_GROUP = 20
AUTO_MANY_GROUPS = 6


# ---------------------------------------------------------------- 小工具
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize(o):
    """递归把非有限浮点转为 None，保证 JSON 合法且确定。"""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    return o


def write_json(obj, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sanitize(obj), f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class SeqLog:
    """阶段写入顺序日志（work/seq.log）：manifest 据此建立阶段状态表，G2 据此验证骨架先于推断。"""

    def __init__(self, work_dir):
        self.path = os.path.join(work_dir, "seq.log")
        self.n = 0
        with open(self.path, "w", encoding="utf-8", newline="\n") as f:
            f.write("")

    def write(self, fname):
        self.n += 1
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write("%d\twrite\t%s\n" % (self.n, fname))


# ---------------------------------------------------------------- 数据接入
def sniff_encoding(raw):
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return enc, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return "latin-1", raw.decode("latin-1", errors="replace")


def is_missing(cell):
    return cell is None or cell.strip() in st.MISSING_TOKENS


def try_float(cell):
    try:
        return float(cell.strip())
    except (ValueError, AttributeError):
        return None


def parse_csv(path):
    """返回 (parse_params, columns, raw_rows)。columns: [{name, numeric, values}]；raw_rows: 原始字符串行。"""
    with open(path, "rb") as f:
        raw = f.read()
    enc, text = sniff_encoding(raw)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    rows = [r for r in rows if any(c.strip() for c in r)]  # 丢弃全空行
    if not rows:
        raise ValueError("CSV 无数据行: %s" % path)
    header_cells = rows[0]
    # 表头嗅探：存在某列其首行为非数值而其余行过半为数值 → 首行是表头。
    # （不能仅凭首行含字符串判定：无表头 CSV 的分组列首行也是字符串，如 Iris-setosa）
    has_header = False
    if len(rows) > 1:
        ncol0 = len(header_cells)
        rest = [(r + [""] * ncol0)[:ncol0] for r in rows[1:]]
        for j in range(ncol0):
            c0 = header_cells[j]
            if is_missing(c0) or try_float(c0) is not None:
                continue
            col_rest = [r[j] for r in rest if not is_missing(r[j])]
            if col_rest and sum(1 for c in col_rest if try_float(c) is not None) > 0.5 * len(col_rest):
                has_header = True
                break
    if has_header:
        names = [c.strip() or "col%d" % i for i, c in enumerate(header_cells)]
        data = rows[1:]
    else:
        names = ["col%d" % i for i in range(len(header_cells))]
        data = rows
    ncol = len(names)
    norm_rows = [(r + [""] * ncol)[:ncol] for r in data]
    columns = []
    for j, name in enumerate(names):
        cells = [r[j] for r in norm_rows]
        nonmiss = [c for c in cells if not is_missing(c)]
        nparse = sum(1 for c in nonmiss if try_float(c) is not None)
        numeric = bool(nonmiss) and nparse >= max(1, int(math.ceil(0.9 * len(nonmiss))))
        if numeric:
            values = [None if is_missing(c) else try_float(c) for c in cells]
        else:
            values = [None if is_missing(c) else c.strip() for c in cells]
        columns.append({"name": name, "numeric": numeric, "values": values})
    params = {"encoding": enc, "delimiter": delim, "has_header": has_header,
              "missing_tokens": sorted(st.MISSING_TOKENS), "rows_raw": len(norm_rows)}
    return params, columns, norm_rows


def read_sqlite(path):
    """读取第一个用户表。返回 (table, col_names, col_types, rows) 或抛异常。"""
    con = sqlite3.connect(path)
    try:
        cur = con.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if not tables:
            raise ValueError("SQLite 无用户表: %s" % path)
        t = tables[0]
        info = cur.execute("PRAGMA table_info(%s)" % t).fetchall()
        names = [c[1] for c in info]
        types = [c[2] for c in info]
        rows = cur.execute("SELECT * FROM %s" % t).fetchall()
        return t, names, types, [list(r) for r in rows]
    finally:
        con.close()


def db_matches_csv(db_rows, columns, norm_rows):
    """逐格比对（数值经 float 强转后精确相等；字符串精确相等）。返回 (match, detail)。"""
    if len(db_rows) != len(norm_rows):
        return False, "行数不一致: db=%d csv=%d" % (len(db_rows), len(norm_rows))
    ncol = len(columns)
    bad = 0
    for i, (dr, cr) in enumerate(zip(db_rows, norm_rows)):
        if len(dr) < ncol:
            return False, "第 %d 行 db 列数不足" % i
        for j in range(ncol):
            dcell = dr[j]
            if columns[j]["numeric"]:
                try:
                    dv = float(dcell)
                except (TypeError, ValueError):
                    if is_missing(str(dcell)) and is_missing(cr[j]):
                        continue
                    bad += 1
                    continue
                cv = try_float(cr[j])
                if cv is None:
                    if is_missing(str(dcell)):
                        continue
                    bad += 1
                elif dv != cv:
                    bad += 1
            else:
                if str(dcell).strip() != cr[j].strip():
                    bad += 1
        if bad > 20:
            break
    return (bad == 0), ("全部 %d 行 × %d 列一致" % (len(db_rows), ncol) if bad == 0
                        else "发现 ≥%d 处单元格不一致" % bad)


# ---------------------------------------------------------------- 计划解析
def norm_group_label(v):
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return repr(v)
    return str(v)


def group_sort_key(label):
    try:
        return (0, float(label), "")
    except ValueError:
        return (1, 0.0, label)


def auto_detect_group(columns, n_rows):
    """返回 (列名 or None, 候选说明)。"""
    cands = []
    for col in columns:
        vals = [v for v in col["values"] if v is not None]
        if not vals:
            continue
        distinct = sorted(set(norm_group_label(v) for v in vals))
        if not (2 <= len(distinct) <= MAX_DISTINCT_GROUP):
            continue
        if len(distinct) > max(2, 0.2 * n_rows) and len(distinct) > MAX_DISTINCT_GROUP:
            continue
        hint = any(h in col["name"].lower() for h in GROUP_HINTS)
        if col["numeric"] and len(distinct) > 0.05 * n_rows and not hint:
            continue  # 近似连续数值列不做分组
        cands.append((0 if hint else 1, 0 if not col["numeric"] else 1, len(distinct), col["name"]))
    if not cands:
        return None, "无可行分组列（2..%d 个水平的列）" % MAX_DISTINCT_GROUP
    cands.sort()
    return cands[0][3], "自动判定：%d 个水平" % cands[0][2]


def resolve_column(columns, spec):
    names = [c["name"] for c in columns]
    if spec in names:
        return spec
    if spec.isdigit() and int(spec) < len(names):
        return names[int(spec)]
    low = {n.lower(): n for n in names}
    return low.get(str(spec).lower())


def sniff_unit(task_text):
    m = re.search(r"单位[为是：: ]*\s*([A-Za-zμ°%/\^0-9.³²]+)", task_text or "")
    return m.group(1) if m else None


def resolve_plan(case, columns, n_rows, args, overrides, task_text):
    """优先级：decisions overrides > CLI 参数 > --plan 文件 > 自动判定。
    返回 (plan, decisions_register)。"""
    pf = {}
    if getattr(args, "plan", None):
        pf = load_json(args.plan)

    def pick(key, cli_val, auto_fn, dec_id, topic):
        if key in overrides:
            return overrides[key], "override", dec_id, topic
        if cli_val is not None:
            return cli_val, "cli", dec_id, topic
        if key in pf:
            return pf[key], "plan_file", dec_id, topic
        return auto_fn()

    register = []

    def auto_group():
        name, note = auto_detect_group(columns, n_rows)
        return name, "auto", "DEC-001", "分组列（%s）" % note

    gcol, gsrc, _, _ = pick("group_column", getattr(args, "group_by", None), auto_group, "DEC-001", "分组列")
    if gcol is not None:
        resolved = resolve_column(columns, str(gcol))
        if resolved is None:
            raise ValueError("分组列不存在: %s（可用列: %s）" % (gcol, ", ".join(c["name"] for c in columns)))
        gcol = resolved
    register.append({"id": "DEC-001", "topic": "分组列", "value": gcol, "source": gsrc})

    def auto_outcomes():
        outs = [c["name"] for c in columns if c["numeric"] and c["name"] != gcol]
        return outs, "auto", "DEC-002", "结局变量（全部数值列）"

    ocli = getattr(args, "outcomes", None)
    ocli = [s.strip() for s in ocli.split(",")] if ocli else None
    outs, osrc, _, _ = pick("outcomes", ocli, auto_outcomes, "DEC-002", "结局变量")
    outs = [resolve_column(columns, str(o)) or str(o) for o in outs]
    outs = [o for o in outs if o in [c["name"] for c in columns]]
    register.append({"id": "DEC-002", "topic": "结局变量", "value": outs, "source": osrc})

    gcli = getattr(args, "groups", None)
    gcli = [s.strip() for s in gcli.split(",")] if gcli else None
    groups, groups_src = None, "auto"
    if "groups" in overrides:
        groups, groups_src = overrides["groups"], "override"
    elif gcli:
        groups, groups_src = gcli, "cli"
    elif "groups" in pf:
        groups, groups_src = pf["groups"], "plan_file"

    unit, usrc, _, _ = pick("unit", getattr(args, "unit", None),
                            lambda: (sniff_unit(task_text) or "unspecified", "auto", "DEC-005", "单位"),
                            "DEC-005", "单位")
    register.append({"id": "DEC-005", "topic": "测量单位", "value": unit, "source": usrc})

    alpha = case.get("constraints", {}).get("alpha", 0.05)
    if "alpha" in overrides:
        alpha = float(overrides["alpha"])

    plan = {"group_column": gcol, "outcomes": outs, "groups": groups, "groups_source": groups_src,
            "unit": unit, "alpha": float(alpha)}
    return plan, register


# ---------------------------------------------------------------- 清洗
def clean(columns, raw_rows, gcol_name, outcome_names, dup_policy):
    """行级剔除：分组变量缺失必剔除；完全重复行按 dup_policy 处理
    （dedupe_exact_keep_first=删至首行；flag_and_report=只标记报告不删除——
    基准快照中的完全重复可能是真实重测记录，删除需 case.json constraints 显式授权）。
    结局变量缺失按有效 n 逐变量处理。返回 (ledger_info, kept_indices)。"""
    gidx = [c["name"] for c in columns].index(gcol_name)
    seen = set()
    dup_rows = 0
    nogroup_rows = 0
    kept = []
    for i, r in enumerate(raw_rows):
        key = tuple(r)
        if key in seen:
            dup_rows += 1
            if dup_policy == "dedupe_exact_keep_first":
                continue
        else:
            seen.add(key)
        if columns[gidx]["values"][i] is None:
            nogroup_rows += 1
            continue
        kept.append(i)
    per_var_missing = {}
    for name in [gcol_name] + outcome_names:
        col = next(c for c in columns if c["name"] == name)
        per_var_missing[name] = sum(1 for i in kept if col["values"][i] is None)
    outlier_flag = {}
    outlier_rows = set()
    for name in outcome_names:
        col = next(c for c in columns if c["name"] == name)
        vals = [col["values"][i] for i in kept if col["values"][i] is not None]
        if len(vals) < 4:
            outlier_flag[name] = 0
            continue
        q1, q3 = st.vquantile(vals, 0.25), st.vquantile(vals, 0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        cnt = 0
        for i in kept:
            v = col["values"][i]
            if v is not None and (v < lo or v > hi):
                cnt += 1
                outlier_rows.add(i)
        outlier_flag[name] = cnt
    removed_dup = dup_rows if dup_policy == "dedupe_exact_keep_first" else 0
    ledger = {
        "rows_raw": len(raw_rows),
        "rows_kept": len(kept),
        "rows_dropped": removed_dup + nogroup_rows,
        "duplicate_policy": dup_policy,
        "duplicates_flagged": dup_rows,
        "duplicates_removed": removed_dup,
        "group_missing_removed": nogroup_rows,
        "missing_by_variable": per_var_missing,
        "outliers_flagged_cells": outlier_flag,
        "outliers_flagged_rows": len(outlier_rows),
    }
    ledger["closure_ok"] = ledger["rows_raw"] == ledger["rows_kept"] + ledger["rows_dropped"]
    return ledger, kept


# ---------------------------------------------------------------- 推断
def assess_normality(vals):
    n = len(vals)
    if n < 8:
        return {"n": n, "K2": None, "p": None, "normal": False,
                "note": "n<8，保守按非正态处理"}
    k2, p = st.dagostino_k2(vals)
    if k2 is None:
        return {"n": n, "K2": None, "p": None, "normal": False,
                "note": "K^2 变换不可用，保守按非正态处理"}
    return {"n": n, "K2": k2, "p": p, "normal": bool(p > 0.05), "note": ""}


def infer_outcome(group_labels, group_vals, alpha):
    """对单个结局变量执行假设门控推断。group_labels/group_vals 已按组排序、仅含 n>=2 组。"""
    k = len(group_vals)
    norm = {lab: assess_normality(vals) for lab, vals in zip(group_labels, group_vals)}
    all_normal = all(v["normal"] for v in norm.values())
    lw, ld1, ld2, lp = st.levene_median(group_vals)
    homog = bool(lp is not None and lp > alpha)
    assumptions = {"normality": norm,
                   "levene": {"W": lw, "df": [ld1, ld2], "p": lp, "homogeneous": homog,
                              "center": "median"}}

    if k == 2:
        x, y = group_vals[1], group_vals[0]  # 方向：排序后第二组 - 第一组
        contrast = "%s - %s" % (group_labels[1], group_labels[0])
        if all_normal and homog:
            method, code = "student_t", "2G_NORM_EQVAR"
            stat, df, p = st.t_student(x, y)
        elif all_normal:
            method, code = "welch_t", "2G_NORM_HEQVAR"
            stat, df, p = st.t_welch(x, y)
        else:
            method, code = "mannwhitney_u", "2G_NONNORM"
            stat, df, p = st.u_mannwhitney(x, y)
            df = None
        g = st.hedges_g(x, y)
        glo, ghi, bused = st.bootstrap_percentile(st.hedges_g, [x, y], alpha=alpha)
        effect = {"type": "hedges_g", "value": g, "ci95": [glo, ghi],
                  "ci_method": "bootstrap percentile B=%d seed=%d" % (st.BOOTSTRAP_B, st.BOOTSTRAP_SEED),
                  "magnitude": st.effect_magnitude("hedges_g", g),
                  "direction": contrast}
        if method in ("student_t", "welch_t"):
            lo, hi, wdf = st.welch_mean_diff_ci(x, y, alpha=alpha)
            location = {"type": "mean_diff", "estimate": st.vmean(x) - st.vmean(y),
                        "ci95": [lo, hi], "method": "welch", "direction": contrast}
        else:
            est, lo, hi = st.hodges_lehmann_diff(x, y)
            location = {"type": "hodges_lehmann_median_diff", "estimate": est,
                        "ci95": [lo, hi], "method": "hodges_lehmann", "direction": contrast}
        post = []
        reference = None
        if method == "mannwhitney_u":
            rt, rdf, rp = st.t_welch(x, y)
            reference = {"method": "welch_t(classical reference)", "statistic": rt,
                         "df": rdf, "p": rp,
                         "note": "仅作可比性参考；主结论以 %s 为准" % method}
        main = {"method": method, "reason_code": code, "statistic": stat,
                "df": df, "p": p}
    else:
        contrast = None
        if all_normal and homog:
            method, code = "oneway_anova", "KG_NORM_EQVAR"
            stat, d1, d2, p, _, _ = st.f_anova(group_vals)
            df = [d1, d2]
            reference = None
        elif all_normal:
            method, code = "welch_anova", "KG_NORM_HEQVAR"
            stat, d1, d2, p = st.f_welch_anova(group_vals)
            df = [d1, d2]
            rf, rd1, rd2, rp, _, _ = st.f_anova(group_vals)
            reference = {"method": "oneway_anova(classical reference)", "statistic": rf,
                         "df": [rd1, rd2], "p": rp,
                         "note": "方差不齐，主结论以 Welch ANOVA 为准；经典 F 仅作可比性参考"}
        else:
            method, code = "kruskal_wallis", "KG_NONNORM"
            stat, d1, p = st.h_kruskal(group_vals)
            df = d1
            rf, rd1, rd2, rp, _, _ = st.f_anova(group_vals)
            reference = {"method": "oneway_anova(classical reference)", "statistic": rf,
                         "df": [rd1, rd2], "p": rp,
                         "note": "正态性不满足，主结论以 Kruskal-Wallis 为准；经典 F 仅作可比性参考"}
        if method in ("oneway_anova", "welch_anova"):
            e2 = st.eta_squared(group_vals)
            o2 = st.omega_squared(group_vals)
            lo, hi, _ = st.bootstrap_percentile(lambda *gs: st.eta_squared(list(gs)), group_vals, alpha=alpha)
            effect = {"type": "eta2", "value": e2, "omega2": o2, "ci95": [lo, hi],
                      "ci_method": "bootstrap percentile B=%d seed=%d" % (st.BOOTSTRAP_B, st.BOOTSTRAP_SEED),
                      "magnitude": st.effect_magnitude("eta2", e2)}
        else:
            eps = st.epsilon_squared_kw(group_vals)
            lo, hi, _ = st.bootstrap_percentile(lambda *gs: st.epsilon_squared_kw(list(gs)), group_vals, alpha=alpha)
            effect = {"type": "eps2", "value": eps, "ci95": [lo, hi],
                      "ci_method": "bootstrap percentile B=%d seed=%d" % (st.BOOTSTRAP_B, st.BOOTSTRAP_SEED),
                      "magnitude": st.effect_magnitude("eps2", eps)}
        location = None
        # 事后两两（与主检验同路线）+ Holm
        raw_p = []
        pairs = []
        for i in range(k):
            for j in range(i + 1, k):
                gx, gy = group_vals[j], group_vals[i]
                clab = "%s - %s" % (group_labels[j], group_labels[i])
                if method == "oneway_anova":
                    s_, _, p_ = st.t_student(gx, gy)
                    m_ = "student_t"
                    ev = st.hedges_g(gx, gy)
                    et = "hedges_g"
                elif method == "welch_anova":
                    s_, _, p_ = st.t_welch(gx, gy)
                    m_ = "welch_t"
                    ev = st.hedges_g(gx, gy)
                    et = "hedges_g"
                else:
                    s_, _, p_ = st.u_mannwhitney(gx, gy)
                    m_ = "mannwhitney_u"
                    ev = st.rank_biserial_from_u(gx, gy)
                    et = "rank_biserial"
                pairs.append({"contrast": clab, "method": m_, "statistic": s_,
                              "p_raw": p_, "effect_type": et, "effect_value": ev})
                raw_p.append(p_)
        adj = st.holm_adjust(raw_p)
        for d, pa in zip(pairs, adj):
            d["p_holm"] = pa
            d["significant_holm"] = bool(pa is not None and pa < alpha)
        post = pairs
        main = {"method": method, "reason_code": code, "statistic": stat,
                "df": df, "p": p}

    main["alpha"] = alpha
    main["significant"] = bool(p is not None and p < alpha)
    return {"assumptions": assumptions, "main": main, "effect": effect,
            "location": location, "post_hoc": post, "reference": reference,
            "groups_order": list(group_labels)}


METHOD_ZH = {
    "student_t": "独立样本 t 检验（Student）",
    "welch_t": "Welch t 检验（不假定方差齐性）",
    "mannwhitney_u": "Mann-Whitney U 检验（tie 校正正态近似）",
    "oneway_anova": "单因素方差分析（ANOVA）",
    "welch_anova": "Welch 方差分析（不假定方差齐性）",
    "kruskal_wallis": "Kruskal-Wallis H 检验（tie 校正）",
}
REASON_ZH = {
    "2G_NORM_EQVAR": "两组均通过 D'Agostino 正态性且 Levene 方差齐",
    "2G_NORM_HEQVAR": "两组正态但 Levene 方差不齐",
    "2G_NONNORM": "至少一组不满足正态性（或 n<8 保守判定）",
    "KG_NORM_EQVAR": "各组均正态且方差齐",
    "KG_NORM_HEQVAR": "各组正态但方差不齐",
    "KG_NONNORM": "至少一组不满足正态性（或 n<8 保守判定）",
}


# ---------------------------------------------------------------- 可选 scipy 交叉校验
def scipy_crosscheck(group_vals, method, stat, p):
    try:
        from scipy import stats as sps  # noqa
    except Exception:
        return {"available": False}
    try:
        if method == "student_t":
            s_, p_ = sps.ttest_ind(group_vals[1], group_vals[0], equal_var=True)
        elif method == "welch_t":
            s_, p_ = sps.ttest_ind(group_vals[1], group_vals[0], equal_var=False)
        elif method == "mannwhitney_u":
            s_, p_ = sps.mannwhitneyu(group_vals[1], group_vals[0],
                                      use_continuity=False, alternative="two-sided",
                                      method="asymptotic")
            s_ = min(s_, len(group_vals[0]) * len(group_vals[1]) - s_)
        elif method == "oneway_anova":
            s_, p_ = sps.f_oneway(*group_vals)
        elif method == "welch_anova":
            try:
                s_, p_ = sps.f_oneway(*group_vals, equal_var=False)
            except TypeError:
                s_, p_ = None, None  # 老版本 scipy 无 equal_var 参数，跳过该校验
        elif method == "kruskal_wallis":
            s_, p_ = sps.kruskal(*group_vals)
        else:
            return {"available": True, "checked": False}
        if s_ is None:
            return {"available": True, "checked": False}
        ds = abs(float(s_) - float(stat))
        dp = abs(float(p_) - float(p))
        ok = ds <= max(1e-6, 1e-6 * abs(float(s_))) and dp <= 1e-6
        return {"available": True, "checked": True, "scipy_statistic": float(s_),
                "scipy_p": float(p_), "abs_diff_statistic": ds, "abs_diff_p": dp, "ok": bool(ok)}
    except Exception as e:
        return {"available": True, "checked": False, "error": str(e)}


# ---------------------------------------------------------------- SVG 图（纯文本，确定性）
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#EECA3B", "#B279A2", "#9D755D"]


def figure_svg(descriptive, gcol_name):
    """每结局一个分组箱线面板（5 数概括）。返回 SVG 文本。"""
    outcomes = sorted(descriptive.keys())
    pw, ph, top, left = 720, 190, 40, 70
    h = top + ph * len(outcomes) + 30
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'font-family="monospace" font-size="11">' % (pw, h)]
    parts.append('<text x="%d" y="20" font-size="13">Grouped boxplots by %s (min/Q1/median/Q3/max)</text>'
                 % (left, gcol_name))
    for pi, oc in enumerate(outcomes):
        groups = descriptive[oc]["groups"]
        labels = sorted(groups.keys(), key=group_sort_key)
        vals = [groups[l] for l in labels if groups[l]]
        if not vals:
            continue
        lo = min(g["min"] for g in vals)
        hi = max(g["max"] for g in vals)
        if hi <= lo:
            hi = lo + 1.0
        pad = 0.05 * (hi - lo)
        lo, hi = lo - pad, hi + pad
        y0 = top + ph * pi + 10
        plot_h = ph - 55

        def Y(v):
            return y0 + plot_h - (v - lo) / (hi - lo) * plot_h

        slot = (pw - left - 30) / max(1, len(labels))
        parts.append('<text x="5" y="%d">%s</text>' % (y0 + 12, oc))
        parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#888"/>'
                     % (left, y0 + plot_h, pw - 30, y0 + plot_h))
        for gi, (lab, g) in enumerate(zip(labels, [groups[l] for l in labels])):
            if not g:
                continue
            cx = left + slot * gi + slot / 2
            bw = min(40, slot * 0.5)
            col = PALETTE[gi % len(PALETTE)]
            parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'
                         % (cx, Y(g["min"]), cx, Y(g["max"]), col))
            parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity="0.35" stroke="%s"/>'
                         % (cx - bw / 2, Y(g["q3"]), bw, max(1.0, Y(g["q1"]) - Y(g["q3"])), col, col))
            parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="2"/>'
                         % (cx - bw / 2, Y(g["median"]), cx + bw / 2, Y(g["median"]), col))
            parts.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="9">%s (n=%d)</text>'
                         % (cx, y0 + plot_h + 14, lab[:14], g["n"]))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- 报告
def build_report(case_id, sources, cleaning, descriptive, inference, plan, interpretation,
                 limitations, uncertainty):
    L = []
    L.append("# 统计分析报告 — %s" % case_id)
    L.append("")
    L.append("（由 stats-run-gates pipeline_e 生成；所有 p 值/效应量写法与 result.json 一致，受 G6 门检约束）")
    L.append("")
    L.append("## 1 数据与清洗")
    for s in sources:
        L.append("- 输入 %s：sha256=%s…，%d bytes" % (s["file"], s["sha256"][:12], s["bytes"]))
    L.append("- 行数：raw=%d，kept=%d，dropped=%d（闭合律 rows_raw==kept+dropped：%s）"
             % (cleaning["rows_raw"], cleaning["rows_kept"], cleaning["rows_dropped"],
                "成立" if cleaning["closure_ok"] else "不成立"))
    for r in cleaning["rules"]:
        L.append("- 清洗规则 %s：影响行数 %s（%s）" % (r["rule"], r["affected_rows"], r.get("detail", "")))
    db = cleaning.get("db_consistency", {})
    L.append("- CSV/SQLite 一致性：%s" % ("未核对（%s）" % db.get("detail") if not db.get("checked")
                                         else ("一致" if db.get("match") else "不一致（%s）" % db.get("detail"))))
    L.append("")
    L.append("## 2 描述统计（按 %s 分组）" % plan["group_column"])
    for oc in sorted(descriptive.keys()):
        d = descriptive[oc]
        L.append("### %s（单位：%s）" % (oc, d["unit"]))
        L.append("| 组 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for lab in sorted(d["groups"].keys(), key=group_sort_key):
            g = d["groups"][lab]
            if not g:
                continue
            L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s |"
                     % (lab, g["n"], st.fmt_fixed(g["mean"]), st.fmt_fixed(g["sd"]),
                        st.fmt_fixed(g["median"]), st.fmt_fixed(g["q1"]), st.fmt_fixed(g["q3"]),
                        st.fmt_fixed(g["min"]), st.fmt_fixed(g["max"])))
        L.append("")
    L.append("## 3 假设检验、效应量与 95%% 置信区间（alpha=%s）" % st.fmt_fixed(plan["alpha"], 2))
    for oc in sorted(inference.keys()):
        inf = inference[oc]
        m = inf["main"]
        L.append("### %s [HT:%s]" % (oc, oc))
        L.append("- 方法：%s（理由码 %s：%s）"
                 % (METHOD_ZH[m["method"]], m["reason_code"], REASON_ZH[m["reason_code"]]))
        L.append("- 统计量 = %s，df = %s，%s" % (st.fmt_fixed(m["statistic"]), m["df"], st.fmt_p(m["p"])))
        e = inf["effect"]
        ci95 = e.get("ci95") or [None, None]
        ci_txt = ("[%s, %s]" % (st.fmt_fixed(ci95[0]), st.fmt_fixed(ci95[1]))) if ci95[0] is not None else "NA"
        L.append("- 效应量：%s，95%% CI %s（%s；幅度：%s）[ES:%s]"
                 % (st.fmt_effect(e["type"], e["value"]), ci_txt,
                    e.get("ci_method", ""), e.get("magnitude", ""), oc))
        if e.get("omega2") is not None:
            L.append("- 校正效应量：%s" % st.fmt_effect("omega2", e["omega2"]))
        if inf.get("location"):
            loc = inf["location"]
            L.append("- 位置差（%s）：%s = %s，95%% CI [%s, %s]"
                     % (loc["direction"], loc["type"], st.fmt_fixed(loc["estimate"]),
                        st.fmt_fixed(loc["ci95"][0]), st.fmt_fixed(loc["ci95"][1])))
        if inf.get("reference"):
            r = inf["reference"]
            L.append("- 参考：%s，统计量 = %s，%s（%s）"
                     % (r["method"], st.fmt_fixed(r["statistic"]), st.fmt_p(r["p"]), r["note"]))
        if inf.get("post_hoc"):
            L.append("- 事后两两比较（与主检验同路线，Holm 校正）：")
            for d in inf["post_hoc"]:
                L.append("  - %s：%s，统计量 = %s，%s → Holm %s，%s"
                         % (d["contrast"], d["method"], st.fmt_fixed(d["statistic"]),
                            st.fmt_p(d["p_raw"]), st.fmt_p(d["p_holm"]),
                            st.fmt_effect(d["effect_type"], d["effect_value"])))
        L.append("- 判定：在 alpha=%s 下组间差异%s统计显著 [CI:%s]"
                 % (st.fmt_fixed(m["alpha"], 2), "" if m["significant"] else "不", oc))
        L.append("")
    L.append("## 4 解释")
    for s in interpretation:
        L.append("- %s" % s)
    L.append("")
    L.append("## 5 局限与不确定性")
    for s in limitations:
        L.append("- 局限：%s" % s)
    for s in uncertainty:
        L.append("- 不确定性：%s" % s)
    L.append("")
    L.append("## 6 可复现性")
    L.append("- seed=%d，python=%s，platform=%s；输入/阶段产物哈希见 work/manifest.json；"
             "影子复跑由 scripts/replay_diff.py 逐字节核验。" % (st.BOOTSTRAP_SEED, platform.python_version(), platform.platform()))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- 主流程
def skeleton_result(case_id, required_fields):
    sk = {"case_id": case_id, "status": "partial", "_skeleton": True,
          "skeleton_fields": list(required_fields),
          "exceptions": [{"code": "SKELETON_NOT_FILLED",
                          "message": "契约骨架已建立但流水线未完成填数；本 partial 为诚实中间态。"}]}
    for f in required_fields:
        if f not in sk:
            sk[f] = {} if f not in ("interpretation", "limitations") else ([] if f == "limitations" else "")
    return sk


def run_core(input_dir, work_dir, output_dir, args, decisions, argv_for_manifest):
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    overrides = decisions.get("overrides", {})
    confirmed = set(decisions.get("confirmed", []))
    seq = SeqLog(work_dir)

    case_path = os.path.join(input_dir, "case.json")
    case = load_json(case_path) if os.path.isfile(case_path) else {}
    case_id = case.get("case_id", "UNKNOWN")
    required = case.get("output_contract", {}).get("required_fields",
                                                   ["case_id", "status", "cleaning", "descriptive",
                                                    "hypothesis_test", "effect_size", "confidence_interval",
                                                    "interpretation", "limitations"])
    task_text = ""
    task_path = os.path.join(input_dir, "task.md")
    if os.path.isfile(task_path):
        with open(task_path, "r", encoding="utf-8", errors="replace") as f:
            task_text = f.read()

    # 先写契约骨架（stage_05）+ 诚实 partial 到交付位，崩溃也留痕
    sk = skeleton_result(case_id, required)
    write_json(sk, os.path.join(work_dir, STAGE5))
    seq.write(STAGE5)
    write_json(sk, os.path.join(output_dir, "result.json"))

    exceptions = []

    # ---- stage 01 接入
    data_files = case.get("data_files") or sorted(
        f for f in os.listdir(input_dir) if f.endswith((".csv", ".db")))
    csv_name = next((f for f in data_files if f.lower().endswith(".csv")), None)
    db_name = next((f for f in data_files if f.lower().endswith((".db", ".sqlite", ".sqlite3"))), None)
    sources = []
    for f in data_files:
        p = os.path.join(input_dir, f)
        if os.path.isfile(p):
            sources.append({"file": f, "sha256": rm.sha256_file(p), "bytes": os.path.getsize(p)})
    if csv_name:
        primary_path = os.path.join(input_dir, csv_name)
        params, columns, raw_rows = parse_csv(primary_path)
        primary_kind = "csv"
    elif db_name:
        t, names, types, rows = read_sqlite(os.path.join(input_dir, db_name))
        raw_rows = [["" if v is None else str(v) for v in r] for r in rows]
        columns = []
        for j, nm in enumerate(names):
            vals = [r[j] for r in raw_rows]
            nonmiss = [c for c in vals if not is_missing(c)]
            nparse = sum(1 for c in nonmiss if try_float(c) is not None)
            numeric = bool(nonmiss) and nparse == len(nonmiss)
            columns.append({"name": nm, "numeric": numeric,
                            "values": [None if is_missing(c) else (try_float(c) if numeric else c.strip()) for c in vals]})
        params = {"encoding": "sqlite", "delimiter": None, "has_header": True,
                  "missing_tokens": sorted(st.MISSING_TOKENS), "rows_raw": len(raw_rows),
                  "table": t, "column_types": types}
        primary_kind = "sqlite"
    else:
        raise SystemExit("FATAL: 输入目录无 CSV/SQLite 数据文件")
    stage1 = {"case_id": case_id,
              "inputs": sources,
              "primary": {"file": csv_name or db_name, "kind": primary_kind},
              "parse_params": params,
              "columns": [{"name": c["name"], "numeric": c["numeric"]} for c in columns]}
    write_json(stage1, os.path.join(work_dir, STAGE1))
    seq.write(STAGE1)

    # SQLite 一致性核对
    db_check = {"checked": False, "match": None, "detail": "无 SQLite 文件"}
    if db_name and csv_name:
        try:
            t, names, types, db_rows = read_sqlite(os.path.join(input_dir, db_name))
            match, detail = db_matches_csv(db_rows, columns, raw_rows)
            db_check = {"checked": True, "match": bool(match), "table": t,
                        "column_types": types, "detail": detail}
            if not match:
                exceptions.append({"code": "DB_MISMATCH",
                                   "message": "CSV 与 SQLite 内容不一致，按 DEC-004 以 CSV 为准。",
                                   "detail": detail})
        except Exception as e:
            db_check = {"checked": False, "match": None, "detail": "SQLite 读取失败: %s" % e}
            exceptions.append({"code": "DB_UNREADABLE", "message": str(e)})

    # ---- 计划解析（含裁决登记）
    plan, register = resolve_plan(case, columns, len(raw_rows), args, overrides, task_text)
    if plan["group_column"] is None:
        sk2 = skeleton_result(case_id, required)
        sk2["exceptions"].append({"code": "NO_GROUPING", "message": "无法确定分组列"})
        write_json(sk2, os.path.join(output_dir, "result.json"))
        raise SystemExit("FATAL: 无法确定分组列（result.json 已留诚实 partial）")

    gcol = next(c for c in columns if c["name"] == plan["group_column"])
    all_labels = sorted(set(norm_group_label(v) for v in gcol["values"] if v is not None),
                        key=group_sort_key)
    if plan["groups"]:
        want = [norm_group_label(try_float(g) if try_float(g) is not None else g) for g in plan["groups"]]
        missing_g = [g for g in want if g not in all_labels]
        if missing_g:
            exceptions.append({"code": "GROUP_LABEL_MISSING",
                               "message": "请求的子集组不存在: %s（可用: %s）" % (missing_g, all_labels)})
        group_labels = [g for g in all_labels if g in want]
    else:
        group_labels = all_labels
    if len(all_labels) > AUTO_MANY_GROUPS and not plan["groups"]:
        register.append({"id": "DEC-003", "topic": "组数较多(k=%d)：默认对全部组做 omnibus；"
                         "如任务指定焦点子集，用 --set groups=a,b 覆盖" % len(all_labels),
                         "value": "use_all_%d_groups" % len(all_labels), "source": "auto"})
    if db_check.get("checked") and not db_check.get("match"):
        register.append({"id": "DEC-004", "topic": "CSV/SQLite 不一致时的口径", "value": "use_csv", "source": "auto"})

    # ---- stage 02 清洗
    dup_policy = case.get("constraints", {}).get("duplicate_policy", "flag_and_report")
    if dup_policy not in ("dedupe_exact_keep_first", "flag_and_report"):
        exceptions.append({"code": "UNKNOWN_DUP_POLICY",
                           "message": "未知 duplicate_policy=%r，按 flag_and_report 处理" % dup_policy})
        dup_policy = "flag_and_report"
    ledger, kept = clean(columns, raw_rows, plan["group_column"], plan["outcomes"], dup_policy)
    ledger["db_consistency"] = db_check
    kept_in_groups = [i for i in kept
                      if norm_group_label(gcol["values"][i]) in set(group_labels)]
    cleaned_rows = [[columns[j]["values"][i] for j in range(len(columns))] for i in kept_in_groups]
    ledger["rows_in_analysis_groups"] = len(kept_in_groups)
    ledger["cleaned_sha256"] = sha256_text(json.dumps(sanitize(cleaned_rows), sort_keys=True))
    rules = [
        {"rule": dup_policy, "affected_rows": ledger["duplicates_flagged"],
         "detail": ("完全重复行保留首行、删除其余" if dup_policy == "dedupe_exact_keep_first"
                    else "完全重复行只标记报告不删除（删除需 constraints.duplicate_policy 显式授权）")},
        {"rule": "missing_report_and_exclude", "affected_rows": ledger["group_missing_removed"],
         "detail": "分组变量缺失行整行剔除；结局变量缺失按逐变量有效 n 处理（不零填、不插补）"},
        {"rule": "outlier_flag_1.5IQR", "affected_rows": ledger["outliers_flagged_rows"],
         "detail": "1.5×IQR 栅栏只标记不删除"},
    ]
    ledger["rules"] = rules
    write_json(ledger, os.path.join(work_dir, STAGE2))
    seq.write(STAGE2)

    # ---- stage 03 描述统计
    descriptive = {}
    colmap = {c["name"]: c for c in columns}
    for oc in plan["outcomes"]:
        col = colmap[oc]
        if not col["numeric"]:
            exceptions.append({"code": "OUTCOME_NOT_NUMERIC",
                               "message": "结局变量 %s 非数值列，已跳过" % oc})
            continue
        groups_d = {}
        for lab in group_labels:
            vals = [col["values"][i] for i in kept_in_groups
                    if norm_group_label(gcol["values"][i]) == lab and col["values"][i] is not None]
            groups_d[lab] = st.describe_series(vals)
        descriptive[oc] = {"unit": plan["unit"], "groups": groups_d}
    stage3 = {"plan": {"group_column": plan["group_column"], "outcomes": plan["outcomes"],
                       "groups": group_labels, "unit": plan["unit"], "alpha": plan["alpha"]},
              "descriptive": descriptive}
    write_json(stage3, os.path.join(work_dir, STAGE3))
    seq.write(STAGE3)

    # ---- stage 04 推断
    inference = {}
    for oc in sorted(descriptive.keys()):
        gvals, glabs = [], []
        for lab in group_labels:
            d = descriptive[oc]["groups"][lab]
            if d and d["n"] >= 2:
                col = colmap[oc]
                vals = [col["values"][i] for i in kept_in_groups
                        if norm_group_label(gcol["values"][i]) == lab and col["values"][i] is not None]
                gvals.append(vals)
                glabs.append(lab)
            else:
                exceptions.append({"code": "GROUP_SMALL_N",
                                   "message": "结局 %s 组 %s 有效 n<2，推断中剔除" % (oc, lab)})
        if len(gvals) < 2:
            exceptions.append({"code": "OUTCOME_SKIPPED",
                               "message": "结局 %s 可用组不足 2，无法推断" % oc})
            continue
        inf = infer_outcome(glabs, gvals, plan["alpha"])
        inf["scipy_crosscheck"] = scipy_crosscheck(gvals, inf["main"]["method"],
                                                   inf["main"]["statistic"], inf["main"]["p"])
        if inf["scipy_crosscheck"].get("checked") and not inf["scipy_crosscheck"].get("ok"):
            exceptions.append({"code": "CROSSCHECK_MISMATCH",
                               "message": "结局 %s 与 scipy 交叉校验不一致: %s" % (oc, inf["scipy_crosscheck"])})
        inference[oc] = inf
    write_json({"inference": inference}, os.path.join(work_dir, STAGE4))
    seq.write(STAGE4)

    # ---- 解释/局限/不确定性
    interpretation, limitations, uncertainty = [], [], []
    for oc in sorted(inference.keys()):
        inf = inference[oc]
        m, e = inf["main"], inf["effect"]
        unit = descriptive[oc]["unit"]
        sig = "统计显著" if m["significant"] else "统计上不显著"
        mag = e.get("magnitude", "不可判定")
        if len(inf["groups_order"]) == 2:
            g1, g2 = inf["groups_order"][0], inf["groups_order"][1]
            d1, d2 = descriptive[oc]["groups"][g1], descriptive[oc]["groups"][g2]
            diff = (d2["mean"] - d1["mean"]) if (d1 and d2) else None
            interpretation.append(
                "%s（单位：%s）：%s（n=%d）与 %s（n=%d）比较，采用%s（%s），%s；均值差（%s - %s）= %s %s。"
                "效应量 %s（%s），95%% CI [%s, %s]。统计显著不等于实际意义：本效应幅度为「%s」。"
                "本结果为组间关联证据，不能表述为「证明」因果。[HT:%s] [ES:%s] [CI:%s]"
                % (oc, unit, g1, d1["n"] if d1 else 0, g2, d2["n"] if d2 else 0,
                   METHOD_ZH[m["method"]], sig, st.fmt_p(m["p"]), g2, g1,
                   st.fmt_fixed(diff), unit, e["type"], st.fmt_fixed(e["value"]),
                   st.fmt_fixed(e["ci95"][0] if e.get("ci95") else None),
                   st.fmt_fixed(e["ci95"][1] if e.get("ci95") else None),
                   mag, oc, oc, oc))
        else:
            interpretation.append(
                "%s（单位：%s）：%d 个组比较，采用%s（%s），%s。效应量 %s（%s，幅度「%s」），"
                "95%% CI [%s, %s]；事后两两比较经 Holm 校正（详见 result.json）。"
                "统计显著不等于实际意义；本结果为组间关联证据，不能表述为「证明」因果。[HT:%s] [ES:%s] [CI:%s]"
                % (oc, unit, len(inf["groups_order"]), METHOD_ZH[m["method"]],
                   m["reason_code"], st.fmt_p(m["p"]), e["type"], st.fmt_fixed(e["value"]),
                   mag, st.fmt_fixed(e["ci95"][0] if e.get("ci95") else None),
                   st.fmt_fixed(e["ci95"][1] if e.get("ci95") else None), oc, oc, oc))
        if inf.get("reference"):
            interpretation.append(
                "%s：为主结论稳健性附记经典参考统计量（%s，统计量 = %s，%s）；"
                "该参考值不改变以假设门控选定方法为准的结论。[HT:%s]"
                % (oc, inf["reference"]["method"], st.fmt_fixed(inf["reference"]["statistic"]),
                   st.fmt_p(inf["reference"]["p"]), oc))

    if plan["unit"] == "unspecified":
        limitations.append("测量单位未在 task.md 中明确（DEC-005），解释时无法携带单位。")
    for oc in sorted(descriptive.keys()):
        flags = ledger["outliers_flagged_cells"].get(oc, 0)
        if flags:
            limitations.append("%s 有 %d 个 1.5×IQR 栅栏外取值（仅标记未删除），极端值可能影响参数法结果。" % (oc, flags))
        for lab, d in descriptive[oc]["groups"].items():
            if d and d["n"] < 8:
                limitations.append("%s 组 %s 有效 n=%d<8，正态性按保守口径判定，检验功效有限。" % (oc, lab, d["n"]))
    if not db_check.get("checked"):
        limitations.append("CSV 与 SQLite 一致性未核对（%s）。" % db_check.get("detail", "无数据库"))
    limitations.append("本分析基于观察性数据，全部结论为关联性证据，不支持因果断言。")
    uncertainty.append("效应量 95%% CI 来自分层百分位 bootstrap（B=%d，seed=%d），重抽样尾部分位本身存在蒙特卡洛误差。"
                       % (st.BOOTSTRAP_B, st.BOOTSTRAP_SEED))
    for oc in sorted(inference.keys()):
        m = inference[oc]["main"]
        if m["method"] in ("mannwhitney_u", "kruskal_wallis"):
            uncertainty.append("%s 采用秩检验正态近似（tie 校正），极端 ties 或小组样本下 p 值为近似。" % oc)
        norm = inference[oc]["assumptions"]["normality"]
        border = [lab for lab, v in norm.items() if v.get("p") is not None and 0.01 < v["p"] < 0.10]
        if border:
            uncertainty.append("%s 组 %s 正态性 p 接近 0.05 边界，路线选择对该判定敏感。" % (oc, border))

    # ---- 决策状态
    decisions_out = []
    for d in register:
        status = "confirmed" if (d["source"] in ("cli", "plan_file", "override") or d["id"] in confirmed) else "pending"
        decisions_out.append({"id": d["id"], "topic": d["topic"], "value": d["value"],
                              "source": d["source"], "status": status})

    # ---- 组装 result.json
    cleaning_out = {
        "rows_raw": ledger["rows_raw"], "rows_kept": ledger["rows_kept"],
        "rows_dropped": ledger["rows_dropped"], "closure_ok": ledger["closure_ok"],
        "closure": "rows_raw == rows_kept + rows_dropped",
        "rules": rules, "duplicate_policy": ledger["duplicate_policy"],
        "duplicates_flagged": ledger["duplicates_flagged"],
        "duplicates_removed": ledger["duplicates_removed"],
        "group_missing_removed": ledger["group_missing_removed"],
        "missing_by_variable": ledger["missing_by_variable"],
        "outliers_flagged_cells": ledger["outliers_flagged_cells"],
        "outliers_flagged_rows": ledger["outliers_flagged_rows"],
        "db_consistency": db_check,
    }
    hypothesis_test, effect_size, confidence_interval = {}, {}, {}
    for oc in sorted(inference.keys()):
        inf = inference[oc]
        m = inf["main"]
        hypothesis_test[oc] = {
            "id": "HT:%s" % oc, "method": m["method"], "reason_code": m["reason_code"],
            "statistic": m["statistic"], "df": m["df"], "p": m["p"], "alpha": m["alpha"],
            "significant": m["significant"], "groups_order": inf["groups_order"],
            "assumptions": inf["assumptions"], "post_hoc": inf["post_hoc"],
            "reference": inf["reference"],
        }
        e = inf["effect"]
        effect_size[oc] = dict(e)
        effect_size[oc]["id"] = "ES:%s" % oc
        ci = {"id": "CI:%s" % oc, "effect": {"type": e["type"], "value": e["value"],
                                             "ci95": e.get("ci95"), "method": e.get("ci_method")}}
        if inf.get("location"):
            ci["location"] = inf["location"]
        confidence_interval[oc] = ci

    evidence = []
    for oc in sorted(inference.keys()):
        evidence += ["HT:%s" % oc, "ES:%s" % oc, "CI:%s" % oc]
    evidence += ["SRC:%s" % s["file"] for s in sources]
    evidence += ["STAGE:%s" % s for s in (STAGE1, STAGE2, STAGE3, STAGE4, STAGE5)]
    evidence += [d["id"] for d in decisions_out]

    status = "complete" if not exceptions else "partial"
    result = {
        "case_id": case_id,
        "status": status,
        "cleaning": cleaning_out,
        "descriptive": descriptive,
        "hypothesis_test": hypothesis_test,
        "effect_size": effect_size,
        "confidence_interval": confidence_interval,
        "interpretation": interpretation,
        "limitations": limitations,
        "uncertainty": uncertainty,
        "exceptions": exceptions,
        "decisions": decisions_out,
        "sources": sources,
        "reproducibility": {"seed": st.BOOTSTRAP_SEED, "bootstrap_B": st.BOOTSTRAP_B,
                            "python": platform.python_version(), "platform": platform.platform(),
                            "timestamp_utc": utc_now()},
        "evidence_index": evidence,
        "analysis_plan": {"group_column": plan["group_column"], "outcomes": plan["outcomes"],
                          "groups": group_labels, "unit": plan["unit"], "alpha": plan["alpha"]},
    }
    write_json(result, os.path.join(output_dir, "result.json"))

    # ---- 报告 / 图 / digest
    report = build_report(case_id, sources, cleaning_out, descriptive, inference, plan,
                          interpretation, limitations, uncertainty)
    with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(report)
    with open(os.path.join(output_dir, "figure.svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(figure_svg(descriptive, plan["group_column"]))

    dg = ["# digest — 待确认裁决（stats-run-gates）", "",
          "以下裁决由 pipeline 自动/按参数作出。[PENDING] 项须确认或覆盖后 finalize（G7 门检）。",
          "确认：python3 scripts/pipeline_e.py decide --work <work> --confirm-all",
          "覆盖：python3 scripts/pipeline_e.py decide --work <work> --set groups=28,90（随后 finalize）", ""]
    for d in decisions_out:
        mark = "[PENDING]" if d["status"] == "pending" else "[CONFIRMED]"
        dg.append("- %s %s %s = %s（来源 %s）" % (mark, d["id"], d["topic"], d["value"], d["source"]))
    if not any(d["status"] == "pending" for d in decisions_out):
        dg.append("")
        dg.append("全部裁决已确认，无待办。")
    with open(os.path.join(work_dir, "digest.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(dg) + "\n")

    with open(os.path.join(work_dir, "decision_register.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(sanitize(register), f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")

    rm.build_manifest(input_dir, work_dir, output_dir, case_id, argv_for_manifest)
    finalized = bool(decisions.get("confirmed") or decisions.get("overrides"))
    print("PIPELINE_%s OK: status=%s, outcomes=%s, decisions_pending=%d"
          % ("FINALIZE" if finalized else "RUN", status, sorted(inference.keys()),
             sum(1 for d in decisions_out if d["status"] == "pending")))
    return 0


# ---------------------------------------------------------------- CLI
def load_decisions(work_dir):
    p = os.path.join(work_dir, "decisions.json")
    if os.path.isfile(p):
        return load_json(p)
    return {"confirmed": [], "overrides": {}}


SETTABLE = {"group_column", "outcomes", "groups", "unit", "alpha"}


def main():
    ap = argparse.ArgumentParser(description="stats-run-gates 一键 baseline pipeline")
    ap.add_argument("mode", choices=["run", "decide", "finalize"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--plan", default=None, help="分析计划 JSON（group_column/outcomes/groups/unit/alpha）")
    ap.add_argument("--group-by", dest="group_by", default=None)
    ap.add_argument("--outcomes", default=None, help="逗号分隔")
    ap.add_argument("--groups", default=None, help="逗号分隔的分组子集标签")
    ap.add_argument("--unit", default=None)
    ap.add_argument("--confirm", action="append", default=[], help="decide: 确认指定 DEC id")
    ap.add_argument("--confirm-all", action="store_true")
    ap.add_argument("--set", dest="sets", action="append", default=[], help="decide: key=value 覆盖")
    args, unknown = ap.parse_known_args()

    if args.mode == "decide":
        reg_path = os.path.join(args.work, "decision_register.json")
        if not os.path.isfile(reg_path):
            print("DECIDE_FAIL: 未找到 %s（先运行 run）" % reg_path)
            return 1
        decisions = load_decisions(args.work)
        register = load_json(reg_path)
        valid_ids = {d["id"] for d in register}
        if args.confirm_all:
            decisions["confirmed"] = sorted(valid_ids)
        for cid in args.confirm:
            if cid not in valid_ids:
                print("DECIDE_FAIL: 未知裁决 id %s（有效: %s）" % (cid, sorted(valid_ids)))
                return 1
            if cid not in decisions["confirmed"]:
                decisions["confirmed"].append(cid)
        for kv in args.sets:
            if "=" not in kv:
                print("DECIDE_FAIL: --set 需要 key=value: %s" % kv)
                return 1
            k, v = kv.split("=", 1)
            if k not in SETTABLE:
                print("DECIDE_FAIL: 不可覆盖的键 %s（可覆盖: %s）" % (k, sorted(SETTABLE)))
                return 1
            if k in ("outcomes", "groups"):
                v = [s.strip() for s in v.split(",") if s.strip()]
            decisions["overrides"][k] = v
        decisions["confirmed"] = sorted(set(decisions["confirmed"]))
        write_json(decisions, os.path.join(args.work, "decisions.json"))
        print("DECIDE OK: confirmed=%s overrides=%s（随后请运行 finalize）"
              % (decisions["confirmed"], sorted(decisions["overrides"].keys())))
        return 0

    if args.mode == "finalize" and not os.path.isfile(os.path.join(args.work, "decisions.json")):
        print("FINALIZE_WARN: decisions.json 不存在，按空裁决复跑（digest 待确认项将保留 PENDING）")
    decisions = load_decisions(args.work)
    argv_for_manifest = [a for a in sys.argv[2:]]
    return run_core(args.input, args.work, args.output, args, decisions, argv_for_manifest)


if __name__ == "__main__":
    sys.exit(main())
