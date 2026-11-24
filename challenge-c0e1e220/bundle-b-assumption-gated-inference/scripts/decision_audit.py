#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decision_audit — 对 pipeline_b 产出的 result.json 做独立重算审计

用法：
    python3 decision_audit.py --input-dir /input --result /app/output/result.json

审计器**不看 pipeline 的中间产物**，只凭 case.json + 原始数据文件 +
result.json.decision_log 中记录的可复核规格（列名/列序号/组标签/取值哈希），
用自己的数据加载与决策树代码独立重算：

  (a) 每组正态性结论与 Levene 结论  —— 结论翻转 → ASSUMPTION_MISMATCH
  (b) 记录的 chosen_test vs 决策树在当前假设下的应选 → TEST_MISMATCH
  (c) 主检验 statistic/df 重算，容差 1e-6          → STAT_MISMATCH
      主检验 p 重算，容差 1e-6                     → P_MISMATCH
      （每组取值 sha256 不一致也报 STAT_MISMATCH，说明数据重建失败）
  (d) bootstrap CI：端点 |Δ|≤0.05 且区间含点估计    → BOOT_CI_DRIFT
  (e) Holm 校正 p 公式重算 + 单调性                 → HOLM_MISMATCH
  (f) alpha 与 case.json constraints.alpha          → ALPHA_MISMATCH

任一违例：逐条打印 `VIOLATION <码> ...`，exit 1；全部通过打印 PASS，exit 0。
"""
import argparse
import csv
import hashlib
import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_b as sc

TOL_STAT = 1e-6      # 统计量/df 容差（× max(1,|stat|)）
TOL_P = 1e-6         # p 值绝对容差
TOL_BOOT = 0.05      # bootstrap CI 端点漂移容差
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "-"}


class Violation(Exception):
    pass


def is_number(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False

# ---------------------------------------------------------------- 独立数据加载
# 与 pipeline_b 不共享代码：本模块按 references/decision-tree.md 附录 A 的
# 公开口径自行实现（编码嗅探 → 分隔符嗅探 → 表头嗅探 → 可选去重 → 缺失排除）。


def load_raw_rows(path):
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("latin-1")
    if path.lower().endswith((".db", ".sqlite", ".sqlite3")):
        return None  # 走 sqlite 分支
    first = text.split("\n", 1)[0]
    delim = max([",", ";", "\t"], key=lambda d: first.count(d))
    rows = [[c.strip() for c in r] for r in csv.reader(text.splitlines(), delimiter=delim)]
    return [r for r in rows if any(c != "" for c in r)]


def load_table_for_audit(input_dir, fname):
    path = os.path.join(input_dir, fname)
    if fname.lower().endswith((".db", ".sqlite", ".sqlite3")):
        con = sqlite3.connect(path)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'")]
            t = tables[0]
            names = [d[1] for d in con.execute("PRAGMA table_info(%s)" % t)]
            rows = [[("" if v is None else str(v)) for v in r]
                    for r in con.execute("SELECT * FROM %s" % t)]
            return names, rows, True
        finally:
            con.close()
    rows = load_raw_rows(path)
    if rows is None or not rows:
        raise Violation("无法读取数据文件 %s" % fname)
    bad = sum(0 if is_number(c) else 1 for c in rows[0])
    has_header = len(rows) >= 2 and bad * 2 >= len(rows[0])
    if has_header:
        return rows[0], rows[1:], True
    return ["col_%d" % (i + 1) for i in range(len(rows[0]))], rows[0:], False


def apply_cleaning(rows, case):
    """审计侧清洗：与 pipeline 公开口径一致（见 references 附录 A）。"""
    pol = str((case.get("constraints") or {}).get("duplicate_policy", "")).lower()
    if "dedupe" in pol:
        seen, keep = set(), []
        for r in rows:
            k = tuple(r)
            if k not in seen:
                seen.add(k)
                keep.append(r)
        return keep
    return rows  # 默认只报告不删除


def rebuild_groups(input_dir, case, entry):
    """按 decision_log 规格从原始数据重建各组取值。"""
    fname = entry["data"]["file"]
    names, rows, _ = load_table_for_audit(input_dir, fname)
    rows = apply_cleaning(rows, case)
    gi = entry["data"]["group_column"]["index"]
    oi = entry["data"]["outcome_column"]["index"]
    out = {}
    for lab in entry["data"]["levels"]:
        vals = []
        for r in rows:
            if gi >= len(r) or oi >= len(r):
                continue
            g, o = r[gi].strip(), r[oi].strip()
            if g.lower() in MISSING_TOKENS or o.lower() in MISSING_TOKENS:
                continue
            match = (g == lab) or (is_number(g) and is_number(lab)
                                   and abs(float(g) - float(lab)) < 1e-12)
            if match and is_number(o):
                vals.append(float(o))
        out[lab] = vals
    return out


def vhash(vals):
    return hashlib.sha256("\n".join(repr(v) for v in sorted(vals)).encode()).hexdigest()

# ---------------------------------------------------------------- 独立决策树


def expected_test(all_normal, var_homog, k):
    """决策树的审计侧独立实现（与 references/decision-tree.md 表 1 对应）。"""
    if k == 2:
        if all_normal and var_homog:
            return "student_t"
        if all_normal:
            return "welch_t"
        return "mannwhitney_u"
    if all_normal and var_homog:
        return "anova"
    if all_normal:
        return "welch_anova"
    return "kruskal_wallis"


def rerun_test(chosen, level_vals):
    values = [v for _, v in level_vals]
    if chosen == "student_t":
        r = sc.t_student(values[1], values[0])
    elif chosen == "welch_t":
        r = sc.t_welch(values[1], values[0])
    elif chosen == "mannwhitney_u":
        r = sc.mannwhitney(values[1], values[0])
    elif chosen == "anova":
        r = sc.anova_classic(values)
    elif chosen == "welch_anova":
        r = sc.anova_welch(values)
    elif chosen == "kruskal_wallis":
        r = sc.kruskal(values)
    else:
        raise Violation("未知检验 %s" % chosen)
    df = r.get("df")
    if not isinstance(df, list):
        df = [df]
    return r.get("statistic"), df, r.get("p")


def expected_reason_prefixes(group_facts, levene_concl, all_normal):
    """由重算事实推导 reason_codes 前缀集合（审计侧）。"""
    pref = set()
    for f in group_facts:
        if f["conclusion"] == "not_tested":
            pref.add("N_LT_8")
        elif f["conclusion"] == "non_normal":
            pref.add("ZERO_VAR" if f["p"] is None else "NORMALITY_FAIL")
    if all_normal:
        pref.add("NORMALITY_OK")
    if levene_concl == "homogeneous":
        pref.add("VAR_HOMOG")
    elif levene_concl == "heterogeneous":
        pref.add("VAR_INHOMOG")
    pref.add("SELECT")
    return pref

# ---------------------------------------------------------------- 审计主流程


def close(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def audit_entry(input_dir, case, entry, alpha_case, viol):
    aid = entry.get("analysis_id", "?")
    tag = "analysis=%s" % aid
    # alpha
    if not close(entry.get("test_result", {}).get("alpha"), alpha_case, 1e-12):
        viol.append("ALPHA_MISMATCH %s recorded=%s case=%s"
                    % (tag, entry.get("test_result", {}).get("alpha"), alpha_case))
    # (0) 数据重建 + 取值哈希
    try:
        groups = rebuild_groups(input_dir, case, entry)
    except Violation as e:
        viol.append("STAT_MISMATCH %s data_rebuild_failed: %s" % (tag, e))
        return
    level_vals = []
    for g in entry.get("groups", []):
        lab = g["label"]
        vals = groups.get(lab, [])
        if len(vals) != g["n"]:
            viol.append("STAT_MISMATCH %s group=%s n recorded=%d rebuilt=%d"
                        % (tag, lab, g["n"], len(vals)))
        elif vhash(vals) != g.get("values_sha256"):
            viol.append("STAT_MISMATCH %s group=%s values_sha256 不一致（数据被改动？）"
                        % (tag, lab))
        level_vals.append((lab, vals))
    if len(level_vals) < 2:
        viol.append("STAT_MISMATCH %s 重建后有效组 < 2" % tag)
        return
    k = len(level_vals)
    # (a) 正态性
    group_facts = []
    for (lab, vals), g in zip(level_vals, entry["groups"]):
        n = len(vals)
        if n < sc.MIN_N_NORMALITY:
            concl, p2 = "not_tested", None
        else:
            k2, p2, status = sc.dagostino_k2(vals)
            if status == "zero_variance":
                concl, p2 = "non_normal", None
            elif status == "not_tested":
                concl, p2 = "not_tested", None
            else:
                concl = "non_normal" if p2 < alpha_case else "normal"
        rec_concl = g["normality"]["conclusion"]
        rec_p = g["normality"].get("p")
        if rec_concl != concl:
            viol.append("ASSUMPTION_MISMATCH %s group=%s normality recorded=%s "
                        "recomputed=%s" % (tag, lab, rec_concl, concl))
        elif rec_p is not None and p2 is not None and not close(rec_p, p2, TOL_P):
            viol.append("ASSUMPTION_MISMATCH %s group=%s normality p recorded=%.10g "
                        "recomputed=%.10g" % (tag, lab, rec_p, p2))
        group_facts.append({"label": lab, "conclusion": concl, "p": p2})
    all_normal = all(f["conclusion"] == "normal" for f in group_facts)
    # Levene
    W, d1, d2, lp = sc.levene_median([v for _, v in level_vals])
    lev_concl = ("homogeneous" if (lp is not None and lp >= alpha_case)
                 else "heterogeneous" if lp is not None else "not_tested")
    rec_lev = entry.get("levene", {})
    if rec_lev.get("conclusion") != lev_concl:
        viol.append("ASSUMPTION_MISMATCH %s levene recorded=%s recomputed=%s"
                    % (tag, rec_lev.get("conclusion"), lev_concl))
    elif rec_lev.get("p") is not None and lp is not None \
            and not close(rec_lev["p"], lp, TOL_P):
        viol.append("ASSUMPTION_MISMATCH %s levene p recorded=%.10g recomputed=%.10g"
                    % (tag, rec_lev["p"], lp))
    var_homog = lev_concl == "homogeneous"
    # reason_codes 前缀集合
    rec_pref = {c.split(":")[0].split(" ")[0] for c in entry.get("reason_codes", [])}
    exp_pref = expected_reason_prefixes(group_facts, lev_concl, all_normal)
    if rec_pref != exp_pref:
        viol.append("ASSUMPTION_MISMATCH %s reason_codes prefixes recorded=%s expected=%s"
                    % (tag, sorted(rec_pref), sorted(exp_pref)))
    # assumptions 汇总字段
    asm = entry.get("assumptions", {})
    if asm.get("all_normal") != all_normal or asm.get("var_homogeneous") != var_homog:
        viol.append("ASSUMPTION_MISMATCH %s assumptions summary recorded=%s "
                    "recomputed all_normal=%s var_homogeneous=%s"
                    % (tag, asm, all_normal, var_homog))
    # (b) 决策树
    exp = expected_test(all_normal, var_homog, k)
    rec_test = entry.get("chosen_test")
    if rec_test != exp:
        viol.append("TEST_MISMATCH %s recorded=%s expected=%s (all_normal=%s "
                    "var_homog=%s k=%d)" % (tag, rec_test, exp, all_normal, var_homog, k))
        return  # 检验选错时统计量口径不同，后续重算无意义
    # (c) 主检验重算
    stat, df, p = rerun_test(rec_test, level_vals)
    tr = entry.get("test_result", {})
    if not close(tr.get("statistic"), stat, TOL_STAT):
        viol.append("STAT_MISMATCH %s statistic recorded=%s recomputed=%s"
                    % (tag, tr.get("statistic"), stat))
    rdf = tr.get("df") or []
    if len(rdf) != len(df) or any(not close(a, b, TOL_STAT) for a, b in zip(rdf, df)):
        viol.append("STAT_MISMATCH %s df recorded=%s recomputed=%s" % (tag, rdf, df))
    if not close(tr.get("p"), p, TOL_P):
        viol.append("P_MISMATCH %s p recorded=%s recomputed=%s" % (tag, tr.get("p"), p))
    # (d) bootstrap CI
    boot = (entry.get("confidence_interval") or {}).get("hedges_g_bootstrap")
    if boot:
        x, y = level_vals[1][1], level_vals[0][1]
        lo2, hi2, m = sc.bootstrap_hedges_g(x, y, B=sc.BOOT_B, seed=sc.BOOT_SEED,
                                            alpha=alpha_case)
        for key, vv in (("lo", lo2), ("hi", hi2)):
            rv = boot.get(key)
            if rv is None or vv is None or abs(rv - vv) > TOL_BOOT:
                viol.append("BOOT_CI_DRIFT %s hedges_g %s recorded=%s recomputed=%s"
                            % (tag, key, rv, vv))
        point = boot.get("point")
        blo, bhi = boot.get("lo"), boot.get("hi")
        if point is not None and blo is not None and bhi is not None \
                and not (blo - 1e-12 <= point <= bhi + 1e-12):
            viol.append("BOOT_CI_DRIFT %s 点估计 %.6g 不在记录区间 [%.6g, %.6g] 内"
                        % (tag, point, blo, bhi))
    # (e) Holm
    ph = entry.get("posthoc") or []
    if ph:
        raw = [r["p_raw"] for r in ph]
        exp_adj = sc.holm(raw)
        for r, ea in zip(ph, exp_adj):
            if not close(r.get("p_holm"), ea, 1e-9):
                viol.append("HOLM_MISMATCH %s pair=%s p_holm recorded=%s expected=%s"
                            % (tag, r.get("pair"), r.get("p_holm"), ea))
        order = sorted(range(len(raw)), key=lambda i: raw[i])
        seq = [ph[i].get("p_holm") for i in order]
        if any(seq[i + 1] < seq[i] - 1e-12 for i in range(len(seq) - 1)):
            viol.append("HOLM_MISMATCH %s 校正后 p 不满足随秩单调不减" % tag)
        hm = entry.get("holm") or {}
        if hm.get("m") not in (None, len(ph)):
            viol.append("HOLM_MISMATCH %s holm.m recorded=%s expected=%d"
                        % (tag, hm.get("m"), len(ph)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="decision_log 独立重算审计")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--result", required=True)
    a = ap.parse_args(argv)

    res = json.load(open(a.result, encoding="utf-8"))
    case_path = os.path.join(a.input_dir, "case.json")
    case = json.load(open(case_path, encoding="utf-8")) if os.path.exists(case_path) else {}
    alpha_case = float((case.get("constraints") or {}).get("alpha", 0.05))

    viol = []
    if not close(res.get("alpha"), alpha_case, 1e-12):
        viol.append("ALPHA_MISMATCH top-level recorded=%s case=%s"
                    % (res.get("alpha"), alpha_case))
    entries = res.get("decision_log") or []
    if not entries:
        print("FAIL: result.json 无 decision_log，无法审计")
        return 1
    for e in entries:
        try:
            audit_entry(a.input_dir, case, e, alpha_case, viol)
        except Exception as ex:  # 审计自身不应崩溃；计为违例
            viol.append("STAT_MISMATCH analysis=%s audit_exception: %r"
                        % (e.get("analysis_id", "?"), ex))
    if viol:
        print("DECISION AUDIT: FAIL (%d violation(s))" % len(viol))
        for v in viol:
            print("VIOLATION " + v)
        return 1
    print("DECISION AUDIT: PASS — %d 个分析条目全部通过独立重算" % len(entries))
    print("  校验项: alpha / 数据哈希 / 正态性结论 / Levene 结论 / reason_codes / "
          "chosen_test / statistic+df / p / bootstrap CI / Holm")
    print("  容差: stat,p ≤1e-6；bootstrap 端点 ≤0.05；holm ≤1e-9")
    return 0


if __name__ == "__main__":
    sys.exit(main())
