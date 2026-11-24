#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline_d.py — interpretation-tribunal 一键 baseline（run / decide / finalize）。

用法：
  python3 pipeline_d.py run --input /input --work /app/work --output /app/output \
      [--outcome 列名] [--group 列名] [--levels a,b] [--unit 单位] [--alpha 0.05]
  python3 pipeline_d.py decide --work /app/work --set outcome=c2 [--set group=c4 ...]
  python3 pipeline_d.py finalize --input /input --work /app/work --output /app/output

产出：result.json（9 个契约字段 + claims 证据绑定数组 + sources/reproducibility/
uncertainty/exceptions/decisions）、report.md（结果解释章节每句结论句以 [ev:Hk]
结尾，且与 result.json.claims[].sentence 逐字一致）、digest.md（≤5 项待确认裁决）。

统计核心为本目录 statcore_d.py（纯标准库）；措辞纪律见 wording_lint.py，
结论-证据绑定见 claim_bind.py。finalize 会在重写交付物后自动跑这两项检查。
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
import statcore_d as sc

VERSION = "1.0.0"
SEED = 20240501
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "-"}
BOOT_B = 2000


# ---------------------------------------------------------------------------
# 数据接入
# ---------------------------------------------------------------------------

def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def is_missing(tok):
    return tok is None or tok.strip().lower() in MISSING_TOKENS


def to_float(tok):
    if is_missing(tok):
        return None
    try:
        return float(tok.strip())
    except (ValueError, AttributeError):
        return None


def sniff_header(rows):
    """表头嗅探：首行的类型签名（数值/文本逐列）与其余行的众数签名不同
    且首行含非数值单元格时，判定首行为表头。可正确处理无表头但末列为
    文本标签的 CSV（如 iris）。"""
    if len(rows) < 2:
        return False

    def sig(cells):
        return tuple(0 if (to_float(c) is not None or is_missing(c)) else 1
                     for c in cells)

    sig0 = sig(rows[0])
    if not any(sig0):
        return False  # 首行全数值，不可能是表头
    from collections import Counter
    rest = Counter(sig(r) for r in rows[1:21])
    modal = rest.most_common(1)[0][0]
    return sig0 != modal


def load_csv_table(path):
    text = read_text(path)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if r]
    if not rows:
        raise ValueError("空 CSV 文件: %s" % path)
    if sniff_header(rows):
        cols = [c.strip() for c in rows[0]]
        data = rows[1:]
    else:
        cols = ["c%d" % i for i in range(len(rows[0]))]
        data = rows
    return cols, data


def load_db_table(path):
    con = sqlite3.connect(path)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            raise ValueError("SQLite 中无用户表: %s" % path)
        cur.execute('SELECT * FROM "%s"' % tables[0])
        cols = [d[0] for d in cur.description]
        rows = [["" if v is None else str(v) for v in r] for r in cur.fetchall()]
        return tables[0], cols, rows
    finally:
        con.close()


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 列类型与启发式选择
# ---------------------------------------------------------------------------

def column_profiles(cols, rows):
    profs = {}
    for j, name in enumerate(cols):
        vals = [r[j] if j < len(r) else "" for r in rows]
        miss = sum(1 for v in vals if is_missing(v))
        nums = [to_float(v) for v in vals if not is_missing(v)]
        numeric = bool(nums) and all(v is not None for v in nums)
        distinct = len(set(v.strip() for v in vals if not is_missing(v)))
        profs[name] = {
            "index": j, "missing": miss, "numeric": numeric,
            "distinct": distinct,
        }
    return profs


def guess_group(cols, profs):
    for name in cols:
        p = profs[name]
        if not p["numeric"] and p["distinct"] >= 2:
            return name, "启发式：首个非数值列且取值数>=2"
    cands = [(profs[n]["distinct"], n) for n in cols
             if profs[n]["numeric"] and 2 <= profs[n]["distinct"] <= 10]
    if cands:
        cands.sort()
        return cands[0][1], "启发式：取值数最少的数值列（2..10 个水平）"
    cands = [(profs[n]["distinct"], n) for n in cols
             if profs[n]["numeric"] and profs[n]["distinct"] >= 2]
    if cands:
        cands.sort()
        return cands[0][1], "启发式（低置信）：取值数最少的数值列；水平偏多，建议 --levels 限定"
    return None, "未找到可用分组变量"


def guess_outcome(cols, profs, group, task_text):
    task_l = (task_text or "").lower()
    for name in cols:
        if name == group or not profs[name]["numeric"]:
            continue
        if name.lower() in task_l:
            return name, "启发式：列名出现在 task.md 中"
    for name in cols:
        if name != group and profs[name]["numeric"]:
            return name, "启发式：首个非分组数值列；请人工核对（decide --set outcome=...）"
    return None, "未找到可用结果变量"


def extract_unit(task_text, outcome):
    if not task_text:
        return None
    if outcome:
        m = re.search(re.escape(outcome) + r"\s*[（(]\s*([^\s（）()，。；]+)\s*[）)]",
                      task_text)
        if m and m.group(1).lower() not in ("单位", "unit"):
            return m.group(1)
    m = re.search(r"单位\s*[是为：:]?\s*([^\s，。；：:（）()]+)", task_text)
    if m:
        return m.group(1)
    return None


def fmt_group_label(v):
    """分组水平显示：整数值浮点显示为整数。"""
    try:
        f = float(v)
        if f == int(f):
            return str(int(f))
        return ("%g" % f)
    except (ValueError, TypeError):
        return str(v)


def glabel(g):
    s = str(g)
    return s if s.endswith("组") else s + "组"


# ---------------------------------------------------------------------------
# 数字展示（claim_bind 按展示精度做容差核对，改动须同步 references）
# ---------------------------------------------------------------------------

def fmt_p(p):
    return "p<0.0001" if p < 0.0001 else ("p=%.4f" % p)


def unit_suffix(unit):
    """句子中的单位后缀；单位未注明时留空。"""
    return (" " + unit) if unit and unit != "未注明" else ""


def fmt3(x):
    return "%.3f" % x


# ---------------------------------------------------------------------------
# 主分析
# ---------------------------------------------------------------------------

def analyze(input_dir, work_dir, output_dir, overrides):
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    exceptions = []
    notes = []

    # ---- case.json / task.md ----
    case_path = os.path.join(input_dir, "case.json")
    case = {}
    if os.path.exists(case_path):
        case = json.loads(read_text(case_path))
    else:
        exceptions.append("未找到 case.json，按空配置继续")
    case_id = case.get("case_id", "unknown-case")
    constraints = case.get("constraints", {}) or {}
    task_path = os.path.join(input_dir, "task.md")
    task_text = read_text(task_path) if os.path.exists(task_path) else ""

    alpha = float(overrides.get("alpha") or constraints.get("alpha") or 0.05)

    # ---- 数据文件 ----
    data_files = case.get("data_files") or [
        f for f in sorted(os.listdir(input_dir))
        if f.lower().endswith((".csv", ".db", ".sqlite", ".sqlite3"))]
    sources = {}
    csv_path = db_path = None
    for f in data_files:
        p = os.path.join(input_dir, f)
        if not os.path.exists(p):
            exceptions.append("数据文件缺失: %s" % f)
            continue
        sources[f] = {"sha256": sha256_of(p), "bytes": os.path.getsize(p)}
        low = f.lower()
        if low.endswith(".csv") and csv_path is None:
            csv_path = p
        elif low.endswith((".db", ".sqlite", ".sqlite3")) and db_path is None:
            db_path = p

    # ---- 主表（CSV 优先，SQLite 兜底）----
    if csv_path:
        cols, rows = load_csv_table(csv_path)
        primary = os.path.basename(csv_path)
    elif db_path:
        _, cols, rows = load_db_table(db_path)
        primary = os.path.basename(db_path)
    else:
        raise RuntimeError("无可用数据文件（CSV/SQLite）")

    # SQLite 一致性（行数口径，轻量）
    if db_path and csv_path:
        try:
            _, db_cols, db_rows = load_db_table(db_path)
            if len(db_rows) != len(rows):
                notes.append("CSV 行数(%d) 与 SQLite 行数(%d) 不一致，"
                             "以 CSV 为主源，建议人工确认口径" % (len(rows), len(db_rows)))
            else:
                notes.append("CSV 与 SQLite 行数一致（%d 行）；"
                             "数值口径（含 TEXT 存储）已按浮点解析" % len(rows))
        except Exception as e:  # noqa: BLE001
            exceptions.append("SQLite 一致性核对失败: %s" % e)

    rows_in = len(rows)
    profs = column_profiles(cols, rows)

    # ---- 清洗：完全重复 dedupe_keep_first ----
    seen = set()
    dedup_rows = []
    dup_count = 0
    for r in rows:
        key = tuple(r)
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        dedup_rows.append(r)
    rows = dedup_rows

    # ---- 变量决定 ----
    group_col, group_why = (overrides.get("group"), "人工指定") if overrides.get("group") \
        else guess_group(cols, profs)
    outcome_col, outcome_why = (overrides.get("outcome"), "人工指定") if overrides.get("outcome") \
        else guess_outcome(cols, profs, group_col, task_text)
    if not group_col or not outcome_col:
        raise RuntimeError("无法确定结果变量/分组变量：%s / %s" % (outcome_why, group_why))
    unit = overrides.get("unit") or extract_unit(task_text, outcome_col) or "未注明"
    levels = overrides.get("levels")
    if isinstance(levels, str):
        levels = [s.strip() for s in levels.split(",") if s.strip()]

    gj, oj = profs[group_col]["index"], profs[outcome_col]["index"]

    # ---- 清洗：缺失 report_and_exclude（按分析变量有效 n）----
    missing_by_column = {c: profs[c]["missing"] for c in cols if profs[c]["missing"]}
    used = []
    miss_excluded = 0
    for r in rows:
        gv = r[gj] if gj < len(r) else ""
        ov = to_float(r[oj] if oj < len(r) else "")
        if is_missing(gv) or ov is None:
            miss_excluded += 1
            continue
        if levels is not None and fmt_group_label(gv) not in levels:
            continue
        used.append((fmt_group_label(gv), ov))
    rows_used = len(used)
    if rows_in and miss_excluded / max(rows_in, 1) > 0.2:
        notes.append("缺失排除比例较高（%d/%d 行），剩余样本代表性需人工确认"
                     % (miss_excluded, rows_in))

    # ---- 异常值：1.5xIQR 只标记不删除（按结果变量总体）----
    all_out = [v for _, v in used]
    outlier_count = 0
    if len(all_out) >= 4:
        srt = sorted(all_out)
        q1, q3 = sc._quantile(srt, 0.25), sc._quantile(srt, 0.75)
        iqr = q3 - q1
        lo_f, hi_f = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier_count = sum(1 for v in all_out if v < lo_f or v > hi_f)

    # ---- 分组 ----
    groups = {}
    order = []
    for g, v in used:
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(v)
    if levels is not None:
        order = [g for g in levels if g in groups]
    k = len(order)
    if k < 2:
        raise RuntimeError("有效分组水平不足（%d 个）" % k)
    gdata = [groups[g] for g in order]
    ns = [len(g) for g in gdata]

    # ---- 描述统计 ----
    desc = {
        "outcome": outcome_col, "group": group_col, "unit": unit,
        "overall": sc.descriptive(all_out),
        "by_group": {g: sc.descriptive(groups[g]) for g in order},
    }

    # ---- 假设 ----
    normality = {}
    all_normal = True
    for g in order:
        d = groups[g]
        res = sc.dagostino_k2(d)
        if res is None:
            normality[g] = {"n": len(d), "K2": None, "p": None,
                            "note": "n<8，保守按非正态处理"}
            all_normal = False
        else:
            k2, p, _, _ = res
            normality[g] = {"n": len(d), "K2": k2, "p": p,
                            "normal_at_alpha": bool(p >= alpha)}
            if p < alpha:
                all_normal = False
    lev_w, lev_df1, lev_df2, lev_p = sc.levene_median(gdata)
    var_equal = bool(lev_p >= alpha)

    # ---- 路线门控 ----
    if k == 2:
        if all_normal and var_equal:
            route, method = "student_t", "Student 独立样本 t 检验"
            reason = "normal_ok_var_equal"
        elif all_normal:
            route, method = "welch_t", "Welch t 检验"
            reason = "normal_ok_var_unequal"
        else:
            route, method = "mann_whitney", "Mann-Whitney U 检验（tie 校正正态近似）"
            reason = "normality_violated"
    else:
        if all_normal and var_equal:
            route, method = "anova", "单因素方差分析（ANOVA）"
            reason = "normal_ok_var_equal"
        elif all_normal:
            route, method = "welch_anova", "Welch 方差分析（异方差稳健）"
            reason = "normal_ok_var_unequal"
        else:
            route, method = "kruskal_wallis", "Kruskal-Wallis H 检验（tie 校正）"
            reason = "normality_violated"
    if not all_normal and any(n < 8 for n in ns):
        reason += "+small_n_conservative"

    # ---- 主检验 + 敏感性对照 ----
    sensitivity = None
    if route == "student_t":
        stat, df, p = sc.student_t(gdata[0], gdata[1])
        df_list = [df]
        t_w, df_w, p_w = sc.welch_t(gdata[0], gdata[1])
        sensitivity = {"method": "Welch t 检验", "statistic": t_w, "df": [df_w],
                       "p": p_w, "note": "方差不齐情形下的敏感性对照"}
    elif route == "welch_t":
        stat, df, p = sc.welch_t(gdata[0], gdata[1])
        df_list = [df]
        t_s, df_s, p_s = sc.student_t(gdata[0], gdata[1])
        sensitivity = {"method": "Student t 检验", "statistic": t_s, "df": [df_s],
                       "p": p_s, "note": "方差齐性成立情形下的敏感性对照"}
    elif route == "mann_whitney":
        stat, z, p = sc.mann_whitney(gdata[0], gdata[1])
        df_list = []
        t_w, df_w, p_w = sc.welch_t(gdata[0], gdata[1])
        sensitivity = {"method": "Welch t 检验", "statistic": t_w, "df": [df_w],
                       "p": p_w,
                       "note": "参数路线敏感性对照（大样本下结论方向应与主检验一致）"}
    elif route == "anova":
        stat, df1, df2, p, ss_b, ss_w, ss_t = sc.anova_oneway(gdata)
        df_list = [df1, df2]
        f_w, wd1, wd2, p_w = sc.welch_anova(gdata)
        sensitivity = {"method": "Welch 方差分析", "statistic": f_w,
                       "df": [wd1, wd2], "p": p_w, "note": "异方差敏感性对照"}
    elif route == "welch_anova":
        stat, df1, df2, p = sc.welch_anova(gdata)
        df_list = [df1, df2]
        f_c, cd1, cd2, p_c, ss_b, ss_w, ss_t = sc.anova_oneway(gdata)
        sensitivity = {"method": "经典单因素 ANOVA", "statistic": f_c,
                       "df": [cd1, cd2], "p": p_c,
                       "note": "方差齐性成立情形下的经典对照统计量"}
    else:  # kruskal_wallis
        stat, df_kw, p = sc.kruskal_wallis(gdata)
        df_list = [df_kw]
        f_c, cd1, cd2, p_c, ss_b, ss_w, ss_t = sc.anova_oneway(gdata)
        sensitivity = {"method": "经典单因素 ANOVA", "statistic": f_c,
                       "df": [cd1, cd2], "p": p_c,
                       "note": "参数路线敏感性对照（结论方向应与秩检验一致）"}

    # ---- 效应量与 CI ----
    if k == 2:
        g_eff = sc.hedges_g(gdata[0], gdata[1])
        g_ci = sc.bootstrap_hedges_g_ci(gdata[0], gdata[1], B=BOOT_B, seed=SEED,
                                        alpha=alpha)
        effect = {"name": "hedges_g", "symbol": "Hedges g", "value": g_eff,
                  "ci95": list(g_ci) if g_ci else None,
                  "magnitude": sc.effect_magnitude("hedges_g", g_eff),
                  "method": "pooled SD 标准化 + bootstrap B=%d seed=%d percentile CI"
                            % (BOOT_B, SEED)}
        if route == "mann_whitney":
            hl = sc.hodges_lehmann(gdata[0], gdata[1], seed=SEED)
            hl_ci = sc.bootstrap_hl_ci(gdata[0], gdata[1], B=BOOT_B, seed=SEED,
                                       alpha=alpha)
            ci_block = {"parameter": "median_difference (%s - %s, Hodges-Lehmann)"
                                     % (order[0], order[1]),
                        "estimate": hl, "ci95": list(hl_ci),
                        "method": "Hodges-Lehmann 中位数差 + bootstrap B=%d percentile"
                                  % BOOT_B}
        else:
            diff, ci = sc.mean_diff_welch_ci(gdata[0], gdata[1], alpha=alpha)
            ci_block = {"parameter": "mean_difference (%s - %s)"
                                     % (order[0], order[1]),
                        "estimate": diff, "ci95": list(ci),
                        "method": "Welch t 置信区间"}
    else:
        eta2 = sc.eta_squared(ss_b, ss_t)
        if route == "kruskal_wallis":
            eps2 = sc.epsilon_squared_kw(stat, sum(ns), k)
            effect = {"name": "epsilon_squared", "symbol": "ε²", "value": eps2,
                      "ci95": None,
                      "magnitude": sc.effect_magnitude("eta2", eps2),
                      "aux": {"eta_squared": eta2},
                      "note": "KW 路线报告 ε²；η² 为经典分解参考值"}
        else:
            om2 = sc.omega_squared(ss_b, ss_w, ss_t, cd2, k)
            effect = {"name": "omega_squared", "symbol": "ω²", "value": om2,
                      "ci95": None,
                      "magnitude": sc.effect_magnitude("eta2", om2),
                      "aux": {"eta_squared": eta2},
                      "note": "ω² 为主（偏倚校正）；η² 见 aux；CI 未自助估计"}
        means = {g: desc["by_group"][g]["mean"] for g in order}
        hi = max(means, key=means.get)
        lo = min(means, key=means.get)
        diff, ci = sc.mean_diff_welch_ci(groups[hi], groups[lo], alpha=alpha)
        ci_block = {"parameter": "mean_difference (%s - %s，均值最高组-最低组)"
                                 % (hi, lo),
                    "estimate": diff, "ci95": list(ci),
                    "method": "Welch t 置信区间（事后对照，未做多重校正）"}

    # ---- 事后两两比较（k>=3，与主检验同路线，Holm 校正）----
    posthoc = []
    if k >= 3:
        pairs = [(order[i], order[j])
                 for i in range(k) for j in range(i + 1, k)]
        tested = []
        for a_, b_ in pairs:
            da, db = groups[a_], groups[b_]
            if route == "anova":
                _, _, pp = sc.student_t(da, db)
                pm = "Student t 检验"
            elif route == "welch_anova":
                _, _, pp = sc.welch_t(da, db)
                pm = "Welch t 检验"
            else:
                _, _, pp = sc.mann_whitney(da, db)
                pm = "Mann-Whitney U 检验"
            tested.append((a_, b_, pm, pp))
        adj = sc.holm_adjust([x[3] for x in tested])
        for (a_, b_, pm, pp), pa in zip(tested, adj):
            posthoc.append({"a": a_, "b": b_, "method": pm, "p_raw": pp,
                            "p_adj": pa, "significant": bool(pa < alpha)})

    # ------------------------------------------------------------------
    # claims 构建（结论-证据绑定的核心）
    # ------------------------------------------------------------------
    claims = []
    means = {g: desc["by_group"][g]["mean"] for g in order}
    mag_cn = {"negligible": "可忽略", "small": "小", "medium": "中等",
              "large": "大"}

    def practical_tail(mag):
        if mag in ("negligible", "small"):
            return ("统计显著并不等同于实际重要，该差异的实际意义有限，"
                    "是否达到最小实际重要差异 Δ 需结合领域标准判断。")
        if mag == "medium":
            return ("提示该差异可能具有实际意义；"
                    "是否达到实际重要需结合领域阈值 Δ 判断。")
        return ("表明该差异可能具有实际意义；"
                "其实际重要性仍需结合领域阈值判断。")

    def make_claim(cid, a_, b_, sig, p_used, method_name, es, p_note=""):
        ma, mb = means.get(a_), means.get(b_)
        if ma is None or mb is None:
            diff = None
            direction = "no_difference"
        else:
            diff = ma - mb
            if not sig:
                direction = "no_difference"
            else:
                direction = "increase" if diff > 0 else "decrease"
        claim = {
            "id": cid, "outcome": outcome_col,
            "comparison": "%s vs %s" % (a_, b_) if a_ else "全部组 omnibus",
            "direction": direction, "significant": bool(sig),
            "p": p_used, "alpha": alpha,
            "effect_size": {"name": es["name"], "value": es["value"],
                            "ci95": es.get("ci95")},
            "method": method_name,
            "group_a": a_, "group_b": b_,
            "mean_a": ma, "mean_b": mb, "diff": diff,
            "magnitude": es.get("magnitude"),
        }
        return claim

    def two_group_sentence(cl, method_name, diff_label, diff_val):
        a_, b_ = cl["group_a"], cl["group_b"]
        if cl["significant"]:
            winner = glabel(a_) if (cl["diff"] or 0) > 0 else glabel(b_)
            s = ("在 α=%s 水平下，%s与%s的 %s 差异具有统计学意义（%s，%s）；"
                 "%s的均值更高，%s（%s−%s）为 %s%s。[ev:%s]"
                 % (("%g" % alpha), glabel(a_), glabel(b_), outcome_col,
                    method_name, fmt_p(cl["p"]), winner, diff_label,
                    a_, b_, fmt3(diff_val), unit_suffix(unit), cl["id"]))
        else:
            s = ("在 α=%s 水平下，%s与%s的 %s 差异不具有统计学意义（%s，%s）；"
                 "证据不足以支持「两组 %s 存在差异」的结论。[ev:%s]"
                 % (("%g" % alpha), glabel(a_), glabel(b_), outcome_col,
                    method_name, fmt_p(cl["p"]), outcome_col, cl["id"]))
        return s

    def two_group_practical(cl, es_symbol):
        if cl["significant"]:
            ci = cl["effect_size"]["ci95"]
            ci_txt = ("，95%% 置信区间为 [%s, %s]" % (fmt3(ci[0]), fmt3(ci[1]))
                      ) if ci else ""
            return ("效应量 %s = %s%s，按常用阈值属于%s效应；%s[ev:%s]"
                    % (es_symbol, fmt3(cl["effect_size"]["value"]), ci_txt,
                       mag_cn[cl["magnitude"]],
                       practical_tail(cl["magnitude"]), cl["id"]))
        tail = ("阴性结果可能受样本量限制（最小组 n=%d），检验效能有限；"
                % min(ns)) if min(ns) < 30 else ""
        return ("不宜将「不具有统计学意义」解读为「不存在差异」；%s"
                "实际意义判断需结合效应量置信区间与领域阈值。[ev:%s]"
                % (tail, cl["id"]))

    if k == 2:
        a_, b_ = order[0], order[1]
        h1 = make_claim("H1", a_, b_, p < alpha, p, method, effect)
        if route == "mann_whitney":
            diff_label, diff_val = "中位数差（Hodges-Lehmann）", ci_block["estimate"]
        else:
            diff_label, diff_val = "均值差", h1["diff"]
        h1["diff"] = diff_val if route == "mann_whitney" else h1["diff"]
        h1["diff_label"] = diff_label
        h1["sentence"] = two_group_sentence(h1, method, diff_label, diff_val)
        h1["practical_note"] = two_group_practical(h1, "Hedges g")
        claims.append(h1)
    else:
        hi = max(means, key=means.get)
        lo = min(means, key=means.get)
        h1 = make_claim("H1", hi, lo, p < alpha, p, method, effect)
        if h1["significant"]:
            h1["sentence"] = (
                "在 α=%s 水平下，%s各组间 %s 的差异具有统计学意义（%s，%s）；"
                "均值最高的%s与最低的%s相差 %s%s。[ev:H1]"
                % (("%g" % alpha), group_col, outcome_col, method, fmt_p(p),
                   glabel(hi), glabel(lo), fmt3(means[hi] - means[lo]),
                   unit_suffix(unit)))
        else:
            h1["sentence"] = (
                "在 α=%s 水平下，%s各组间 %s 的差异不具有统计学意义（%s，%s）；"
                "证据不足以支持「%s 随 %s 不同而存在差异」的结论。[ev:H1]"
                % (("%g" % alpha), group_col, outcome_col, method, fmt_p(p),
                   outcome_col, group_col))
        if h1["significant"]:
            h1["practical_note"] = (
                "效应量 %s = %s（η² = %s），按常用阈值属于%s效应；%s[ev:H1]"
                % (effect["symbol"], fmt3(effect["value"]),
                   fmt3(effect["aux"]["eta_squared"]),
                   mag_cn[effect["magnitude"]],
                   practical_tail(effect["magnitude"])))
        else:
            h1["practical_note"] = (
                "不宜将「不具有统计学意义」解读为「不存在差异」；"
                "实际意义判断需结合效应量与领域阈值。[ev:H1]")
        claims.append(h1)
        for idx, ph in enumerate(posthoc, start=2):
            da, db = groups[ph["a"]], groups[ph["b"]]
            if ph["method"].startswith("Mann"):
                es_val = sc.hodges_lehmann(da, db, seed=SEED)
                es_ci = list(sc.bootstrap_hl_ci(da, db, B=BOOT_B, seed=SEED,
                                                alpha=alpha))
                es = {"name": "hodges_lehmann", "value": es_val, "ci95": es_ci,
                      "magnitude": None}
            else:
                es_val = sc.hedges_g(da, db)
                es_ci = list(sc.bootstrap_hedges_g_ci(da, db, B=BOOT_B,
                                                      seed=SEED, alpha=alpha))
                es = {"name": "hedges_g", "value": es_val, "ci95": es_ci,
                      "magnitude": sc.effect_magnitude("hedges_g", es_val)}
            cl = make_claim("H%d" % idx, ph["a"], ph["b"], ph["significant"],
                            ph["p_adj"], ph["method"] + "（Holm 校正）", es)
            cl["p_raw"] = ph["p_raw"]
            if es["name"] == "hodges_lehmann":
                # 秩路线句中引用的是中位数差，diff 与之一致以便机器核对
                cl["diff"] = es["value"]
            if cl["significant"]:
                cl["sentence"] = (
                    "在 α=%s 水平下，经 Holm 校正，%s与%s的 %s 差异具有统计学意义"
                    "（%s，调整后 %s）。[ev:%s]"
                    % (("%g" % alpha), glabel(ph["a"]), glabel(ph["b"]),
                       outcome_col, ph["method"], fmt_p(ph["p_adj"]), cl["id"]))
            else:
                cl["sentence"] = (
                    "在 α=%s 水平下，经 Holm 校正，%s与%s的 %s 差异不具有统计学意义"
                    "（%s，调整后 %s）；未校正结果不应单独作为结论依据。[ev:%s]"
                    % (("%g" % alpha), glabel(ph["a"]), glabel(ph["b"]),
                       outcome_col, ph["method"], fmt_p(ph["p_adj"]), cl["id"]))
            if cl["significant"]:
                if es["name"] == "hedges_g":
                    cl["practical_note"] = (
                        "该两组比较的事后效应量 Hedges g = %s，"
                        "95%% 置信区间为 [%s, %s]，按常用阈值属于%s效应；"
                        "实际重要性仍需结合领域阈值判断。[ev:%s]"
                        % (fmt3(es["value"]), fmt3(es_ci[0]), fmt3(es_ci[1]),
                           mag_cn[es["magnitude"]], cl["id"]))
                else:
                    cl["practical_note"] = (
                        "该两组比较的事后中位数差（Hodges-Lehmann）为 %s%s，"
                        "bootstrap 95%% 置信区间为 [%s, %s]；"
                        "实际重要性仍需结合领域阈值判断。[ev:%s]"
                        % (fmt3(es["value"]), unit_suffix(unit), fmt3(es_ci[0]),
                           fmt3(es_ci[1]), cl["id"]))
            else:
                cl["practical_note"] = (
                    "该两组差异校正后不具有统计学意义；"
                    "不宜解读为「不存在差异」，实际意义需结合领域阈值判断。[ev:%s]"
                    % cl["id"])
            claims.append(cl)

    # ------------------------------------------------------------------
    # 状态、局限、不确定性
    # ------------------------------------------------------------------
    limitations = []
    uncertainty = []
    if min(ns) < 30:
        limitations.append("部分组样本量较小（最小组 n=%d），检验效能与估计稳定性有限。"
                           % min(ns))
    if not all_normal:
        limitations.append("正态性假设未满足（或样本量不足以检验），结论依赖秩方法"
                           "或对分布稳健的检验。")
    if not var_equal:
        limitations.append("Levene 检验提示方差不齐；已采用异方差稳健路线，"
                           "经典方差分析结果仅作敏感性对照。")
    if k >= 3:
        limitations.append("本分析涉及 %d 组间多重比较，已做 Holm 校正；"
                           "未校正 p 不应单独作为结论依据。" % k)
    limitations.append("数据为观察性来源，组间差异不能推断因果。")
    if miss_excluded:
        limitations.append("缺失值按 report_and_exclude 口径处理（排除 %d 行），"
                           "剩余样本的代表性需人工确认。" % miss_excluded)
    if outlier_count:
        limitations.append("结果变量存在 %d 个 1.5×IQR 栅栏外取值，按口径只标记"
                           "未删除；对结论的敏感性需人工评估。" % outlier_count)
    if unit == "未注明":
        limitations.append("结果变量单位未在任务说明中注明，数值口径以原始数据为准。")
    uncertainty.append("置信区间刻画的是估计量的不确定性，并非个体取值的范围。")
    uncertainty.append("bootstrap CI 基于 B=%d、seed=%d，复跑可完全复现。"
                       % (BOOT_B, SEED))
    uncertainty.extend(notes)
    if sensitivity is not None:
        agree = (sensitivity["p"] < alpha) == (p < alpha)
        uncertainty.append("敏感性对照（%s）与主检验结论%s。"
                           % (sensitivity["method"], "一致" if agree else "不一致，需谨慎解读"))

    status = "complete"
    # levels 限定是有意的子集分析，不计入数据损失；仅看缺失排除比例
    pool = miss_excluded + rows_used
    if exceptions or rows_used < 8 or (pool and miss_excluded > 0.5 * pool):
        status = "partial"

    decisions = {
        "outcome": outcome_col, "group": group_col,
        "levels": levels, "unit": unit, "alpha": alpha,
        "outcome_basis": outcome_why, "group_basis": group_why,
        "source": "manual" if overrides else "auto+defaults",
    }

    result = {
        "case_id": case_id,
        "status": status,
        "cleaning": {
            "rows_in": rows_in, "rows_used": rows_used,
            "missing_policy": "report_and_exclude",
            "missing_by_column": missing_by_column,
            "missing_excluded_rows": miss_excluded,
            "duplicate_policy": "dedupe_exact_keep_first",
            "duplicates_removed": dup_count,
            "outlier_policy": "1.5xIQR_flag_only",
            "outliers_flagged": {outcome_col: outlier_count},
        },
        "descriptive": desc,
        "hypothesis_test": {
            "route": route, "method": method, "reason_code": reason,
            "statistic": stat, "df": df_list, "p": p,
            "p_display": fmt_p(p), "alpha": alpha,
            "normality": normality, "levene": {
                "W": lev_w, "df": [lev_df1, lev_df2], "p": lev_p,
                "equal_variance_at_alpha": var_equal},
            "sensitivity": sensitivity,
            "posthoc": posthoc,
        },
        "effect_size": effect,
        "confidence_interval": ci_block,
        "interpretation": {
            "summary": [c["sentence"] for c in claims],
            "practical_significance": [c["practical_note"] for c in claims],
            "ci_meaning": "置信区间刻画的是估计量的不确定性，并非个体取值的范围。",
            "evidence_binding": "结果解释章节每句结论句以 [ev:Hk] 结尾，"
                                "可在 claims 数组中解析复核",
            "caveats": ["统计显著并不等同于实际重要，两者分开表述；",
                        "数据为观察性来源，组间差异不能推断因果。"],
        },
        "limitations": limitations,
        "claims": claims,
        "sources": sources,
        "reproducibility": {
            "seed": SEED, "python": platform.python_version(),
            "platform": platform.platform(),
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "versions": {"statcore_d": VERSION, "pipeline_d": VERSION,
                         "wording_lint": VERSION, "claim_bind": VERSION},
        },
        "uncertainty": uncertainty,
        "exceptions": exceptions,
        "decisions": decisions,
    }
    ctx = {
        "case_id": case_id, "primary": primary, "cols": cols, "profs": profs,
        "result": result, "order": order, "k": k, "ns": ns,
        "group_col": group_col, "outcome_col": outcome_col, "unit": unit,
        "alpha": alpha, "route": route, "method": method, "reason": reason,
        "task_head": (task_text or "").splitlines()[:5],
        "group_why": group_why, "outcome_why": outcome_why,
        "overrides": overrides,
    }
    return ctx


# ---------------------------------------------------------------------------
# 报告与摘要渲染
# ---------------------------------------------------------------------------

def render_report(ctx):
    r = ctx["result"]
    desc = r["descriptive"]
    ht = r["hypothesis_test"]
    lines = []
    add = lines.append
    add("# 统计分析报告：%s" % ctx["case_id"])
    add("")
    add("> 本报告由 interpretation-tribunal pipeline 自动生成。"
        "「结果解释」章节每句结论句以 [ev:H<编号>] 结尾，"
        "与 result.json 的 claims 数组一一绑定，可用 claim_bind.py 机器复核；"
        "措辞纪律由 wording_lint.py 机器复核。")
    add("")
    add("## 1 数据接入与清洗")
    add("")
    add("- 主数据源：%s；输入文件 sha256 见 result.json.sources。" % ctx["primary"])
    add("- 行数：原始 %d 行 → 去重后 %d 行 → 分析有效 %d 行。"
        % (r["cleaning"]["rows_in"],
           r["cleaning"]["rows_in"] - r["cleaning"]["duplicates_removed"],
           r["cleaning"]["rows_used"]))
    add("- 缺失：report_and_exclude（按变量有效 n，不零填、不插补），"
        "排除 %d 行；完全重复 dedupe_keep_first 去除 %d 行；"
        "异常值 1.5×IQR 栅栏只标记不删除（%s 列标记 %d 个）。"
        % (r["cleaning"]["missing_excluded_rows"],
           r["cleaning"]["duplicates_removed"],
           desc["outcome"],
           r["cleaning"]["outliers_flagged"].get(desc["outcome"], 0)))
    add("")
    add("## 2 描述统计（结果变量：%s，单位：%s）" % (desc["outcome"], desc["unit"]))
    add("")
    add("| 组别 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max | 偏度 |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for g in ctx["order"]:
        d = desc["by_group"][g]
        add("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (g, d["n"], fmt3(d["mean"]), fmt3(d["sd"]), fmt3(d["median"]),
               fmt3(d["q1"]), fmt3(d["q3"]), fmt3(d["min"]), fmt3(d["max"]),
               fmt3(d["skew"])))
    add("")
    add("## 3 假设检验")
    add("")
    add("路线门控结论：%s（理由码 %s）。"
        % (ht["method"], ht["reason_code"]))
    add("")
    add("| 项目 | 数值 |")
    add("|---|---|")
    norm_txt = []
    for g, nb in ht["normality"].items():
        if nb["K2"] is None:
            norm_txt.append("%s: n=%d（n<8 保守按非正态）" % (g, nb["n"]))
        else:
            norm_txt.append("%s: K²=%.3f, 正态性 p %.4f" % (g, nb["K2"], nb["p"]))
    add("| 正态性（D'Agostino K²） | %s |" % "；".join(norm_txt))
    add("| 方差齐性（Levene, median 中心） | W=%.4f, 齐性 p %.4f |"
        % (ht["levene"]["W"], ht["levene"]["p"]))
    df_txt = ", ".join("%.2f" % d for d in ht["df"]) if ht["df"] else "-"
    add("| 主检验 | %s：统计量 %.4f，df %s，%s |"
        % (ht["method"], ht["statistic"], df_txt, ht["p_display"]))
    if ht["sensitivity"]:
        s = ht["sensitivity"]
        sdf = ", ".join("%.2f" % d for d in s["df"]) if s["df"] else "-"
        add("| 敏感性对照 | %s：统计量 %.4f，df %s，%s（%s） |"
            % (s["method"], s["statistic"], sdf, fmt_p(s["p"]), s["note"]))
    if ht["posthoc"]:
        add("")
        add("| 事后比较（Holm 校正） | 方法 | 原始 p | 调整后 p | 结论 |")
        add("|---|---|---|---|---|")
        for ph in ht["posthoc"]:
            add("| %s vs %s | %s | %s | %s | %s |"
                % (ph["a"], ph["b"], ph["method"], fmt_p(ph["p_raw"]),
                   fmt_p(ph["p_adj"]),
                   "显著" if ph["significant"] else "不显著"))
    add("")
    add("## 4 效应量与置信区间")
    add("")
    es = r["effect_size"]
    ci = r["confidence_interval"]
    add("| 项目 | 数值 |")
    add("|---|---|")
    ci_txt = ("[%s, %s]" % (fmt3(es["ci95"][0]), fmt3(es["ci95"][1]))
              ) if es.get("ci95") else "未估计"
    add("| 效应量 %s | %s（%s效应），95%% CI %s |"
        % (es["symbol"], fmt3(es["value"]),
           {"negligible": "可忽略", "small": "小", "medium": "中等",
            "large": "大"}[es["magnitude"]], ci_txt))
    add("| %s | 估计 %s，95%% CI [%s, %s]（%s） |"
        % (ci["parameter"], fmt3(ci["estimate"]), fmt3(ci["ci95"][0]),
           fmt3(ci["ci95"][1]), ci["method"]))
    add("")
    add("置信区间刻画的是估计量的不确定性，并非个体取值的范围；"
        "区间越宽，估计不确定性越大。")
    add("")
    add("## 5 结果解释")
    add("")
    for c in r["claims"]:
        add(c["sentence"] + c["practical_note"])
        add("")
    add("统计显著并不等同于实际重要；上述结论均为观察性比较，不能推断因果。")
    add("")
    add("## 6 局限与不确定性")
    add("")
    for it in r["limitations"]:
        add("- %s" % it)
    add("")
    add("剩余不确定性说明：")
    for it in r["uncertainty"]:
        add("- %s" % it)
    if r["status"] != "complete":
        add("")
        add("**本次分析状态为 %s**：存在异常或不完整环节（见 exceptions），"
            "上述结论的不确定性高于常规，交付前须人工复核。"
            % r["status"])
    add("")
    add("## 7 复核与运行信息")
    add("")
    add("| 项目 | 数值 |")
    add("|---|---|")
    for f, meta in r["sources"].items():
        add("| 源文件 %s | sha256=%s…（%d 字节） |"
            % (f, meta["sha256"][:12], meta["bytes"]))
    rp = r["reproducibility"]
    add("| 复跑 | seed=%d, python %s, %s, utc %s |"
        % (rp["seed"], rp["python"], rp["platform"], rp["utc"]))
    add("| 裁决 | outcome=%s, group=%s, levels=%s, unit=%s, alpha=%s（%s） |"
        % (r["decisions"]["outcome"], r["decisions"]["group"],
           r["decisions"]["levels"], r["decisions"]["unit"],
           r["decisions"]["alpha"], r["decisions"]["source"]))
    add("| 异常 | %s |" % ("；".join(r["exceptions"]) if r["exceptions"] else "无"))
    add("")
    return "\n".join(lines)


def render_digest(ctx):
    r = ctx["result"]
    ht = r["hypothesis_test"]
    cols_info = []
    for c in ctx["cols"]:
        p = ctx["profs"][c]
        kind = "数值" if p["numeric"] else "文本"
        cols_info.append("%s(%s,缺失%d,取值%d)" % (c, kind, p["missing"],
                                                  p["distinct"]))
    lines = []
    add = lines.append
    add("# digest.md — 待确认裁决（≤5 项）")
    add("")
    add("## 候选列")
    add("")
    add("；".join(cols_info))
    add("")
    add("## 待确认项")
    add("")
    add("1. **结果变量 / 分组变量**：当前 outcome=`%s`（%s），group=`%s`（%s），"
        "levels=%s。核对 task.md 后如需覆盖："
        "`python3 $SKILL_DIR/scripts/pipeline_d.py decide --work /app/work "
        "--set outcome=列名 --set group=列名 --set levels=a,b`"
        % (r["decisions"]["outcome"], ctx["outcome_why"],
           r["decisions"]["group"], ctx["group_why"], r["decisions"]["levels"]))
    add("2. **单位**：当前 `%s`（来自 task.md 或人工指定）。覆盖："
        "`decide --work /app/work --set unit=单位名`" % r["decisions"]["unit"])
    add("3. **检验路线**：%s（理由码 %s）。敏感性对照：%s。"
        % (ht["method"], ht["reason_code"],
           ht["sensitivity"]["method"] if ht["sensitivity"] else "无"))
    add("4. **claims**：共 %d 条，其中显著 %d 条；每条结论句在 report.md 中"
        "以 [ev:Hk] 绑定，可用 claim_bind.py 复核。"
        % (len(r["claims"]), sum(1 for c in r["claims"] if c["significant"])))
    warns = [u for u in r["uncertainty"]]
    add("5. **警示**：%s" % ("；".join(warns) if warns else "无"))
    add("")
    add("确认无误或完成 decide 后执行："
        "`python3 $SKILL_DIR/scripts/pipeline_d.py finalize "
        "--input /input --work /app/work --output /app/output`")
    add("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def _load_decisions(work_dir):
    p = os.path.join(work_dir, "decisions.json")
    if os.path.exists(p):
        return json.loads(read_text(p))
    return {}


def _load_run_config(work_dir):
    p = os.path.join(work_dir, "run_config.json")
    if os.path.exists(p):
        return json.loads(read_text(p)).get("overrides", {})
    return {}


def _save_run_config(work_dir, overrides):
    with open(os.path.join(work_dir, "run_config.json"), "w",
              encoding="utf-8") as f:
        json.dump({"overrides": overrides}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _write_outputs(ctx, work_dir, output_dir):
    result = ctx["result"]
    rp = os.path.join(output_dir, "result.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(render_report(ctx))
    digest = render_digest(ctx)
    for d in (output_dir, work_dir):
        with open(os.path.join(d, "digest.md"), "w", encoding="utf-8") as f:
            f.write(digest)
    return rp


def _self_check(output_dir):
    """内部调用 wording_lint / claim_bind，返回 (ok, messages)。"""
    msgs = []
    ok = True
    try:
        import wording_lint
        v = wording_lint.lint_report(os.path.join(output_dir, "report.md"),
                                     os.path.join(output_dir, "result.json"))
        if v:
            ok = False
            msgs.extend("wording_lint: " + x for x in v)
        else:
            msgs.append("wording_lint: PASS")
    except Exception as e:  # noqa: BLE001
        ok = False
        msgs.append("wording_lint 内部调用失败: %s" % e)
    try:
        import claim_bind
        v = claim_bind.bind_check(os.path.join(output_dir, "report.md"),
                                  os.path.join(output_dir, "result.json"))
        if v:
            ok = False
            msgs.extend("claim_bind: " + x for x in v)
        else:
            msgs.append("claim_bind: PASS")
    except Exception as e:  # noqa: BLE001
        ok = False
        msgs.append("claim_bind 内部调用失败: %s" % e)
    return ok, msgs


def cmd_run(args):
    overrides = {}
    for key in ("outcome", "group", "levels", "unit", "alpha"):
        v = getattr(args, key, None)
        if v is not None:
            overrides[key] = v
    # run 时合并既有 decisions（decide 后再 run 不丢失），并持久化生效配置
    overrides = {**_load_decisions(args.work), **overrides}
    os.makedirs(args.work, exist_ok=True)
    _save_run_config(args.work, overrides)
    ctx = analyze(args.input, args.work, args.output, overrides)
    rp = _write_outputs(ctx, args.work, args.output)
    ok, msgs = _self_check(args.output)
    r = ctx["result"]
    print("pipeline run 完成：status=%s, route=%s, claims=%d"
          % (r["status"], r["hypothesis_test"]["route"], len(r["claims"])))
    print("产出：%s, report.md, digest.md（见 %s）" % (rp, args.output))
    for m in msgs:
        print(m)
    if r["status"] != "complete":
        print("注意：status=%s，异常=%s" % (r["status"], r["exceptions"]))
    return 0 if ok else 1


def cmd_decide(args):
    os.makedirs(args.work, exist_ok=True)
    decisions = _load_decisions(args.work)
    allowed = {"outcome", "group", "levels", "unit", "alpha", "note"}
    for kv in args.set or []:
        if "=" not in kv:
            print("忽略无法解析的 --set 项: %s（须为 key=value）" % kv)
            continue
        key, val = kv.split("=", 1)
        key = key.strip()
        if key not in allowed:
            print("忽略不允许的裁决键: %s（允许：%s）" % (key, ",".join(sorted(allowed))))
            continue
        decisions[key] = val.strip()
    with open(os.path.join(args.work, "decisions.json"), "w",
              encoding="utf-8") as f:
        json.dump(decisions, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("decisions 已写入 %s：%s"
          % (os.path.join(args.work, "decisions.json"),
             json.dumps(decisions, ensure_ascii=False)))
    print("请执行 finalize 重写交付物。")
    return 0


def cmd_finalize(args):
    # 生效配置 = run 时配置 + decide 覆盖，保证 finalize 不静默改变量选择
    overrides = {**_load_run_config(args.work), **_load_decisions(args.work)}
    ctx = analyze(args.input, args.work, args.output, overrides)
    _write_outputs(ctx, args.work, args.output)
    ok, msgs = _self_check(args.output)
    for m in msgs:
        print(m)
    r = ctx["result"]
    print("finalize 完成：status=%s, route=%s, claims=%d -> %s"
          % (r["status"], r["hypothesis_test"]["route"], len(r["claims"]),
             args.output))
    if not ok:
        print("自查未通过：交付物不满足措辞纪律或证据绑定，禁止交付。")
        return 1
    print("自查通过（wording_lint + claim_bind），可以交付。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="interpretation-tribunal pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "finalize"):
        sp = sub.add_parser(name)
        sp.add_argument("--input", default="/input")
        sp.add_argument("--work", default="/app/work")
        sp.add_argument("--output", default="/app/output")
        if name == "run":
            sp.add_argument("--outcome")
            sp.add_argument("--group")
            sp.add_argument("--levels")
            sp.add_argument("--unit")
            sp.add_argument("--alpha", type=float)
    sp = sub.add_parser("decide")
    sp.add_argument("--work", default="/app/work")
    sp.add_argument("--set", action="append", default=[])
    args = ap.parse_args(argv)
    try:
        if args.cmd == "run":
            return cmd_run(args)
        if args.cmd == "decide":
            return cmd_decide(args)
        return cmd_finalize(args)
    except Exception as e:  # noqa: BLE001
        # 诚实 partial：写出带原因的 result.json 骨架
        os.makedirs(args.output, exist_ok=True)
        skeleton = {
            "case_id": "unknown", "status": "failed",
            "cleaning": {}, "descriptive": {}, "hypothesis_test": {},
            "effect_size": {}, "confidence_interval": {},
            "interpretation": {}, "limitations": ["pipeline 执行失败：%s" % e],
            "claims": [], "sources": {},
            "reproducibility": {"seed": SEED,
                                "python": platform.python_version(),
                                "utc": datetime.now(timezone.utc).isoformat(
                                    timespec="seconds")},
            "uncertainty": ["pipeline 未完成，所有数值缺失。"],
            "exceptions": ["%s: %s" % (type(e).__name__, e)],
            "decisions": {},
        }
        with open(os.path.join(args.output, "result.json"), "w",
                  encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=2)
        print("pipeline 失败（已写出 failed 状态 result.json）：%s" % e,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
