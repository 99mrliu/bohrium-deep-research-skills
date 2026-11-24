#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_bind.py — 结论-证据绑定机器核验（interpretation-tribunal 重心 2）。

用法：
  python3 claim_bind.py --report /app/output/report.md --result /app/output/result.json

核验项（任一违例 exit 1，全过 exit 0）：
  (a) DANGLING_EVIDENCE    结果解释章节的结论句缺少 [ev:ID] 标签，或标签 ID
                           在 result.json.claims 中不可解析；
  (b) DIRECTION_MISMATCH   claim.direction 与存储的组间均值差符号不一致；
  (c) SIGNIFICANCE_MISMATCH claim.significant 与 p<alpha 不一致；
  (d) NUMBER_MISMATCH      句子引用的数值（p/效应量/CI 端点/均值差/中位数差）
                           与存储值在四舍五入容差外不一致；
  (e) SENTENCE_DRIFT       claims[].sentence 与报告中的句子不逐字一致。

「结论句」的判定：结果解释章节内包含「统计学意义 / 效应量 / 置信区间为 /
中位数差」之一的散文句。数值容差 = 0.51 × 10^(-展示小数位数)。
"""
import argparse
import json
import math
import os
import re
import sys

VERSION = "1.0.0"

EV_TAG = re.compile(r"\[ev:([A-Za-z0-9_\-]+)\]")
CONCLUSION_TRIGGER = re.compile(r"统计学意义|效应量|置信区间为|中位数差")
P_EQ = re.compile(r"p\s*=\s*([0-9]*\.?[0-9]+)")
P_LT = re.compile(r"p\s*<\s*(0\.0001)")
DIFF_PATTERN = re.compile(r"(?:均值差|中位数差)（[^）]*）为\s*(-?[0-9]*\.?[0-9]+)")
CI_PATTERN = re.compile(r"置信区间为\s*\[\s*(-?[0-9]*\.?[0-9]+)\s*[,，]\s*"
                        r"(-?[0-9]*\.?[0-9]+)\s*\]")
ES_PATTERNS = {
    "hedges_g": re.compile(r"Hedges g\s*=\s*(-?[0-9]*\.?[0-9]+)"),
    "cohens_d": re.compile(r"Cohen's d\s*=\s*(-?[0-9]*\.?[0-9]+)"),
    "omega_squared": re.compile(r"ω²\s*=\s*(-?[0-9]*\.?[0-9]+)"),
    "eta_squared": re.compile(r"η²\s*=\s*(-?[0-9]*\.?[0-9]+)"),
    "epsilon_squared": re.compile(r"ε²\s*=\s*(-?[0-9]*\.?[0-9]+)"),
    "hodges_lehmann": re.compile(
        r"中位数差（Hodges-Lehmann）为\s*(-?[0-9]*\.?[0-9]+)"),
}


def _tol(shown):
    """按展示小数位数给四舍五入容差。"""
    if "." in shown:
        d = len(shown.split(".")[1])
    else:
        d = 0
    return 0.51 * (10.0 ** (-d))


def _num_close(shown, stored):
    if stored is None or (isinstance(stored, float) and math.isnan(stored)):
        return True
    return abs(float(shown) - float(stored)) <= _tol(shown)


def _split_sentences(line):
    # 只按句末点号切分：结论句内部允许使用「；」连接子句；
    # 句末 [ev:ID] 标签与句子保持同一片段（标签位于点号之后时不切开）
    parts = re.split(r"(?<=[。！？])(?!\[ev:)", line)
    return [p.strip() for p in parts if p.strip()]


def _interpretation_sentences(text):
    """抽取「结果解释」章节的散文句（跳过表格行/代码围栏）。"""
    lines = text.splitlines()
    start = None
    for i, l in enumerate(lines):
        if re.match(r"^#{1,6}\s*.*结果解释", l):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^#{1,6}\s", lines[j]):
            end = j
            break
    sents = []
    in_fence = False
    for lineno in range(start, end):
        stripped = lines[lineno].strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or stripped.startswith("|"):
            continue
        for s in _split_sentences(lines[lineno]):
            sents.append((lineno + 1, s))
    return sents


def bind_check(report_path, result_path):
    """返回违例字符串列表（空 = 通过）。"""
    with open(report_path, encoding="utf-8") as f:
        report = f.read()
    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)
    claims = result.get("claims") or []
    by_id = {c.get("id"): c for c in claims}
    violations = []

    def vio(code, msg):
        violations.append("%s: %s" % (code, msg))

    sents = _interpretation_sentences(report)
    if sents is None:
        vio("DANGLING_EVIDENCE", "报告缺少「结果解释」章节")
        sents = []

    # (a) 结论句必须有可解析的 [ev:ID]
    for lineno, s in sents:
        tags = EV_TAG.findall(s)
        if not tags and CONCLUSION_TRIGGER.search(s):
            vio("DANGLING_EVIDENCE",
                "line %d 结论句缺少 [ev:ID] 标签：%s" % (lineno, s[:60]))
        for t in tags:
            if t not in by_id:
                vio("DANGLING_EVIDENCE",
                    "line %d 标签 [ev:%s] 在 result.json.claims 中不可解析"
                    % (lineno, t))
    # 全文范围：任何 [ev:] 标签都必须可解析
    for m in EV_TAG.finditer(report):
        if m.group(1) not in by_id:
            lineno = report[:m.start()].count("\n") + 1
            vio("DANGLING_EVIDENCE",
                "line %d 标签 [ev:%s] 不可解析" % (lineno, m.group(1)))

    tagged = {}
    for lineno, s in sents:
        for t in set(EV_TAG.findall(s)):
            tagged.setdefault(t, []).append((lineno, s))

    for c in claims:
        cid = c.get("id")
        stored = c.get("sentence") or ""

        # (e) SENTENCE_DRIFT
        if stored and stored not in report:
            vio("SENTENCE_DRIFT",
                "claim %s 的 sentence 与报告不逐字一致：%s…"
                % (cid, stored[:50]))

        # (c) SIGNIFICANCE_MISMATCH
        p_stored = c.get("p")
        alpha = c.get("alpha", 0.05)
        if p_stored is not None:
            implied = bool(p_stored < alpha)
            if implied != bool(c.get("significant")):
                vio("SIGNIFICANCE_MISMATCH",
                    "claim %s：significant=%s 但 p=%.6g, alpha=%.6g"
                    % (cid, c.get("significant"), p_stored, alpha))

        # (b) DIRECTION_MISMATCH
        direction = c.get("direction")
        ma, mb = c.get("mean_a"), c.get("mean_b")
        if bool(c.get("significant")):
            if direction not in ("increase", "decrease"):
                vio("DIRECTION_MISMATCH",
                    "claim %s：显著但 direction=%s" % (cid, direction))
            elif ma is not None and mb is not None:
                if direction == "increase" and not ma > mb:
                    vio("DIRECTION_MISMATCH",
                        "claim %s：direction=increase 但 mean_a(%.6g)<=mean_b(%.6g)"
                        % (cid, ma, mb))
                if direction == "decrease" and not ma < mb:
                    vio("DIRECTION_MISMATCH",
                        "claim %s：direction=decrease 但 mean_a(%.6g)>=mean_b(%.6g)"
                        % (cid, ma, mb))
        else:
            if direction != "no_difference":
                vio("DIRECTION_MISMATCH",
                    "claim %s：不显著但 direction=%s（应为 no_difference）"
                    % (cid, direction))

        # (d) NUMBER_MISMATCH：对该 claim 标签下的每个报告句核对数值
        for lineno, s in tagged.get(cid, []):
            for m in P_EQ.finditer(s):
                if not _num_close(m.group(1), p_stored):
                    vio("NUMBER_MISMATCH",
                        "line %d claim %s：句中 p=%s 与存储 p=%.6g 不一致"
                        % (lineno, cid, m.group(1), p_stored))
            if P_LT.search(s):
                if not (p_stored is not None and p_stored < 0.0001):
                    vio("NUMBER_MISMATCH",
                        "line %d claim %s：句中 p<0.0001 但存储 p=%.6g"
                        % (lineno, cid, p_stored))
            es = c.get("effect_size") or {}
            es_name = es.get("name")
            if es_name in ES_PATTERNS:
                for m in ES_PATTERNS[es_name].finditer(s):
                    if not _num_close(m.group(1), es.get("value")):
                        vio("NUMBER_MISMATCH",
                            "line %d claim %s：句中效应量=%s 与存储 %.6g 不一致"
                            % (lineno, cid, m.group(1), es.get("value")))
            if es.get("ci95"):
                for m in CI_PATTERN.finditer(s):
                    lo_s, hi_s = es["ci95"]
                    if not (_num_close(m.group(1), lo_s)
                            and _num_close(m.group(2), hi_s)):
                        vio("NUMBER_MISMATCH",
                            "line %d claim %s：句中 CI=[%s, %s] 与存储 "
                            "[%.6g, %.6g] 不一致"
                            % (lineno, cid, m.group(1), m.group(2), lo_s, hi_s))
            for m in DIFF_PATTERN.finditer(s):
                if not _num_close(m.group(1), c.get("diff")):
                    vio("NUMBER_MISMATCH",
                        "line %d claim %s：句中差值=%s 与存储 diff=%.6g 不一致"
                        % (lineno, cid, m.group(1), c.get("diff")))

    return violations


def main(argv=None):
    ap = argparse.ArgumentParser(description="结论-证据绑定核验")
    ap.add_argument("--report", default="/app/output/report.md")
    ap.add_argument("--result", default="/app/output/result.json")
    args = ap.parse_args(argv)
    for p in (args.report, args.result):
        if not os.path.exists(p):
            print("找不到文件: %s" % p, file=sys.stderr)
            return 2
    violations = bind_check(args.report, args.result)
    if violations:
        for v in violations:
            print("VIOLATION %s" % v)
        print("claim_bind: %d 项违例" % len(violations))
        return 1
    print("claim_bind: PASS（结论句与 claims 证据绑定一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
