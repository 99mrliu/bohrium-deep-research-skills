#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_check — G0..G7 阶段门（重心脚本 2）。任一 FAIL 即 exit 1 并打印门号与原因。

  G0 输入已登记且 sha256 可复算一致（含阶段产物/交付物哈希防篡改）
  G1 清洗闭合律 rows_raw == rows_kept + rows_dropped
  G2 契约骨架在推断前已写出（seq 顺序 + 骨架字段覆盖 output_contract）
  G3 result.json 关键统计量（每结局每组 n/均值、主 p）可在阶段产物中找到一致来源
  G4 uncertainty / limitations 非空
  G5 status 枚举合法；partial 时 exceptions 非空
  G6 report.md 中出现的 p 值/效应量数字与 result.json 一致（REPORT_NUMBER_DRIFT）
  G7 digest.md 中待确认裁决均已确认或显式覆盖

用法：python3 gate_check.py [--input /input] [--work /app/work] [--output /app/output]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_e as st
import run_manifest as rm

STAGE1, STAGE2, STAGE3, STAGE4, STAGE5 = (
    "stage_01_ingest.json", "stage_02_clean.json", "stage_03_descriptive.json",
    "stage_04_inference.json", "stage_05_result_draft.json")

P_TOKEN = re.compile(r"p\s*(<|=)\s*(\d+\.\d+)")
E_TOKEN = re.compile(r"\b(hedges_g|eta2|omega2|eps2|rank_biserial)\s*=\s*(-?\d+\.\d+)")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def canon_p(p):
    return st.fmt_p(p)


def canon_p_token(m):
    if m.group(1) == "<":
        return "p < %s" % m.group(2)
    return "p = %.4f" % float(m.group(2))


def walk_numbers(obj, key_pred):
    """遍历 result 子树，收集键名满足 key_pred 的数值。"""
    out = []

    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if key_pred(k) and isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append(v)
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec(obj)
    return out


def gate_g0(input_dir, work_dir, output_dir, errs):
    mpath = os.path.join(work_dir, "manifest.json")
    if not os.path.isfile(mpath):
        errs.append(("G0", "G0_MANIFEST_MISSING: %s 不存在（先跑 pipeline_e run）" % mpath))
        return
    m = load_json(mpath)
    for e in m.get("inputs", []):
        p = os.path.join(input_dir, e["file"])
        if not os.path.isfile(p):
            errs.append(("G0", "G0_INPUT_MISSING: %s" % e["file"]))
        elif rm.sha256_file(p) != e["sha256"]:
            errs.append(("G0", "G0_INPUT_CHANGED: %s（输入已变化，必须重跑 pipeline）" % e["file"]))
    for s in m.get("stages", []):
        p = os.path.join(work_dir, s["file"])
        if not os.path.isfile(p):
            errs.append(("G0", "G0_STAGE_MISSING: %s" % s["file"]))
        elif rm.registered_hash(p) != s["sha256"]:
            errs.append(("G0", "G0_STAGE_CHANGED: %s（阶段产物与登记不符）" % s["file"]))
    for o in m.get("outputs", []):
        p = os.path.join(output_dir, o["file"])
        if not os.path.isfile(p):
            errs.append(("G0", "G0_OUTPUT_MISSING: %s" % o["file"]))


def gate_g1(work_dir, result, errs):
    p = os.path.join(work_dir, STAGE2)
    if not os.path.isfile(p):
        errs.append(("G1", "G1_STAGE_MISSING: %s" % STAGE2))
        return
    c2 = load_json(p)
    if c2.get("rows_raw") != c2.get("rows_kept", 0) + c2.get("rows_dropped", 0):
        errs.append(("G1", "G1_CLOSURE: stage_02 rows_raw=%s != kept=%s + dropped=%s"
                     % (c2.get("rows_raw"), c2.get("rows_kept"), c2.get("rows_dropped"))))
    cl = result.get("cleaning", {})
    if cl.get("rows_raw") != cl.get("rows_kept", 0) + cl.get("rows_dropped", 0):
        errs.append(("G1", "G1_CLOSURE: result.cleaning 闭合律不成立"))
    for k in ("rows_raw", "rows_kept", "rows_dropped"):
        if cl.get(k) != c2.get(k):
            errs.append(("G1", "G1_INCONSISTENT: result.cleaning.%s=%s 与 stage_02 %s 不一致"
                         % (k, cl.get(k), c2.get(k))))


def gate_g2(input_dir, work_dir, errs):
    mpath = os.path.join(work_dir, "manifest.json")
    dpath = os.path.join(work_dir, STAGE5)
    if not os.path.isfile(dpath):
        errs.append(("G2", "G2_SKELETON_MISSING: %s（必须先写契约骨架再填数）" % STAGE5))
        return
    draft = load_json(dpath)
    cpath = os.path.join(input_dir, "case.json")
    required = []
    if os.path.isfile(cpath):
        required = load_json(cpath).get("output_contract", {}).get("required_fields", [])
    sk_fields = set(draft.get("skeleton_fields", [])) | set(draft.keys())
    missing = [f for f in required if f not in sk_fields]
    if missing:
        errs.append(("G2", "G2_SKELETON_FIELDS: 骨架缺契约字段 %s" % missing))
    if draft.get("status") != "partial":
        errs.append(("G2", "G2_SKELETON_STATUS: 骨架 status 应为 partial，实为 %s" % draft.get("status")))
    if os.path.isfile(mpath):
        seq = load_json(mpath).get("stages", [])
        order = {s["file"]: s["seq"] for s in seq}
        if STAGE5 in order and STAGE4 in order and not (order[STAGE5] < order[STAGE4]):
            errs.append(("G2", "G2_ORDER: 骨架(seq=%s)未先于推断产物(seq=%s)写出"
                         % (order[STAGE5], order[STAGE4])))


def gate_g3(work_dir, result, errs):
    p3, p4 = os.path.join(work_dir, STAGE3), os.path.join(work_dir, STAGE4)
    if not (os.path.isfile(p3) and os.path.isfile(p4)):
        errs.append(("G3", "G3_STAGE_MISSING: stage_03/04 不存在"))
        return
    s3 = load_json(p3).get("descriptive", {})
    s4 = load_json(p4).get("inference", {})
    for oc, dd in result.get("descriptive", {}).items():
        if oc not in s3:
            errs.append(("G3", "UNTRACEABLE_NUMBER: descriptive.%s 在 stage_03 无来源" % oc))
            continue
        for lab, g in dd.get("groups", {}).items():
            src = s3[oc].get("groups", {}).get(lab)
            if not src or not g:
                errs.append(("G3", "UNTRACEABLE_NUMBER: descriptive.%s.%s 在 stage_03 无来源" % (oc, lab)))
                continue
            for k in ("n", "mean"):
                if g.get(k) != src.get(k):
                    errs.append(("G3", "UNTRACEABLE_NUMBER: descriptive.%s.%s.%s=%r 与 stage_03 来源 %r 不一致"
                                 % (oc, lab, k, g.get(k), src.get(k))))
    for oc, ht in result.get("hypothesis_test", {}).items():
        src = s4.get(oc, {}).get("main", {})
        for k in ("p", "statistic", "method"):
            if ht.get(k) != src.get(k):
                errs.append(("G3", "UNTRACEABLE_NUMBER: hypothesis_test.%s.%s=%r 与 stage_04 来源 %r 不一致"
                             % (oc, k, ht.get(k), src.get(k))))


def gate_g4(result, errs):
    if not result.get("uncertainty"):
        errs.append(("G4", "G4_UNCERTAINTY_EMPTY: uncertainty 为空"))
    if not result.get("limitations"):
        errs.append(("G4", "G4_LIMITATIONS_EMPTY: limitations 为空"))


def gate_g5(result, errs):
    s = result.get("status")
    if s not in st.STATUS_ENUM:
        errs.append(("G5", "G5_INVALID_STATUS: %r 不在枚举 %s" % (s, st.STATUS_ENUM)))
    if s == "partial" and not result.get("exceptions"):
        errs.append(("G5", "G5_DISHONEST_PARTIAL: status=partial 但 exceptions 为空"))


def result_token_sets(result):
    p_tokens, e_tokens = set(), set()
    ht = result.get("hypothesis_test", {})
    for p in walk_numbers(ht, lambda k: k in ("p", "p_raw", "p_holm")):
        p_tokens.add(canon_p(p))
    for oc, e in result.get("effect_size", {}).items():
        if isinstance(e, dict):
            if isinstance(e.get("value"), (int, float)):
                e_tokens.add(st.fmt_effect(e.get("type"), e["value"]))
            if isinstance(e.get("omega2"), (int, float)):
                e_tokens.add(st.fmt_effect("omega2", e["omega2"]))
    for oc, h in ht.items():
        for ph in h.get("post_hoc", []) or []:
            if isinstance(ph.get("effect_value"), (int, float)):
                e_tokens.add(st.fmt_effect(ph.get("effect_type"), ph["effect_value"]))
    main_p = {canon_p(h["p"]) for h in ht.values() if isinstance(h.get("p"), (int, float))}
    main_e = {st.fmt_effect(e["type"], e["value"])
              for e in result.get("effect_size", {}).values()
              if isinstance(e, dict) and isinstance(e.get("value"), (int, float))}
    return p_tokens, e_tokens, main_p, main_e


def gate_g6(output_dir, result, errs):
    rpath = os.path.join(output_dir, "report.md")
    if not os.path.isfile(rpath):
        errs.append(("G6", "G6_REPORT_MISSING: report.md 不存在"))
        return
    with open(rpath, "r", encoding="utf-8") as f:
        text = f.read()
    p_tokens, e_tokens, main_p, main_e = result_token_sets(result)
    rep_p = {canon_p_token(m) for m in P_TOKEN.finditer(text)}
    rep_e = {"%s = %.4f" % (m.group(1), float(m.group(2))) for m in E_TOKEN.finditer(text)}
    for t in sorted(rep_p - p_tokens):
        errs.append(("G6", "REPORT_NUMBER_DRIFT: report.md 出现 %r，result.json 中无一致 p 值" % t))
    for t in sorted(rep_e - e_tokens):
        errs.append(("G6", "REPORT_NUMBER_DRIFT: report.md 出现 %r，result.json 中无一致效应量" % t))
    for t in sorted(main_p - rep_p):
        errs.append(("G6", "REPORT_NUMBER_DRIFT: result.json 主 p 值 %r 未在 report.md 出现" % t))
    for t in sorted(main_e - rep_e):
        errs.append(("G6", "REPORT_NUMBER_DRIFT: result.json 主效应量 %r 未在 report.md 出现" % t))


def gate_g7(work_dir, errs):
    dpath = os.path.join(work_dir, "digest.md")
    if not os.path.isfile(dpath):
        errs.append(("G7", "G7_DIGEST_MISSING: digest.md 不存在"))
        return
    with open(dpath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    pend = [l.strip() for l in lines if re.match(r"^-\s*\[PENDING\]", l)]
    if pend:
        errs.append(("G7", "G7_PENDING_DECISION: %d 项裁决未确认/覆盖：%s"
                     % (len(pend), pend[:5])))


def main():
    ap = argparse.ArgumentParser(description="G0..G7 阶段门")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    errs = []
    rpath = os.path.join(args.output, "result.json")
    result = {}
    if os.path.isfile(rpath):
        try:
            result = load_json(rpath)
        except json.JSONDecodeError as e:
            errs.append(("G5", "G5_RESULT_UNPARSEABLE: %s" % e))
    else:
        errs.append(("G5", "G5_RESULT_MISSING: %s 不存在" % rpath))
    gate_g0(args.input, args.work, args.output, errs)
    if result:
        gate_g1(args.work, result, errs)
        gate_g2(args.input, args.work, errs)
        gate_g3(args.work, result, errs)
        gate_g4(result, errs)
        gate_g5(result, errs)
        gate_g6(args.output, result, errs)
    gate_g7(args.work, errs)
    if errs:
        by_gate = {}
        for g, m in errs:
            by_gate.setdefault(g, []).append(m)
        for g in sorted(by_gate):
            for m in by_gate[g]:
                print("%s FAIL %s" % (g, m))
        print("GATE_CHECK FAIL: %d 项违规" % len(errs))
        return 1
    print("GATE_CHECK PASS: G0-G7 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
