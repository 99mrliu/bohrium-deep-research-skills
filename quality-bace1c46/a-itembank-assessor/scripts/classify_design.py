#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classify_design.py — 基于关键词加权打分的研究设计分型启发式。

读取 --work 下的 docs.jsonl 与 pages/<doc_id>.jsonl，输出 design.json：
{"docs": {doc_id: {"design_type":..., "confidence":..., "uncertain":bool,
                  "matched_signals":[{"signal","weight","count"}], "scores":{...}}}}
低置信或分差过小标 uncertain=true，交由模型裁决；模型修正写入 design_overrides.json。
仅标准库。
"""
import argparse
import json
import os
import re
import sys

DESIGN_TYPES = ["rct", "cohort", "case_control", "cross_sectional",
                "diagnostic", "systematic_review", "other"]

# (短语, 权重)；多词强信号权重 3，单词/弱信号 1-2
SIGNALS = {
    "rct": [
        ("randomized controlled trial", 3), ("randomised controlled trial", 3),
        ("randomly assigned", 3), ("randomly allocated", 3), ("random allocation", 3),
        ("double-blind", 2), ("double blind", 2), ("placebo-controlled", 2),
        ("placebo", 1), ("randomized", 2), ("randomised", 2), ("randomization", 2),
        ("随机对照", 3), ("随机分组", 2), ("随机化", 2), ("双盲", 2), ("安慰剂", 2),
    ],
    "cohort": [
        ("prospective cohort", 3), ("retrospective cohort", 3),
        ("cohort study", 3), ("follow-up", 2), ("followed up", 2),
        ("cohort", 2), ("incidence", 1), ("person-years", 2),
        ("队列", 2), ("前瞻性", 2), ("随访", 2), ("人年", 2),
    ],
    "case_control": [
        ("case-control", 3), ("case control", 3),
        ("cases and controls", 3), ("controls were selected", 2),
        ("odds ratio", 1), ("病例对照", 3), ("病例组", 1), ("对照组", 1),
    ],
    "cross_sectional": [
        ("cross-sectional", 3), ("cross sectional", 3),
        ("prevalence survey", 2), ("prevalence", 1), ("questionnaire survey", 1),
        ("横断面", 3), ("现况调查", 3), ("患病率", 1),
    ],
    "diagnostic": [
        ("diagnostic accuracy", 3), ("sensitivity and specificity", 3),
        ("receiver operating", 3), ("roc curve", 2), ("auc", 2),
        ("sensitivity", 2), ("specificity", 2), ("reference standard", 2),
        ("诊断准确性", 3), ("诊断试验", 3), ("灵敏度", 2), ("特异度", 2), ("金标准", 2),
    ],
    "systematic_review": [
        ("systematic review", 3), ("meta-analysis", 3), ("meta analysis", 3),
        ("prisma", 3), ("pooled", 2), ("forest plot", 2), ("heterogeneity", 1),
        ("pubmed", 1), ("embase", 1), ("系统综述", 3), ("系统评价", 3), ("meta分析", 3),
    ],
}

MIN_SCORE = 3          # 低于此总分 → other
UNCERTAIN_SCORE = 4    # 低于此总分 → uncertain
UNCERTAIN_MARGIN = 1   # 前两名分差 ≤ 此值 → uncertain


def log(msg):
    print("[classify_design] %s" % msg, file=sys.stderr)


def load_pages(work_dir, doc_id):
    path = os.path.join(work_dir, "pages", doc_id + ".jsonl")
    texts = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    texts.append(json.loads(line).get("text", ""))
    except Exception as e:
        log("读取页面失败 %s: %s" % (path, e))
    return "\n".join(texts)


def classify(text):
    low = (text or "").casefold()
    scores, matched = {}, {}
    for dt, sigs in SIGNALS.items():
        total = 0
        hits = []
        for phrase, w in sigs:
            n = low.count(phrase.casefold())
            if n:
                capped = min(n, 3)
                total += w * capped
                hits.append({"signal": phrase, "weight": w, "count": n})
        scores[dt] = total
        matched[dt] = hits
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_dt, top_sc = ranked[0]
    second_sc = ranked[1][1] if len(ranked) > 1 else 0
    if top_sc < MIN_SCORE:
        return {"design_type": "other", "confidence": 0.0, "uncertain": True,
                "matched_signals": matched.get(top_dt, []), "scores": scores}
    confidence = round(top_sc / (top_sc + second_sc + 1.0), 3)
    uncertain = top_sc < UNCERTAIN_SCORE or (top_sc - second_sc) <= UNCERTAIN_MARGIN
    return {"design_type": top_dt, "confidence": confidence, "uncertain": uncertain,
            "matched_signals": matched.get(top_dt, []), "scores": scores}


def main():
    ap = argparse.ArgumentParser(description="研究设计启发式分型")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()

    docs_path = os.path.join(args.work, "docs.jsonl")
    if not os.path.isfile(docs_path):
        log("docs.jsonl 不存在，输出空 design.json")
        with open(os.path.join(args.work, "design.json"), "w", encoding="utf-8") as f:
            json.dump({"docs": {}}, f, ensure_ascii=False, indent=2)
        return 0

    out = {"docs": {}}
    with open(docs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            doc_id = rec["doc_id"]
            if rec.get("tier") == "failed":
                out["docs"][doc_id] = {"design_type": "unassessable",
                                       "confidence": 0.0, "uncertain": True,
                                       "matched_signals": [], "scores": {},
                                       "note": "解析失败，无法分型"}
                continue
            text = load_pages(args.work, doc_id)
            out["docs"][doc_id] = classify(text)
            log("%s → %s (conf=%s, uncertain=%s)" %
                (doc_id, out["docs"][doc_id]["design_type"],
                 out["docs"][doc_id]["confidence"], out["docs"][doc_id]["uncertain"]))

    with open(os.path.join(args.work, "design.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
