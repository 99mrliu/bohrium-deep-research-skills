#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aggregate_grade.py — 按明文阈值把复核计数映射为统计报告质量等级。

输入：work-dir 下 recheck/*.jsonl（含 verification）、docs.jsonl、verify_report.json
产出：grades.json {"grade","limited","counts","derivation","per_doc",...}
等级 ∈ {adequate, concerns, serious_concerns, ungradable}
阈值规则全文见 rules/recheck_rules.md 第 6 节；此处实现与之一一对应。
仅标准库。
"""
import argparse
import json
import os
import sys


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


def main():
    ap = argparse.ArgumentParser(description="汇总分级")
    ap.add_argument("--work-dir", default="/app/work")
    args = ap.parse_args()

    docs = load_jsonl(os.path.join(args.work_dir, "docs.jsonl"))
    rdir = os.path.join(args.work_dir, "recheck")
    rows = []
    per_doc = {}
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            if fn.endswith(".jsonl"):
                dr = load_jsonl(os.path.join(rdir, fn))
                rows.extend(dr)
                per_doc[fn[:-6]] = len(dr)

    mech = [r for r in rows if not r["check_type"].startswith("completeness:")]
    comp = [r for r in rows if r["check_type"].startswith("completeness:")]

    def is_verified(r):
        return (r.get("verification") or {}).get("verified", True)

    n_pass = sum(1 for r in mech if r["status"] == "pass")
    disc = [r for r in mech if r["status"] == "discrepancy"]
    n_disc_v = sum(1 for r in disc if is_verified(r) and not r.get("downgraded"))
    n_disc_u = len(disc) - n_disc_v
    n_nr = sum(1 for r in mech if r["status"] == "not_recomputable")
    verdict = n_pass + n_disc_v + n_disc_u  # 有判定的机械复核行数
    n_absent = sum(1 for r in comp if r["status"] == "absent")
    n_reported = sum(1 for r in comp if r["status"] == "reported")

    abstract_only_docs = [d["doc_id"] for d in docs
                          if d.get("abstract_only") and d.get("status") == "ok"]
    ok_docs = [d["doc_id"] for d in docs if d.get("status") == "ok"]
    limited = bool(ok_docs) and len(abstract_only_docs) == len(ok_docs)

    derivation = []
    if not mech:
        grade = "ungradable"
        derivation.append("机械复核行数为 0（无数字声明或全部文献抽取失败）→ ungradable。")
    else:
        ratio = (n_disc_v / verdict) if verdict >= 5 else 0.0
        derivation.append(
            "机械复核 %d 行：pass=%d，discrepancy（已验证）=%d，"
            "discrepancy（未验证降级）=%d，not_recomputable=%d。"
            % (len(mech), n_pass, n_disc_v, n_disc_u, n_nr))
        derivation.append("关键完整性缺口 absent=%d（reported=%d）。"
                          % (n_absent, n_reported))
        if n_disc_v >= 3 or (verdict >= 5 and ratio >= 0.3):
            grade = "serious_concerns"
            derivation.append(
                "命中 serious_concerns 阈值：已验证 discrepancy ≥3 或有判定行 ≥5 "
                "且占比 ≥30%%（当前 %d 行，占比 %.0f%%）。"
                % (n_disc_v, ratio * 100))
        elif n_disc_v >= 1 or n_disc_u >= 2 or n_absent >= 2:
            grade = "concerns"
            why = []
            if n_disc_v >= 1:
                why.append("已验证 discrepancy ≥1（%d）" % n_disc_v)
            if n_disc_u >= 2:
                why.append("未验证 discrepancy ≥2（%d，校验失败降级计入）" % n_disc_u)
            if n_absent >= 2:
                why.append("关键统计项 absent ≥2（%d）" % n_absent)
            derivation.append("命中 concerns 阈值：" + "；".join(why) + "。")
        elif n_pass >= 1:
            grade = "adequate"
            derivation.append("存在 ≥1 条已验证 pass，且无 discrepancy、"
                              "关键缺口 ≤1 → adequate。")
        else:
            grade = "ungradable"
            derivation.append("无任何 pass 且无 discrepancy（全部 not_recomputable）"
                              "→ ungradable。")
    if limited:
        derivation.append("全部可解析文献均为仅摘要条目：复核限于摘要口径，标记 "
                          "limited=true；摘要外结论一律不外推。")
    if n_disc_u == 1:
        derivation.append("存在 1 条校验失败的 discrepancy（未验证），按规则"
                          "单独不足以升级，但列入 uncertainties 提示人工核对。")

    grades = {
        "grade": grade,
        "limited": limited,
        "counts": {
            "mechanical_rows": len(mech),
            "pass": n_pass,
            "discrepancy_verified": n_disc_v,
            "discrepancy_unverified": n_disc_u,
            "not_recomputable": n_nr,
            "completeness_reported": n_reported,
            "completeness_absent": n_absent,
        },
        "per_doc_rows": per_doc,
        "abstract_only_docs": abstract_only_docs,
        "derivation": derivation,
        "thresholds_ref": "rules/recheck_rules.md 第 6 节",
    }
    with open(os.path.join(args.work_dir, "grades.json"), "w",
              encoding="utf-8") as f:
        json.dump(grades, f, ensure_ascii=False, indent=2)
    print(json.dumps({"grade": grade, "limited": limited}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
