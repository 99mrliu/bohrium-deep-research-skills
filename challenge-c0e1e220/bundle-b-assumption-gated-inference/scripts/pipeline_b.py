#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline_b — assumption-gated-inference 一键基线管线（仅标准库）

子命令：
  run       从 /input 原始数据到 /app/output/result.json + report.md，
            决策链写入 result.json.decision_log 与 /app/work/digest.md
  decide    记录人工裁决（group/outcomes/focus/alpha），供 finalize 使用
  finalize  应用裁决重跑并重写交付物

关键设计：每个结局变量的检验选择被记录为**结构化决策链**（每组正态性、
Levene、各组 n、chosen_test、reason_codes、被否决候选检验、每组取值哈希），
可被 scripts/decision_audit.py 从原始数据独立重算审计。
"""
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_b as sc

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "-"}
POSTHOC_MAX_K = 6          # 超过该组数不做两两事后比较（避免组合爆炸）
TEST_NAMES = {
    "student_t": "Student 独立样本 t 检验",
    "welch_t": "Welch 独立样本 t 检验",
    "mannwhitney_u": "Mann-Whitney U 检验（tie 校正渐近）",
    "anova": "单因素方差分析（ANOVA）",
    "welch_anova": "Welch 异方差方差分析",
    "kruskal_wallis": "Kruskal-Wallis H 检验（tie 校正）",
}
STAT_NAMES = {
    "student_t": "t", "welch_t": "t", "mannwhitney_u": "U",
    "anova": "F", "welch_anova": "F_welch", "kruskal_wallis": "H",
}

# ------------------------------------------------------------------ 数据接入


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text_any(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def is_number(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def sniff_header(rows):
    """首行 ≥半数单元格无法解析为数值 → 视为表头。"""
    if len(rows) < 2:
        return False
    bad = sum(0 if is_number(c) else 1 for c in rows[0])
    return bad * 2 >= len(rows[0])


PROFILES = {
    "iris": ["sepal_length", "sepal_width", "petal_length", "petal_width", "class"],
    "wine": ["cultivar", "alcohol", "malic_acid", "ash", "alcalinity_of_ash",
             "magnesium", "total_phenols", "flavanoids", "nonflavanoid_phenols",
             "proanthocyanins", "color_intensity", "hue", "od280_od315", "proline"],
}


def load_csv(path, dataset_hint=""):
    text, enc = read_text_any(path)
    first = text.split("\n", 1)[0]
    delim = max([",", ";", "\t"], key=lambda d: first.count(d))
    rows = [[c.strip() for c in r] for r in csv.reader(text.splitlines(), delimiter=delim)]
    rows = [r for r in rows if any(c != "" for c in r)]
    if not rows:
        return None
    header = sniff_header(rows)
    if header:
        names, data = rows[0], rows[1:]
    else:
        data = rows
        hint = (dataset_hint or "").lower()
        names = None
        for key, prof in PROFILES.items():
            if key in hint and len(prof) == len(rows[0]):
                names = list(prof)
                break
        if names is None:
            names = ["col_%d" % (i + 1) for i in range(len(rows[0]))]
    return {"names": names, "rows": data, "encoding": enc, "header": header,
            "delimiter": delim, "source_type": "csv"}


def load_sqlite(path):
    con = sqlite3.connect(path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        if not tables:
            return None
        t = tables[0]
        names = [d[1] for d in con.execute("PRAGMA table_info(%s)" % t)]
        rows = [[("" if v is None else str(v)) for v in r]
                for r in con.execute("SELECT * FROM %s" % t)]
        return {"names": names, "rows": rows, "encoding": "sqlite",
                "header": True, "delimiter": None, "source_type": "sqlite",
                "table": t}
    finally:
        con.close()


def load_table(input_dir, case):
    """优先 case.json data_files 中第一个 CSV/TSV，否则第一个 SQLite。"""
    files = case.get("data_files") or []
    hint = case.get("dataset", "")
    for f in files:
        if f.lower().endswith((".csv", ".tsv", ".txt")):
            p = os.path.join(input_dir, f)
            if os.path.exists(p):
                t = load_csv(p, hint)
                if t:
                    t["file"] = f
                    return t, None
    for f in files:
        if f.lower().endswith((".db", ".sqlite", ".sqlite3")):
            p = os.path.join(input_dir, f)
            if os.path.exists(p):
                t = load_sqlite(p)
                if t:
                    t["file"] = f
                    return t, None
    # 兜底：目录里任何 csv
    for f in sorted(os.listdir(input_dir)):
        if f.lower().endswith(".csv"):
            t = load_csv(os.path.join(input_dir, f), hint)
            if t:
                t["file"] = f
                return t, None
    return None, "no_data_table"


def parse_columns(table):
    """把原始字符串列解析为 (dtype, values)。返回列对象列表。"""
    cols = []
    for j, name in enumerate(table["names"]):
        raw = [r[j] if j < len(r) else "" for r in table["rows"]]
        nmiss = sum(1 for c in raw if c.strip().lower() in MISSING_TOKENS)
        numeric = all(is_number(c) for c in raw if c.strip().lower() not in MISSING_TOKENS)
        if numeric:
            vals = [None if c.strip().lower() in MISSING_TOKENS else float(c) for c in raw]
            dtype = "num"
        else:
            vals = [None if c.strip().lower() in MISSING_TOKENS else c.strip() for c in raw]
            dtype = "str"
        cols.append({"name": name, "index": j, "dtype": dtype, "values": vals,
                     "raw": raw, "n_missing": nmiss})
    return cols

# ------------------------------------------------------------------ 清洗


def dedupe_rows(rows):
    seen, keep, ndup = set(), [], 0
    for r in rows:
        key = tuple(r)
        if key in seen:
            ndup += 1
            continue
        seen.add(key)
        keep.append(r)
    return keep, ndup


def iqr_outlier_flags(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 4:
        return 0
    q1, q3 = sc.quantile(xs, 0.25), sc.quantile(xs, 0.75)
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return sum(1 for v in xs if v < lo or v > hi)

# ------------------------------------------------------------------ 列识别


def word_in(text, token):
    return re.search(r"(?<![\w.])" + re.escape(str(token)) + r"(?![\w.])", text) is not None


def detect_groupings(cols, task_text, max_levels=10):
    out = []
    for c in cols:
        uniq = sorted({v for v in c["values"] if v is not None})
        nu = len(uniq)
        if nu < 2:
            continue
        if c["dtype"] == "str":
            low_card = nu <= max_levels
            intlike = False
            labels = [str(v) for v in uniq]
        else:
            intlike = all(float(v).is_integer() for v in uniq)
            low_card = intlike and nu <= max_levels
            labels = [("%d" % int(v)) if float(v).is_integer() else repr(v) for v in uniq]
        name_hit = word_in(task_text, c["name"])
        vhits = 0
        if nu <= 30:  # 水平命中只对低基数列有意义（连续列的值撞词不计）
            for lab in labels:
                if word_in(task_text, lab):
                    vhits += 1
                elif "-" in lab and word_in(task_text, lab.rsplit("-", 1)[-1]):
                    vhits += 1  # 如 Iris-setosa ↔ setosa
        score = 3 * name_hit + 2 * (vhits >= 2) + 1 * (c["dtype"] == "str" and nu <= 10) \
            + 1 * (intlike and nu <= 20)
        # 连续浮点列（非整数取值或基数 >30）永远不自动当分组变量
        qualifies = ((c["dtype"] == "str" and 2 <= nu <= 10) or
                     (c["dtype"] == "num" and intlike and 2 <= nu <= 10) or
                     (score >= 5 and nu <= 30))
        if qualifies:
            out.append({"col": c, "labels": labels, "values": uniq, "score": score,
                        "name_hit": name_hit, "value_hits": vhits})
    out.sort(key=lambda g: (-g["score"], len(g["labels"])))
    return out


def detect_focus(grouping, task_text):
    """识别 task.md 点名的两组聚焦比较，如 “28 天组与 90 天组”。"""
    labels = grouping["labels"]
    hits = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*天?\s*组\s*与\s*(\d+(?:\.\d+)?)\s*天?\s*组",
                         task_text):
        a, b = m.group(1), m.group(2)
        la = [l for l in labels if is_number(l) and abs(float(l) - float(a)) < 1e-12]
        lb = [l for l in labels if is_number(l) and abs(float(l) - float(b)) < 1e-12]
        if la and lb and la[0] != lb[0]:
            hits.append((la[0], lb[0]))
    if not hits:
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                pa = re.escape(a) + r"[^\n。；]{0,12}与[^\n。；]{0,12}" + re.escape(b)
                pb = re.escape(b) + r"[^\n。；]{0,12}与[^\n。；]{0,12}" + re.escape(a)
                if re.search(pa, task_text) or re.search(pb, task_text):
                    hits.append((a, b))
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None


def detect_outcomes(cols, groupings, task_text):
    gidx = {g["col"]["index"] for g in groupings}
    nums = [c for c in cols if c["dtype"] == "num" and c["index"] not in gidx]
    named = [c for c in nums if word_in(task_text, c["name"])]
    if 0 < len(named) < len(nums):
        return named
    return nums


def parse_units(task_text, cols):
    units = {}
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*[（(]\s*([^（）()]+?)\s*[)）]", task_text):
        units[m.group(1)] = m.group(2)
    gm = re.search(r"单位\s*[:：]?\s*([A-Za-zμ°%/³³\w.]+)", task_text)
    global_unit = gm.group(1) if gm else None
    out = {}
    for c in cols:
        if c["name"] in units:
            out[c["name"]] = units[c["name"]]
        elif global_unit:
            out[c["name"]] = global_unit
    return out

# ------------------------------------------------------------------ 决策链核心


def group_values(col_vals, group_vals, level):
    return [v for v, g in zip(col_vals, group_vals)
            if v is not None and g is not None and
            (str(g) == level or (is_number(str(g)) and is_number(level)
                                 and abs(float(g) - float(level)) < 1e-12))]


def values_hash(vals):
    return hashlib.sha256("\n".join(repr(v) for v in sorted(vals)).encode()).hexdigest()


def assess_group(vals, alpha):
    """单组正态性评估 → normality 记录（conclusion ∈ normal/non_normal/not_tested）。"""
    n = len(vals)
    if n < sc.MIN_N_NORMALITY:
        return {"test": "dagostino_k2", "statistic": None, "p": None,
                "conclusion": "not_tested",
                "note": "n=%d < %d，正态性检验功效不足，按非正态保守处理" % (n, sc.MIN_N_NORMALITY)}
    k2, p, status = sc.dagostino_k2(vals)
    if status == "zero_variance":
        return {"test": "dagostino_k2", "statistic": None, "p": None,
                "conclusion": "non_normal", "note": "组内方差为零，正态性无意义"}
    if status == "not_tested":
        return {"test": "dagostino_k2", "statistic": None, "p": None,
                "conclusion": "not_tested", "note": "K² 峰度变换不可用"}
    return {"test": "dagostino_k2", "statistic": k2, "p": p,
            "conclusion": "non_normal" if p < alpha else "normal", "note": ""}


def gate_and_test(level_vals, alpha):
    """检验选择门控 + 执行。level_vals: [(label, values)]（已排序）。
    返回决策链条目主体。"""
    labels = [l for l, _ in level_vals]
    k = len(level_vals)
    codes, group_recs = [], []
    for lab, vals in level_vals:
        rec = assess_group(vals, alpha)
        if rec["conclusion"] == "not_tested":
            codes.append("N_LT_8:%s n=%d" % (lab, len(vals)))
        elif rec["conclusion"] == "non_normal" and rec["p"] is not None:
            codes.append("NORMALITY_FAIL:%s p=%.4f" % (lab, rec["p"]))
        elif rec["conclusion"] == "non_normal":
            codes.append("ZERO_VAR:%s" % lab)
        group_recs.append({"label": lab, "n": len(vals),
                           "values_sha256": values_hash(vals), "normality": rec})
    all_normal = all(r["normality"]["conclusion"] == "normal" for r in group_recs)
    if all_normal:
        codes.append("NORMALITY_OK")
    # Levene
    W, df1, df2, lp = sc.levene_median([v for _, v in level_vals])
    if lp is None:
        levene = {"center": "median", "statistic": None, "df1": None, "df2": None,
                  "p": None, "conclusion": "not_tested"}
        var_homog = False
        codes.append("LEVENE_UNAVAILABLE")
    else:
        var_homog = lp >= alpha
        levene = {"center": "median", "statistic": W, "df1": df1, "df2": df2,
                  "p": lp, "conclusion": "homogeneous" if var_homog else "heterogeneous"}
        codes.append(("VAR_HOMOG" if var_homog else "VAR_INHOMOG") + " p=%.4f" % lp)
    # 决策树（与 references/decision-tree.md 逐条对应）
    rejected = []
    if k == 2:
        if all_normal and var_homog:
            chosen = "student_t"
            rejected = [{"test": "welch_t", "reason": "方差齐性成立，无需 Welch 自由度校正"},
                        {"test": "mannwhitney_u", "reason": "正态性与方差齐性均满足，参数检验功效更高"}]
        elif all_normal:
            chosen = "welch_t"
            rejected = [{"test": "student_t", "reason": "方差不齐（Levene p<alpha），合并方差不适用"},
                        {"test": "mannwhitney_u", "reason": "正态性满足，参数检验优先"}]
        else:
            chosen = "mannwhitney_u"
            rejected = [{"test": "student_t", "reason": "正态性不满足或 n<%d" % sc.MIN_N_NORMALITY},
                        {"test": "welch_t", "reason": "正态性不满足，Welch 仅校正方差不能校正偏态"}]
    else:
        if all_normal and var_homog:
            chosen = "anova"
            rejected = [{"test": "welch_anova", "reason": "方差齐性成立"},
                        {"test": "kruskal_wallis", "reason": "全部组正态且方差齐，参数检验功效更高"}]
        elif all_normal:
            chosen = "welch_anova"
            rejected = [{"test": "anova", "reason": "方差不齐（Levene p<alpha）"},
                        {"test": "kruskal_wallis", "reason": "正态性满足，参数路线优先"}]
        else:
            chosen = "kruskal_wallis"
            rejected = [{"test": "anova", "reason": "存在非正态组或 n<%d" % sc.MIN_N_NORMALITY},
                        {"test": "welch_anova", "reason": "正态性不满足"}]
    codes.append("SELECT " + chosen)
    values = [v for _, v in level_vals]
    # 两组方向约定：统计量与效应量均为 排序后第二组 − 第一组
    if chosen == "student_t":
        res = sc.t_student(values[1], values[0])
    elif chosen == "welch_t":
        res = sc.t_welch(values[1], values[0])
    elif chosen == "mannwhitney_u":
        res = sc.mannwhitney(values[1], values[0])
    elif chosen == "anova":
        res = sc.anova_classic(values)
    elif chosen == "welch_anova":
        res = sc.anova_welch(values)
    else:
        res = sc.kruskal(values)
    df = res.get("df")
    if not isinstance(df, list):
        df = [df]
    test_result = {"statistic_name": STAT_NAMES[chosen], "statistic": res.get("statistic"),
                   "df": df, "p": res.get("p"), "alpha": alpha,
                   "significant": (res.get("p") is not None and res["p"] < alpha)}
    return {"design": "two_group" if k == 2 else "k_group", "group_levels": labels,
            "groups": group_recs, "levene": levene,
            "assumptions": {"all_normal": all_normal, "var_homogeneous": var_homog,
                            "min_n": min(len(v) for _, v in level_vals)},
            "candidates": (["student_t", "welch_t", "mannwhitney_u"] if k == 2
                           else ["anova", "welch_anova", "kruskal_wallis"]),
            "chosen_test": chosen, "reason_codes": codes,
            "rejected_candidates": rejected, "test_result": test_result}


def run_posthoc(chosen, level_vals, alpha):
    """两两事后比较，与主检验同路线，Holm 校正（族 = 该结局的全部两两对）。"""
    pairs = []
    for i in range(len(level_vals)):
        for j in range(i + 1, len(level_vals)):
            pairs.append((i, j))
    raw = []
    for i, j in pairs:
        xi, xj = level_vals[i][1], level_vals[j][1]
        if chosen == "anova":
            r = sc.t_student(xi, xj)
            tname = "student_t"
        elif chosen == "welch_anova":
            r = sc.t_welch(xi, xj)
            tname = "welch_t"
        else:
            r = sc.mannwhitney(xi, xj)
            tname = "mannwhitney_u"
        raw.append({"pair": [level_vals[i][0], level_vals[j][0]], "test": tname,
                    "statistic": r.get("statistic"), "p_raw": r.get("p"),
                    "mean_diff": sc.mean(xj) - sc.mean(xi)})
    pvals = [r["p_raw"] if r["p_raw"] is not None else 1.0 for r in raw]
    adj = sc.holm(pvals)
    for r, pa in zip(raw, adj):
        r["p_holm"] = pa
        r["significant"] = pa is not None and pa < alpha
    return raw


def effect_and_ci(design, chosen, level_vals, alpha):
    eff, ci = {}, {}
    values = [v for _, v in level_vals]
    if design == "two_group":
        x, y = values[1], values[0]   # 方向：排序后第二组 − 第一组
        g = sc.hedges_g(x, y)
        mw = sc.mannwhitney(x, y)
        eff["hedges_g"] = {"value": g, "direction": "mean(%s) - mean(%s)" %
                           (level_vals[1][0], level_vals[0][0]),
                           "correction": "exact J via lgamma"}
        eff["rank_biserial_r"] = {"value": sc.rank_biserial_from_u(mw["U1"], len(x), len(y)),
                                  "direction": "正值表示 %s 组取值倾向更大" % level_vals[1][0]}
        if g is not None:
            lo, hi, m = sc.bootstrap_hedges_g(x, y, alpha=alpha)
            ci["hedges_g_bootstrap"] = {"point": g, "lo": lo, "hi": hi, "B": m,
                                        "seed": sc.BOOT_SEED, "method": "percentile",
                                        "level": 1 - alpha}
        if chosen in ("student_t", "welch_t"):
            d, lo, hi, df = sc.welch_mean_diff_ci(x, y, alpha=alpha)
            ci["mean_diff_welch"] = {"point": d, "lo": lo, "hi": hi, "df": df,
                                     "level": 1 - alpha}
        else:
            est, lo, hi = sc.hodges_lehmann(x, y, alpha=alpha)
            ci["median_diff_hodges_lehmann"] = {"point": est, "lo": lo, "hi": hi,
                                                "level": 1 - alpha,
                                                "note": "两两差中位数，大样本分位区间"}
    else:
        if chosen in ("anova", "welch_anova"):
            e2, o2 = sc.eta_omega(values)
            eff["eta_squared"] = e2
            eff["omega_squared"] = o2
            if chosen == "welch_anova":
                eff["note"] = "η²/ω² 基于经典 SS 口径（Welch F' 无对应 SS 分解）"
        else:
            N = sum(len(v) for v in values)
            eff["epsilon_squared"] = sc.epsilon_squared_kw(
                None, N, len(values))  # 由调用方回填 H
    return eff, ci

# ------------------------------------------------------------------ 报告工具


def fmt_p(p):
    if p is None:
        return "NA"
    return "<0.0001" if p < 0.0001 else "%.4f" % p


def fmt(x, nd=4):
    if x is None:
        return "NA"
    if isinstance(x, float):
        return ("%.*f" % (nd, x)).rstrip("0").rstrip(".") if abs(x) < 1e6 else "%.4g" % x
    return str(x)

# ------------------------------------------------------------------ 主流程


def run(input_dir, work_dir, output_dir, overrides=None):
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    overrides = overrides or {}
    exceptions, decisions_log = [], []
    t0 = datetime.datetime.now(datetime.timezone.utc)

    case_path = os.path.join(input_dir, "case.json")
    task_path = os.path.join(input_dir, "task.md")
    if not os.path.exists(case_path):
        raise SystemExit("缺少 /input/case.json")
    case = json.load(open(case_path, encoding="utf-8"))
    task_text = open(task_path, encoding="utf-8").read() if os.path.exists(task_path) else ""
    constraints = case.get("constraints", {}) or {}
    alpha = float(overrides.get("alpha", constraints.get("alpha", 0.05)))

    table, err = load_table(input_dir, case)
    sources = {}
    for f in case.get("data_files") or []:
        p = os.path.join(input_dir, f)
        if os.path.exists(p):
            sources[f] = sha256_file(p)
    if table is None:
        res = skeleton_result(case, alpha, t0, sources)
        res["status"] = "failed"
        res["exceptions"].append({"type": "no_data_table",
                                  "detail": "未找到可用数据表（CSV/SQLite）"})
        write_outputs(output_dir, work_dir, res, None, [], [], None)
        return res

    # ---- 清洗
    cleaning = {"rules": [], "missing": {}, "duplicates": {}, "outliers": {}}
    dup_policy = str(constraints.get("duplicate_policy", "")).lower()
    n_raw = len(table["rows"])
    kept, ndup = dedupe_rows(table["rows"])
    if "dedupe" in dup_policy:
        table["rows"] = kept
        cleaning["duplicates"] = {"policy": "dedupe_exact_keep_first",
                                  "removed_rows": ndup, "n_before": n_raw,
                                  "n_after": len(kept)}
        cleaning["rules"].append("完全重复行：constraints.duplicate_policy 要求，"
                                 "去重保留首行，移除 %d 行" % ndup)
    else:
        cleaning["duplicates"] = {"policy": "report_only_no_removal",
                                  "duplicate_rows_found": ndup,
                                  "note": "未声明 duplicate_policy：低精度/圆整测量下完全重复可能为"
                                          "真实重复观测，默认只报告不删除（防止 n 偏倚）"}
        cleaning["rules"].append("完全重复行：发现 %d 行，按默认口径仅报告不删除" % ndup)
    cols = parse_columns(table)
    for c in cols:
        cleaning["missing"][c["name"]] = {
            "n_missing": c["n_missing"],
            "policy": "report_and_exclude（按变量有效 n，不零填、不插补）"}
        if c["dtype"] == "num":
            n_out = iqr_outlier_flags(c["values"])
            cleaning["outliers"][c["name"]] = {"n_flagged_1.5iqr": n_out,
                                               "policy": "只标记不删除"}
    cleaning["rules"].append("缺失 token：'' / NA / N/A / NaN / null / - / nan，按变量排除")
    cleaning["rules"].append("异常值：1.5×IQR 栅栏只标记不删除")

    units = parse_units(task_text, cols)

    # ---- 分组与结局识别（可被 decide 覆盖）
    groupings = detect_groupings(cols, task_text)
    if overrides.get("group"):
        gcols = [c for c in cols if c["name"] == overrides["group"]]
        if gcols:
            c = gcols[0]
            uniq = sorted({v for v in c["values"] if v is not None})
            labels = [("%d" % int(v)) if isinstance(v, float) and v.is_integer()
                      else str(v) for v in uniq]
            groupings = [{"col": c, "labels": labels, "values": uniq, "score": 99,
                          "name_hit": True, "value_hits": 0}]
            decisions_log.append({"key": "group", "value": overrides["group"],
                                  "reason": "decide 覆盖"})
    if overrides.get("drop_grouping"):
        groupings = [g for g in groupings if g["col"]["name"] != overrides["drop_grouping"]]
    if not groupings:
        res = skeleton_result(case, alpha, t0, sources)
        res["status"] = "partial"
        res["cleaning"] = cleaning
        res["exceptions"].append({"type": "no_grouping_column",
                                  "detail": "未识别出低基数分组列；请用 decide --key group 指定"})
        write_outputs(output_dir, work_dir, res, table, cols, [], None)
        return res

    outcomes = detect_outcomes(cols, groupings, task_text)
    if overrides.get("outcomes"):
        names = set(overrides["outcomes"])
        outcomes = [c for c in cols if c["name"] in names]
        decisions_log.append({"key": "outcomes", "value": sorted(names),
                              "reason": "decide 覆盖"})
    if not outcomes:
        exceptions.append({"type": "no_outcome_column", "detail": "无数值结局列"})

    # ---- 分析计划
    plans = []  # (grouping, outcome, levels_subset, role)
    for g in groupings:
        focus = None
        if overrides.get("focus"):
            focus = tuple(str(v) for v in overrides["focus"])
        elif len(g["labels"]) > 2:
            focus = detect_focus(g, task_text)
        for oc in outcomes:
            if focus:
                plans.append((g, oc, list(focus), "focused_two_group"))
                if len(g["labels"]) >= 3:
                    plans.append((g, oc, g["labels"], "omnibus_k_group"))
            elif len(g["labels"]) == 2:
                plans.append((g, oc, g["labels"], "two_group"))
            else:
                plans.append((g, oc, g["labels"], "k_group"))
    if overrides.get("group") or overrides.get("focus"):
        decisions_log.append({"key": "focus", "value": overrides.get("focus"),
                              "reason": "decide 覆盖" if overrides.get("focus") else "auto"})

    # ---- 执行分析
    decision_log, descriptive, ht, eff_all, ci_all = [], {}, {}, {}, {}
    panels = []
    for idx, (g, oc, levels, role) in enumerate(plans, 1):
        aid = "A%d" % idx
        level_vals = [(lab, group_values(oc["values"], g["col"]["values"], lab))
                      for lab in levels]
        level_vals = [(l, v) for l, v in level_vals if v]
        level_vals = sorted(level_vals,
                            key=lambda lv: (0, float(lv[0])) if is_number(lv[0]) else (1, lv[0]))
        if len(level_vals) < 2:
            exceptions.append({"type": "insufficient_groups",
                               "detail": "%s @ %s 有效组 < 2" % (oc["name"], g["col"]["name"])})
            continue
        entry = gate_and_test(level_vals, alpha)
        entry["analysis_id"] = aid
        entry["role"] = role
        entry["data"] = {"file": table["file"], "source_type": table["source_type"],
                         "group_column": {"name": g["col"]["name"], "index": g["col"]["index"]},
                         "outcome_column": {"name": oc["name"], "index": oc["index"]},
                         "levels": [l for l, _ in level_vals],
                         "unit": units.get(oc["name"])}
        # 事后比较
        if entry["design"] == "k_group":
            if len(level_vals) <= POSTHOC_MAX_K:
                entry["posthoc"] = run_posthoc(entry["chosen_test"], level_vals, alpha)
                entry["holm"] = {"family": "outcome 内全部两两比较",
                                 "m": len(entry["posthoc"]),
                                 "raw": [r["p_raw"] for r in entry["posthoc"]],
                                 "adjusted": [r["p_holm"] for r in entry["posthoc"]]}
            else:
                entry["posthoc"] = []
                entry["holm"] = {"family": None, "m": 0,
                                 "note": "组数 %d > %d，不做两两事后比较" %
                                         (len(level_vals), POSTHOC_MAX_K)}
                exceptions.append({"type": "posthoc_skipped", "detail": entry["holm"]["note"]})
        else:
            entry["posthoc"] = []
        eff, ci = effect_and_ci(entry["design"], entry["chosen_test"], level_vals, alpha)
        if entry["chosen_test"] == "kruskal_wallis":
            N = sum(len(v) for _, v in level_vals)
            eff["epsilon_squared"] = sc.epsilon_squared_kw(
                entry["test_result"]["statistic"], N, len(level_vals))
        entry["effect_size"] = eff
        entry["confidence_interval"] = ci
        decision_log.append(entry)

        descriptive[aid] = {
            "outcome": oc["name"], "unit": units.get(oc["name"]),
            "group_var": g["col"]["name"],
            "overall": sc.describe([v for _, v in level_vals for v in v]),
            "by_group": {l: sc.describe(v) for l, v in level_vals}}
        tr = entry["test_result"]
        ht[aid] = {"outcome": oc["name"], "group_var": g["col"]["name"], "role": role,
                   "design": entry["design"], "chosen_test": entry["chosen_test"],
                   "method": TEST_NAMES[entry["chosen_test"]],
                   "reason_codes": entry["reason_codes"],
                   "statistic_name": tr["statistic_name"], "statistic": tr["statistic"],
                   "df": tr["df"], "p": tr["p"], "alpha": tr["alpha"],
                   "significant": tr["significant"],
                   "posthoc": entry["posthoc"]}
        if entry["design"] == "k_group" and entry["chosen_test"] != "anova":
            bench = sc.anova_classic([v for _, v in level_vals])
            ht[aid]["classical_anova_benchmark"] = {
                "statistic": bench["statistic"], "df": bench["df"], "p": bench["p"],
                "note": "教学参考基准（非门控选择；门控选择见 chosen_test）"}
        eff_all[aid] = eff
        ci_all[aid] = ci
        panels.append({"title": "%s @ %s（%s）" % (oc["name"], g["col"]["name"], role),
                       "unit": units.get(oc["name"], ""),
                       "groups": [{"label": l, "stats": descriptive[aid]["by_group"][l]}
                                  for l, _ in level_vals]})

    # ---- 汇总 result.json
    res = skeleton_result(case, alpha, t0, sources)
    res["status"] = "ok" if decision_log else "partial"
    res["cleaning"] = cleaning
    res["descriptive"] = descriptive
    res["hypothesis_test"] = {"alpha": alpha, "multiplicity": "Holm（族=结局内两两比较）",
                              "analyses": ht}
    res["effect_size"] = eff_all
    res["confidence_interval"] = ci_all
    res["decision_log"] = decision_log
    res["exceptions"] = exceptions
    res["decisions"] = decisions_log + [
        {"key": "groupings_detected",
         "value": [{"group": g["col"]["name"], "levels": g["labels"], "score": g["score"]}
                   for g in groupings], "reason": "auto"},
        {"key": "outcomes_detected", "value": [c["name"] for c in outcomes], "reason": "auto"},
        {"key": "alpha", "value": alpha, "reason": "case.json constraints 或默认 0.05"}]
    res["uncertainty"] = build_uncertainty(decision_log)
    res["limitations"] = build_limitations(decision_log, plans, groupings, cleaning)
    res["interpretation"] = build_interpretation(decision_log, alpha, units)

    write_outputs(output_dir, work_dir, res, table, cols, decision_log, panels)
    return res


def skeleton_result(case, alpha, t0, sources):
    return {
        "case_id": case.get("case_id"),
        "status": "failed",
        "alpha": alpha,
        "cleaning": {}, "descriptive": {}, "hypothesis_test": {},
        "effect_size": {}, "confidence_interval": {},
        "interpretation": "", "limitations": [],
        "decision_log": [],
        "sources": {"input_sha256": sources},
        "reproducibility": {"bootstrap_seed": sc.BOOT_SEED, "bootstrap_B": sc.BOOT_B,
                            "python": platform.python_version(),
                            "platform": platform.platform(),
                            "utc": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "stat_core": "statcore_b.py（纯标准库）"},
        "uncertainty": [], "exceptions": [], "decisions": [],
    }


def build_uncertainty(decision_log):
    u = []
    for e in decision_log:
        tr = e["test_result"]
        if tr["p"] is not None and 0.01 < tr["p"] < 0.10:
            u.append("%s：p=%s 接近 α，结论对抽样波动敏感" % (e["analysis_id"], fmt_p(tr["p"])))
        if e["assumptions"]["min_n"] < sc.MIN_N_NORMALITY:
            u.append("%s：存在 n<%d 的组，正态性无法检验，非参路线功效有限"
                     % (e["analysis_id"], sc.MIN_N_NORMALITY))
    if not u:
        u.append("主要结论不依赖临界 p 值；残余不确定性见 limitations")
    return u


def build_limitations(decision_log, plans, groupings, cleaning):
    lim = ["缺失值按变量有效 n 排除（report_and_exclude），若缺失非随机可能引入偏倚",
           "异常值仅以 1.5×IQR 标记未删除；秩方法与稳健效应对其不敏感，参数路线结论"
           "在存在标记异常值时应谨慎",
           "bootstrap CI 为百分位法（B=%d，seed=%d）；对小样本或强偏态可能欠覆盖"
           % (sc.BOOT_B, sc.BOOT_SEED),
           "CSV/SQLite 跨源一致性、单位口径审计不在本 bundle 范围（属数据真实性层）",
           "统计显著不等于实际意义；因果解释需实验设计支持，本分析仅作关联层面推断"]
    for g in groupings:
        focused = [p for p in plans if p[0] is g and p[3] == "focused_two_group"]
        if focused and len(g["labels"]) > 2:
            others = [l for l in g["labels"] if l not in focused[0][2]]
            lim.append("task.md 点名聚焦比较 %s；%s 的其余水平 %s 仅进入全组别 omnibus" %
                       (list(focused[0][2]), g["col"]["name"], others))
    if cleaning.get("duplicates", {}).get("policy") == "report_only_no_removal":
        lim.append("未声明 duplicate_policy，完全重复行仅报告未删除（见 cleaning.duplicates）")
    return lim


def build_interpretation(decision_log, alpha, units):
    paras = []
    for e in decision_log:
        tr = e["test_result"]
        unit = e["data"].get("unit") or ""
        u_s = ("（单位：%s）" % unit) if unit else ""
        oc = e["data"]["outcome_column"]["name"]
        gv = e["data"]["group_column"]["name"]
        sig = tr["significant"]
        head = ("【%s】%s 按 %s 比较%s：" % (e["analysis_id"], oc, gv, u_s))
        reason = "；".join(e["reason_codes"])
        main = ("假设门控结果（%s）→ 采用 %s：%s=%s，df=%s，p=%s。"
                % (reason, TEST_NAMES[e["chosen_test"]], tr["statistic_name"],
                   fmt(tr["statistic"]), fmt(tr["df"]), fmt_p(tr["p"])))
        if sig:
            concl = ("在 α=%g 水平下，组间差异具有统计学意义" % alpha)
        else:
            concl = ("在 α=%g 水平下，尚无足够证据表明组间存在差异" % alpha)
        eff_s = ""
        es = e.get("effect_size", {})
        if "hedges_g" in es and es["hedges_g"].get("value") is not None:
            g = abs(es["hedges_g"]["value"])
            mag = "小" if g < 0.5 else ("中" if g < 0.8 else "大")
            eff_s = "效应量 Hedges g=%s（%s 等效应）" % (fmt(es["hedges_g"]["value"]), mag)
        elif es.get("eta_squared") is not None:
            eff_s = "效应量 η²=%s，ω²=%s" % (fmt(es["eta_squared"]), fmt(es["omega_squared"]))
        elif es.get("epsilon_squared") is not None:
            eff_s = "效应量 ε²=%s" % fmt(es["epsilon_squared"])
        if eff_s:
            eff_s += "；统计显著性需结合实际效应大小判断其科学意义"
        ph = ""
        if e.get("posthoc"):
            sigpairs = ["%s vs %s" % tuple(r["pair"]) for r in e["posthoc"] if r["significant"]]
            ph = "事后两两比较（Holm 校正）显著对：%s。" % ("、".join(sigpairs) if sigpairs else "无")
        paras.append(head + main + concl + "。" + eff_s + ph +
                     " 本结论为统计关联层面证据，不构成因果证明。")
    return "\n\n".join(paras) if paras else "无可用分析。"

# ------------------------------------------------------------------ 输出


def write_outputs(output_dir, work_dir, res, table, cols, decision_log, panels):
    with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(render_report(res))
    with open(os.path.join(work_dir, "digest.md"), "w", encoding="utf-8") as f:
        f.write(render_digest(res))
    if panels:
        with open(os.path.join(output_dir, "fig_boxplots.svg"), "w", encoding="utf-8") as f:
            f.write(render_svg_boxplots(panels))


def render_digest(res):
    L = []
    L.append("# digest — 待确认裁决（≤5 项）与决策链摘要\n")
    dec = [d for d in res.get("decisions", []) if d["key"] == "groupings_detected"]
    L.append("## 待确认（如无误可全部接受，直接 finalize）")
    if dec:
        for g in dec[0]["value"]:
            L.append("1. 分组变量 `%s`（水平：%s）——是否识别正确？" %
                     (g["group"], ", ".join(map(str, g["levels"]))))
    oc_names = []
    for d in res.get("decisions", []):
        if d.get("key") == "outcomes_detected":
            oc_names = d.get("value", [])
    L.append("2. 结局变量：%s——是否应收窄/改选？（decide --key outcomes）" %
             (", ".join("`%s`" % a for a in oc_names) if oc_names else "见 result.decisions"))
    L.append("3. alpha = %s（constraints.alpha；改：decide --key alpha）" % res.get("alpha"))
    dup = res.get("cleaning", {}).get("duplicates", {})
    L.append("4. 重复行处理：%s" % dup.get("policy", "NA"))
    L.append("5. 决策链中的假设结论（下表）——是否有领域理由覆盖？\n")
    L.append("## 决策链摘要（全量见 result.json.decision_log）")
    L.append("| 分析 | 结局 | 设计 | 各组 n | 正态性 | Levene | 选择检验 | reason_codes |")
    L.append("|---|---|---|---|---|---|---|---|")
    for e in res.get("decision_log", []):
        ns = ",".join("%s:%d" % (g["label"], g["n"]) for g in e["groups"])
        norm = ",".join("%s:%s" % (g["label"], g["normality"]["conclusion"])
                        for g in e["groups"])
        lev = e["levene"]["conclusion"]
        L.append("| %s | %s | %s | %s | %s | %s | **%s** | %s |" % (
            e["analysis_id"], e["data"]["outcome_column"]["name"], e["design"],
            ns, norm, lev, e["chosen_test"], "; ".join(e["reason_codes"])))
    L.append("\n## 复核命令\n")
    L.append("```bash")
    L.append("python3 $SKILL_DIR/scripts/decision_audit.py --input-dir /input "
             "--result /app/output/result.json")
    L.append("```")
    return "\n".join(L) + "\n"


def render_report(res):
    L = ["# 统计分析报告\n"]
    L.append("- case_id：`%s`　状态：`%s`　α=%g" % (res.get("case_id"), res["status"],
                                                  res.get("alpha", 0.05)))
    L.append("- 复现：seed=%s, B=%s, python=%s, utc=%s" % (
        res["reproducibility"]["bootstrap_seed"], res["reproducibility"]["bootstrap_B"],
        res["reproducibility"]["python"], res["reproducibility"]["utc"]))
    L.append("\n## 1. 数据清洗\n")
    cl = res.get("cleaning", {})
    for r in cl.get("rules", []):
        L.append("- " + r)
    L.append("\n## 2. 描述统计\n")
    for aid, d in res.get("descriptive", {}).items():
        u = ("（%s）" % d["unit"]) if d.get("unit") else ""
        L.append("### %s：%s @ %s%s" % (aid, d["outcome"], d["group_var"], u))
        L.append("| 组 | n | 均值 | SD | 中位数 | Q1 | Q3 | min | max | 偏度 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for lab, s in d["by_group"].items():
            if s:
                L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                    lab, s["n"], fmt(s["mean"]), fmt(s["sd"]), fmt(s["median"]),
                    fmt(s["q1"]), fmt(s["q3"]), fmt(s["min"]), fmt(s["max"]),
                    fmt(s["skewness"])))
    L.append("\n## 3. 假设门控与检验决策链\n")
    for e in res.get("decision_log", []):
        tr = e["test_result"]
        L.append("### %s（%s）" % (e["analysis_id"], e["role"]))
        L.append("- 假设：%s" % "；".join(e["reason_codes"]))
        L.append("- 被否决候选：%s" % "；".join(
            "%s（%s）" % (r["test"], r["reason"]) for r in e["rejected_candidates"]))
        L.append("- **%s**：%s=%s，df=%s，p=%s → %s" % (
            TEST_NAMES[e["chosen_test"]], tr["statistic_name"], fmt(tr["statistic"]),
            fmt(tr["df"]), fmt_p(tr["p"]),
            "显著" if tr["significant"] else "不显著"))
        if e.get("posthoc"):
            L.append("- 事后两两（Holm）：" + "；".join(
                "%s~%s p_raw=%s p_holm=%s" % (r["pair"][0], r["pair"][1],
                                              fmt_p(r["p_raw"]), fmt_p(r["p_holm"]))
                for r in e["posthoc"]))
    L.append("\n## 4. 效应量与置信区间\n")
    for aid in res.get("effect_size", {}):
        L.append("- %s：effect=%s；CI=%s" % (
            aid, json.dumps(res["effect_size"][aid], ensure_ascii=False),
            json.dumps(res["confidence_interval"].get(aid, {}), ensure_ascii=False)))
    L.append("\n## 5. 结果解释\n")
    L.append(res.get("interpretation", ""))
    L.append("\n## 6. 局限\n")
    for l in res.get("limitations", []):
        L.append("- " + l)
    return "\n".join(L) + "\n"


def render_svg_boxplots(panels):
    W, PH, ML = 760, 120, 70
    H = 30 + PH * len(panels)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'font-family="monospace" font-size="11">' % (W, H),
           '<rect width="100%" height="100%" fill="white"/>']
    y0 = 24
    for p in panels:
        stats = [g["stats"] for g in p["groups"] if g["stats"]]
        if not stats:
            continue
        lo = min(s["min"] for s in stats)
        hi = max(s["max"] for s in stats)
        if hi <= lo:
            hi = lo + 1.0
        def X(v):
            return ML + (v - lo) / (hi - lo) * (W - ML - 30)
        out.append('<text x="10" y="%d" font-size="12">%s %s</text>'
                   % (y0 + 10, p["title"], ("(" + p["unit"] + ")") if p["unit"] else ""))
        n = len(p["groups"])
        for i, g in enumerate(p["groups"]):
            s = g["stats"]
            yy = y0 + 20 + (PH - 30) * (i + 0.5) / max(1, n)
            if not s:
                continue
            out.append('<text x="6" y="%d">%s</text>' % (yy + 4, g["label"][:10]))
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#888"/>'
                       % (X(s["min"]), yy, X(s["max"]), yy))
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="16" '
                       'fill="#9ecae1" stroke="#3182bd"/>'
                       % (X(s["q1"]), yy - 8, max(1.0, X(s["q3"]) - X(s["q1"]))))
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#08519c" '
                       'stroke-width="2"/>' % (X(s["median"]), yy - 8, X(s["median"]), yy + 8))
        out.append('<text x="%.1f" y="%d" font-size="9">%.3g</text>' % (X(lo) - 8, y0 + PH - 4, lo))
        out.append('<text x="%.1f" y="%d" font-size="9">%.3g</text>' % (X(hi) - 20, y0 + PH - 4, hi))
        y0 += PH
    out.append('<text x="10" y="%d" font-size="9" fill="#666">box=Q1-Q3, line=median, '
               'whiskers=min/max（仅示意，合成渲染，无数据删除）</text>' % (H - 6))
    out.append("</svg>")
    return "\n".join(out)

# ------------------------------------------------------------------ 子命令


def cmd_run(a):
    res = run(a.input_dir, a.work_dir, a.output_dir)
    print("status=%s analyses=%d -> %s" %
          (res["status"], len(res.get("decision_log", [])),
           os.path.join(a.output_dir, "result.json")))
    return 0 if res["status"] == "ok" else (1 if res["status"] == "failed" else 0)


def cmd_decide(a):
    os.makedirs(a.work_dir, exist_ok=True)
    path = os.path.join(a.work_dir, "decisions.json")
    items = []
    if os.path.exists(path):
        items = json.load(open(path, encoding="utf-8"))
    try:
        value = json.loads(a.value)
    except (ValueError, TypeError):
        value = a.value
    items.append({"key": a.key, "value": value, "reason": a.reason or "",
                  "utc": datetime.datetime.now(datetime.timezone.utc)
                  .strftime("%Y-%m-%dT%H:%M:%SZ")})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print("decision recorded: %s = %s（finalize 后生效）" % (a.key, a.value))
    return 0


def cmd_finalize(a):
    overrides = {}
    path = os.path.join(a.work_dir, "decisions.json")
    items = []
    if os.path.exists(path):
        items = json.load(open(path, encoding="utf-8"))
    for d in items:
        overrides[d["key"]] = d["value"]
    res = run(a.input_dir, a.work_dir, a.output_dir, overrides=overrides)
    res["decisions"] = items + res["decisions"]
    with open(os.path.join(a.output_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.output_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(render_report(res))
    with open(os.path.join(a.work_dir, "digest.md"), "w", encoding="utf-8") as f:
        f.write(render_digest(res))
    print("finalized with %d override(s); status=%s" % (len(items), res["status"]))
    return 0 if res["status"] != "failed" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="assumption-gated-inference 管线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("--input-dir", required=True)
        p.add_argument("--work-dir", required=True)
        p.add_argument("--output-dir", required=True)
    p = sub.add_parser("decide")
    p.add_argument("--work-dir", required=True)
    p.add_argument("--key", required=True,
                   choices=["group", "outcomes", "focus", "alpha", "drop_grouping"])
    p.add_argument("--value", required=True)
    p.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    return {"run": cmd_run, "decide": cmd_decide, "finalize": cmd_finalize}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
