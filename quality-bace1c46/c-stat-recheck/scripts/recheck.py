#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recheck.py — 一致性重算引擎（全部脚本完成，规则见 rules/recheck_rules.md）。

输入：work-dir 下 numbers/<doc_id>.jsonl、pages/<doc_id>.jsonl、anchors/<doc_id>.json
产出：
  recheck/<doc_id>.jsonl         每行一个复核结论：
    {"id","doc_id","check_type","status","sides":[{"quote","page"}...],
     "computed","reported","tolerance","note"}
    status ∈ {pass, discrepancy, not_recomputable,
              reported, absent, not_applicable, unclear}
  semantic_queue/<doc_id>.jsonl  需要模型语义确认的配对（needs_semantic）

数值重算均为**近似**：t/F 经正则化不完全 β 函数（连分式实现）、χ² 经正则化
不完全 γ 函数（级数/连分式实现）、正态经 math.erf/erfc。精度声明见规则文档。
discrepancy 仅表示"报告内部不一致，需人工核对"，不代表论文错误。
"""
import argparse
import json
import math
import os
import re
import sys

# ============================================================ 数值近似

def _betacf(a, b, x):
    """不完全 β 函数的连分式部分（Numerical Recipes betacf 移植）。"""
    MAXIT, EPS, FPMIN = 300, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    """正则化不完全 β 函数 I_x(a,b)（近似，绝对误差一般 <1e-9）。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _gser_P(a, x):
    """正则化下不完全 γ P(a,x)，级数实现（x < a+1 时使用）。"""
    gln = math.lgamma(a)
    ap, s, delta = a, 1.0 / a, 1.0 / a
    for _ in range(300):
        ap += 1.0
        delta *= x / ap
        s += delta
        if abs(delta) < abs(s) * 3e-12:
            break
    return s * math.exp(-x + a * math.log(x) - gln)


def _gcf_Q(a, x):
    """正则化上不完全 γ Q(a,x)，连分式实现（x >= a+1 时使用）。"""
    gln = math.lgamma(a)
    FPMIN = 1e-300
    b, c, d = x + 1.0 - a, 1.0 / FPMIN, 1.0 / (x + 1.0 - a)
    h = d
    for i in range(1, 301):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + an / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-12:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def gamma_Q(a, x):
    if x < 0 or a <= 0:
        return None
    if x == 0.0:
        return 1.0
    if x < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _gser_P(a, x)))
    return max(0.0, min(1.0, _gcf_Q(a, x)))


def t_two_sided_p(t, df):
    """t 分布双侧 p（近似）。"""
    x = df / (df + t * t)
    return max(0.0, min(1.0, betai(df / 2.0, 0.5, x)))


def f_sf(f, d1, d2):
    """F 分布上尾概率（近似）。"""
    if f <= 0:
        return 1.0
    x = d2 / (d2 + d1 * f)
    return max(0.0, min(1.0, betai(d2 / 2.0, d1 / 2.0, x)))


def chi2_sf(x, k):
    """χ² 生存函数（近似；df ≤ 100 已验证够用，更大 df 同样稳定）。"""
    return gamma_Q(k / 2.0, x / 2.0)


def norm_two_sided_p(z):
    return math.erfc(abs(z) / math.sqrt(2.0))


# ============================================================ 通用工具

def load_jsonl(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def dec_tol(decimals, unit=1.0):
    """按报告精度的四舍五入容差带：±0.5 个末位单位。"""
    return 0.5 * (10.0 ** (-decimals)) * unit + 1e-9


class RowWriter:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.rows = []
        self.queue = []
        self._n = 0

    def add(self, check_type, status, sides, computed=None, reported=None,
            tolerance=None, note=""):
        self._n += 1
        row = {"id": "%s:%s:%d" % (self.doc_id, check_type.replace(":", "_"), self._n),
               "doc_id": self.doc_id, "check_type": check_type, "status": status,
               "sides": sides, "computed": computed, "reported": reported,
               "tolerance": tolerance, "note": note}
        self.rows.append(row)
        return row

    def enqueue(self, question, sides, context=None):
        self.queue.append({"doc_id": self.doc_id, "needs_semantic": True,
                           "question": question, "sides": sides,
                           "context": context or {}})


def side(rec):
    return {"quote": rec.get("sentence", ""), "page": rec.get("page")}


# ============================================================ 各检查项

def check_freq_percent(rw, records):
    """频数↔百分比：count/total 重算 vs 报告百分比（容差=±0.5 末位）。"""
    for rec in records:
        vf = rec["value_fields"]
        if vf["total"] <= 0:
            continue
        computed = 100.0 * vf["count"] / vf["total"]
        reported = vf["percent"]
        tol = dec_tol(vf["percent_decimals"])
        diff = abs(computed - reported)
        status = "pass" if diff <= tol else "discrepancy"
        note = ("重算 %d/%d = %.4f%% vs 报告 %s%%（容差 ±%.4g 个百分点）"
                % (vf["count"], vf["total"], computed, reported, tol))
        if status == "discrepancy":
            note += "；超出容差，属报告内部不一致，需人工核对（不代表论文错误）。"
        rw.add("freq_vs_percent", status,
               [side(rec), {"quote": rec["fragment"], "page": rec["page"]}],
               computed=round(computed, 4), reported=reported,
               tolerance=round(tol, 6), note=note)


def check_stratified_sum(rw, records):
    """分层求和：同句多个 n 的部分和 vs 总 n。"""
    by_sent = {}
    for rec in records:
        key = (rec["page"], rec["sentence"])
        by_sent.setdefault(key, []).append(rec)
    all_n = [r["value_fields"]["n"] for r in records]
    for (page, _sent), recs in by_sent.items():
        vals = [r["value_fields"]["n"] for r in recs]
        if len(vals) < 2:
            continue
        if len(vals) >= 3:
            total_rep = max(vals)
            part_sum = sum(v for v in vals if v is not total_rep) \
                if vals.count(total_rep) == 1 else sum(sorted(vals)[:-1])
            status = "pass" if part_sum == total_rep else "discrepancy"
            rw.add("stratified_sum", status, [side(r) for r in recs],
                   computed=part_sum, reported=total_rep, tolerance=0,
                   note=("同句分组 n 之和 %d vs 总 n=%d" % (part_sum, total_rep))
                        + ("" if status == "pass" else "；不一致，需人工核对。"))
        else:
            s = sum(vals)
            elsewhere = [r for r in records
                         if (r["page"], r["sentence"]) != (page, _sent)]
            exact = [r for r in elsewhere if r["value_fields"]["n"] == s]
            if exact:
                rw.add("stratified_sum", "pass",
                       [side(recs[0]), side(exact[0])],
                       computed=s, reported=s, tolerance=0,
                       note="分组 n 之和与他处总 n 一致。")
                continue
            near = [r for r in elsewhere
                    if 0.9 * s <= r["value_fields"]["n"] <= 1.1 * s]
            if near:
                row = rw.add("stratified_sum", "discrepancy",
                             [side(recs[0]), side(near[0])],
                             computed=s, reported=near[0]["value_fields"]["n"],
                             tolerance=0,
                             note="分组 n 之和与最接近的总 n 不一致；"
                                  "两处 n 是否同一总体需语义确认。")
                rw.enqueue("两处样本量是否指同一总体？分组之和 %d，他处报告 %d。"
                           % (s, near[0]["value_fields"]["n"]),
                           row["sides"], {"check_type": "stratified_sum"})
            else:
                rw.add("stratified_sum", "not_recomputable",
                       [side(recs[0])], computed=s, reported=None, tolerance=0,
                       note="文中未找到可比对的总 n。")


def check_abstract_vs_body(rw, records, pages, abstract_only):
    """摘要↔正文：同一指标词+数值指纹配对，跨区比对。"""
    if abstract_only or not pages:
        return
    full = []
    offset = 0
    for p in pages:
        full.append((p["page"], offset, offset + len(p["text"])))
        offset += len(p["text"]) + 1
    whole = "\n".join(p["text"] for p in pages)
    m_abs = re.search(r"(?im)^\s*abstract\b", whole)
    if not m_abs:
        return
    m_intro = re.search(r"(?im)^\s*introduction\b", whole[m_abs.end():])
    abs_end = m_abs.end() + (m_intro.start() if m_intro else 1200)
    abs_text = whole[m_abs.end():abs_end]

    def ctx_word(sentence, fragment):
        i = sentence.find(fragment)
        head = sentence[:i] if i >= 0 else sentence
        words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", head)
        return words[-1].lower() if words else None

    abs_recs, body_recs = [], []
    for rec in records:
        if rec["kind"] not in ("percent", "freq_percent"):
            continue
        in_abs = rec["sentence"] in abs_text or abs_text.find(
            (rec["sentence"] or "")[:60]) >= 0
        (abs_recs if in_abs else body_recs).append(rec)

    def val(rec):
        vf = rec["value_fields"]
        return vf.get("percent")

    paired = 0
    for a in abs_recs:
        wa = ctx_word(a["sentence"], a["fragment"])
        if not wa:
            continue
        for b in body_recs:
            if ctx_word(b["sentence"], b["fragment"]) != wa:
                continue
            va, vb = val(a), val(b)
            if va is None or vb is None:
                continue
            paired += 1
            if abs(va - vb) <= 0.05:
                rw.add("abstract_vs_body", "pass", [side(a), side(b)],
                       computed=vb, reported=va, tolerance=0.05,
                       note="摘要与正文同一指标（语境词 %s）数值一致。" % wa)
            else:
                row = rw.add("abstract_vs_body", "discrepancy",
                             [side(a), side(b)],
                             computed=vb, reported=va, tolerance=0.05,
                             note="摘要 %s%% vs 正文 %s%%（语境词 %s）；"
                                  "是否同一指标需语义确认。" % (va, vb, wa))
                rw.enqueue("摘要与正文中语境词 %r 附近的两个数值是否同一指标？"
                           % wa, row["sides"],
                           {"check_type": "abstract_vs_body"})
            break
        if paired >= 20:
            break


def _paired_p(rec, p_records):
    """为检验统计量找配对的 p：先同句，后同页 ±200 字符。"""
    same = [p for p in p_records if p["sentence"] == rec["sentence"]]
    if same:
        return same[0]
    cand = [p for p in p_records
            if p["page"] == rec["page"] and p["span"] and rec["span"]
            and abs(p["span"][0] - rec["span"][1]) <= 200]
    return cand[0] if cand else None


def check_p_recompute(rw, test_records, p_records):
    """p 值粗复核：检验量+df 齐全才重算，否则 not_recomputable。"""
    for rec in test_records:
        vf = rec["value_fields"]
        stat, val = vf["stat"], vf["value"]
        df = vf.get("df")
        if df is None:
            m = re.search(r"df\s*=\s*(\d+)", rec["sentence"], re.IGNORECASE)
            if m:
                df = [int(m.group(1))]
        if not df:
            rw.add("p_value_recompute", "not_recomputable", [side(rec)],
                   computed=None, reported=None, tolerance=None,
                   note="检验统计量 %s=%s 缺少自由度，不可重算。" % (stat, val))
            continue
        computed = None
        method = None
        if stat == "t" and len(df) >= 1:
            computed = t_two_sided_p(val, df[0]); method = "t 双侧（不完全β近似）"
        elif stat == "z":
            computed = norm_two_sided_p(val); method = "正态双侧（math.erfc）"
        elif stat == "chi2" and len(df) >= 1:
            computed = chi2_sf(val, df[0]); method = "χ² 上尾（不完全γ近似）"
        elif stat == "F" and len(df) >= 2:
            computed = f_sf(val, df[0], df[1]); method = "F 上尾（不完全β近似）"
        if computed is None:
            rw.add("p_value_recompute", "not_recomputable", [side(rec)],
                   computed=None, reported=None, tolerance=None,
                   note="统计量 %s 自由度形态不支持重算（df=%s）。" % (stat, df))
            continue
        p_rec = _paired_p(rec, p_records)
        if p_rec is None:
            rw.enqueue("检验统计量 %s=%s (df=%s) 附近未找到配对 p 值，"
                       "请确认其对应的显著性声明。" % (stat, val, df),
                       [side(rec)], {"check_type": "p_value_recompute",
                                     "computed_p": round(computed, 6)})
            continue
        pv = p_rec["value_fields"]
        comp, rep = pv["comparator"], pv["value"]
        tol = max(0.005, 0.2 * rep)
        if comp in ("<", "≤"):
            status = "pass" if computed < rep else (
                "discrepancy" if computed >= rep + 0.005 else "pass")
        elif comp in (">", "≥"):
            status = "pass" if computed > rep else (
                "discrepancy" if computed <= rep - 0.005 else "pass")
        else:
            status = "pass" if abs(computed - rep) <= tol else "discrepancy"
        note = ("近似重算 p≈%.6f（%s）vs 报告 p%s%s（容差 %.4g）"
                % (computed, method, comp, rep, tol))
        if status == "discrepancy":
            note += "；超出近似容差，需人工核对（重算为近似，边界情形谨慎解读）。"
        rw.add("p_value_recompute", status, [side(rec), side(p_rec)],
               computed=round(computed, 6), reported="p%s%s" % (comp, rep),
               tolerance=tol, note=note)


def check_effect_direction(rw, effect_records, ci_records):
    """效应方向：OR/HR/RR 点估计 vs CI、CI 是否跨 1、与显著性措辞是否矛盾。"""
    for rec in effect_records:
        vf = rec["value_fields"]
        ci = None
        for c in ci_records:
            if c["sentence"] == rec["sentence"] or (
                    c["page"] == rec["page"] and c["span"] and rec["span"]
                    and abs(c["span"][0] - rec["span"][1]) <= 250):
                ci = c
                break
        if ci is None:
            rw.add("effect_direction", "not_recomputable", [side(rec)],
                   computed=None, reported=vf["value"], tolerance=None,
                   note="%s=%s 附近未找到 95%% CI，方向不可核。" % (
                       vf["measure"], vf["value"]))
            continue
        lo, hi, est = ci["value_fields"]["lo"], ci["value_fields"]["hi"], vf["value"]
        sent = rec["sentence"]
        claim_sig = bool(re.search(r"significant", sent, re.IGNORECASE)) and not \
            re.search(r"(not|non[- ]?|no)\s+(statistically\s+)?significant",
                      sent, re.IGNORECASE)
        claim_null = bool(re.search(
            r"(not|non[- ]?|no)\s+(statistically\s+)?significant", sent, re.IGNORECASE))
        problems = []
        if not (lo <= est <= hi):
            problems.append("点估计 %s 不在 CI [%s, %s] 内" % (est, lo, hi))
        straddle = lo < 1.0 < hi
        if claim_sig and straddle:
            problems.append("CI [%s, %s] 跨 1 但同句声称 significant" % (lo, hi))
        if claim_null and not straddle:
            problems.append("CI [%s, %s] 不跨 1 但同句声称 not significant" % (lo, hi))
        status = "discrepancy" if problems else "pass"
        rw.add("effect_direction", status, [side(rec), side(ci)],
               computed={"lo": lo, "hi": hi}, reported=est, tolerance=None,
               note=("；".join(problems) if problems
                     else "%s=%s 与 CI [%s, %s] 方向一致，显著性措辞无矛盾。"
                          % (vf["measure"], est, lo, hi)))


# ---- 报告完整性缺口表（清单见 rules/completeness_checklist.md） ----

CHECKLIST = [
    ("sample_size_justification", "样本量依据/功效",
     re.compile(r"(sample size (calculation|was based|determination|estimation)"
                r"|power (calculation|analysis|of \d+)|\bpowered\b"
                r"|\d+\s*%\s*power)", re.IGNORECASE), "all"),
    ("primary_effect_with_precision", "主结局效应量与精度（效应量+CI）",
     None, "all"),  # 特殊：依赖 effect+ci 采集结果
    ("missing_data_handling", "缺失数据处理",
     re.compile(r"(missing (data|values)?|imputation|complete[- ]case"
                r"|intention[- ]to[- ]treat|\bITT\b|per[- ]protocol"
                r"|last observation carried forward|\bLOCF\b)",
                re.IGNORECASE), "all"),
    ("multiplicity", "多重性控制",
     re.compile(r"(Bonferroni|Holm|Hochberg|multiplicity"
                r"|multiple (comparisons|testing|endpoints)"
                r"|false discovery|\bFDR\b|adjust(?:ed|ment)? for (multiplicity|multiple))",
                re.IGNORECASE), "all"),
    ("adverse_events", "不良事件/安全性报告",
     re.compile(r"(adverse event|side effect|tolerab|safety (profile|population|analysis)"
                r"|\bharms?\b)", re.IGNORECASE), "trial"),
]

TRIAL_RE = re.compile(r"randomi[sz]ed|random allocation|placebo", re.IGNORECASE)


def check_completeness(rw, records, pages, abstract_only):
    whole = "\n".join(p["text"] for p in pages)
    doc_type = "trial" if TRIAL_RE.search(whole) else "other"
    limited_note = "（仅摘要文献，缺口判定为摘要口径，标 limited）" if abstract_only else ""
    for item, label, pat, scope in CHECKLIST:
        if scope == "trial" and doc_type != "trial":
            rw.add("completeness:" + item, "not_applicable", [],
                   note="%s：文献类型非试验类，不适用。" % label)
            continue
        if item == "primary_effect_with_precision":
            eff = [r for r in records if r["kind"] == "effect"]
            ci = [r for r in records if r["kind"] == "ci"]
            if eff and ci:
                rw.add("completeness:" + item, "reported",
                       [side(eff[0]), side(ci[0])],
                       note="%s：检出效应量与置信区间。%s" % (label, limited_note))
            else:
                rw.add("completeness:" + item, "absent", [],
                       note="%s：未检出效应量+CI 的组合报告（缺口，非过失）。%s"
                            % (label, limited_note))
            continue
        m = pat.search(whole) if pat else None
        if m:
            # 定位所在页与句
            pos = m.start()
            page_no, page_text = 1, pages[0]["text"] if pages else ""
            acc = 0
            for p in pages:
                if acc <= pos < acc + len(p["text"]) + 1:
                    page_no, page_text = p["page"], p["text"]
                    break
                acc += len(p["text"]) + 1
            s = max(0, page_text.rfind("\n", 0, min(pos, len(page_text))))
            e = page_text.find("\n", min(pos, len(page_text)))
            quote = page_text[s:e if e > 0 else len(page_text)].strip()
            rw.add("completeness:" + item, "reported",
                   [{"quote": quote, "page": page_no}],
                   note="%s：已检出。%s" % (label, limited_note))
        else:
            rw.add("completeness:" + item, "absent", [],
                   note="%s：全文未检出相关报告（缺口，非过失）。%s"
                        % (label, limited_note))


# ============================================================ 主流程

def process_doc(work_dir, doc_id, abstract_only):
    pages = load_jsonl(os.path.join(work_dir, "pages", doc_id + ".jsonl"))
    records = load_jsonl(os.path.join(work_dir, "numbers", doc_id + ".jsonl"))
    rw = RowWriter(doc_id)
    by_kind = {}
    for r in records:
        by_kind.setdefault(r["kind"], []).append(r)

    check_freq_percent(rw, by_kind.get("freq_percent", []))
    check_stratified_sum(rw, by_kind.get("sample_size", []))
    check_abstract_vs_body(rw, records, pages, abstract_only)
    check_p_recompute(rw, by_kind.get("test_stat", []),
                      by_kind.get("p_value", []))
    check_effect_direction(rw, by_kind.get("effect", []),
                           by_kind.get("ci", []))
    check_completeness(rw, records, pages, abstract_only)

    out_dir = os.path.join(work_dir, "recheck")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, doc_id + ".jsonl"), "w",
              encoding="utf-8") as f:
        for row in rw.rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if rw.queue:
        qd = os.path.join(work_dir, "semantic_queue")
        os.makedirs(qd, exist_ok=True)
        with open(os.path.join(qd, doc_id + ".jsonl"), "w",
                  encoding="utf-8") as f:
            for q in rw.queue:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")
    return len(rw.rows), len(rw.queue)


def main():
    ap = argparse.ArgumentParser(description="一致性重算引擎")
    ap.add_argument("--work-dir", default="/app/work")
    args = ap.parse_args()
    docs = load_jsonl(os.path.join(args.work_dir, "docs.jsonl"))
    total_rows, total_q = 0, 0
    for d in docs:
        if d.get("status") != "ok":
            continue
        nr, nq = process_doc(args.work_dir, d["doc_id"],
                             bool(d.get("abstract_only")))
        total_rows += nr
        total_q += nq
    print(json.dumps({"recheck_rows": total_rows, "semantic_queue": total_q},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
