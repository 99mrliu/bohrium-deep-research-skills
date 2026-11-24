#!/usr/bin/env python3
"""chain_lint.py — 论证链登记与机械候选扫描。

子命令:
    scaffold  由 work/doc_map.json 生成论证链登记模板 work/chain_register.json
              （环节：研究问题/假设/关键方法/核心结果/结论主张/外推边界；
               每环要求原文引用+定位，初始 status=pending_review，由 Agent 填写转正）
    lint      机械候选扫描，输出 work/lint_candidates.json：
              C1 观察性/横断面设计 + 结论/讨论出现因果措辞 -> 候选"因果混淆"
              C2 结果节出现因果措辞 -> 候选"因果混淆"（结果节应报告关联而非因果）
              X1 结论出现结果节从未出现的数值 -> 候选"外推/无据结论"
              Q1 引言问题与结论句重叠度过低 -> 候选"答非所问/问题未回答"
              全部 candidate=true，须人工（Agent）核对后在
              work/lint_dispositions.json 中转正(confirmed)或驳回(rejected)，防误报。

用法:
    python3 chain_lint.py scaffold --work /app/work
    python3 chain_lint.py lint --work /app/work
退出码: 0 成功；非 0 失败并打印原因到 stderr。
"""
import argparse
import json
import os
import re
import sys

CAUSAL_TERMS = ["导致", "致使", "引起", "造成", "证明", "证实了", "决定了", "决定",
                "因果", "prove", "proves", "proven", "demonstrate that",
                "cause", "causes", "caused", "result in", "results in",
                "determine", "determines"]
OBSERVATIONAL_TERMS = ["横断面", "cross-sectional", "观察性", "observational",
                       "相关性", "correlational", "correlation", "回顾性",
                       "retrospective", "问卷调查", "survey", "现况调查"]
HEDGING_TERMS = ["提示", "可能", "或许", "推测", "有望", "suggest", "suggests",
                 "may", "might", "could", "possibly"]
RE_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|例|人|名|分|岁|mg|mmol|天|年)?")

LINKS = [
    ("L1", "research_question", "研究问题", "introduction"),
    ("L2", "hypothesis", "研究假设", "introduction"),
    ("L3", "key_methods", "关键方法", "methods"),
    ("L4", "core_results", "核心结果", "results"),
    ("L5", "conclusion_claims", "结论主张", "conclusion"),
    ("L6", "extrapolation_boundary", "外推边界", "conclusion"),
]
PAIRS = [("research_question", "hypothesis"), ("hypothesis", "key_methods"),
         ("key_methods", "core_results"), ("core_results", "conclusion_claims"),
         ("conclusion_claims", "extrapolation_boundary")]


def eprint(msg):
    sys.stderr.write("chain_lint.py: %s\n" % msg)


def load_doc_map(work):
    path = os.path.join(work, "doc_map.json")
    if not os.path.isfile(path):
        eprint("失败：缺少 %s，请先运行 doc_map.py" % path)
        sys.exit(2)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def atomic_write_json(path, obj):
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sentences(doc_map, role):
    return doc_map.get("section_sentences", {}).get(role, [])


def cmd_scaffold(work):
    doc_map = load_doc_map(work)
    links = []
    for lid, key, label, role in LINKS:
        pool = sentences(doc_map, role)
        suggestion = None
        if key == "research_question" and doc_map.get("intro_questions"):
            qs = doc_map["intro_questions"]
            suggestion = {"quote": "；".join(q["question"] for q in qs)[:300],
                          "locator": ";".join(q["question_locator"] for q in qs)}
        elif key == "core_results":
            numbered = [s for s in pool if RE_NUMBER.search(s["text"])]
            if numbered:
                suggestion = {"quote": numbered[0]["text"][:300],
                              "locator": numbered[0]["locator"]}
        elif pool:
            suggestion = {"quote": pool[0]["text"][:300],
                          "locator": pool[0]["locator"]}
        links.append({
            "id": lid, "link": key, "label": label,
            "claim": "", "quote": "", "locator": "",
            "status": "pending_review",
            "suggestion": suggestion,
            "fill_instructions": "请用稿件原文填写 claim/quote/locator，"
                                 "status 置 confirmed；若该环在稿件中确实缺失，"
                                 "置 broken 并保留空 quote。",
        })
    register = {
        "case_id": doc_map.get("case_id"),
        "links": links,
        "pairs": [{"from": a, "to": b, "consistent": None,
                   "note": "待 Agent 核对上下游一致性"} for a, b in PAIRS],
    }
    out = os.path.join(work, "chain_register.json")
    if os.path.isfile(out):
        eprint("提示：%s 已存在，覆盖为模板（如已填写请先备份）" % out)
    atomic_write_json(out, register)
    print("chain_register.json 模板已生成: %d 环 + %d 条链边，全部 pending_review" %
          (len(links), len(PAIRS)))
    return 0


def contains_any(text, terms):
    low = text.lower()
    return [t for t in terms if t.lower() in low]


def cmd_lint(work):
    doc_map = load_doc_map(work)
    candidates = []

    methods_sents = sentences(doc_map, "methods")
    results_text = " ".join(s["text"] for s in sentences(doc_map, "results"))
    design_evs = [(s["text"], s["locator"]) for s in methods_sents
                  if contains_any(s["text"], OBSERVATIONAL_TERMS)]
    design_hits = contains_any(" ".join(s["text"] for s in methods_sents),
                               OBSERVATIONAL_TERMS)
    if design_evs:
        design_quote, design_locator = design_evs[0]
    else:
        design_quote, design_locator = "、".join(design_hits), "methods"

    # C1: 观察性设计 + 结论/讨论因果措辞
    for role in ("conclusion", "discussion"):
        for s in sentences(doc_map, role):
            causal = contains_any(s["text"], CAUSAL_TERMS)
            hedges = contains_any(s["text"], HEDGING_TERMS)
            if causal and design_hits and not hedges:
                candidates.append({
                    "type": "causal_confusion",
                    "rule": "C1",
                    "evidence": {
                        "design_quote": design_quote,
                        "design_locator": design_locator,
                        "claim_quote": s["text"],
                        "claim_locator": s["locator"],
                    },
                    "false_positive_guard": "若句中含'提示/可能'等推测措辞或方法实为随机对照/实验设计，"
                                            "应驳回；核对 methods 原文确认设计类型。",
                })

    # C2: 结果节出现因果措辞
    for s in sentences(doc_map, "results"):
        causal = contains_any(s["text"], CAUSAL_TERMS)
        hedges = contains_any(s["text"], HEDGING_TERMS)
        if causal and not hedges:
            candidates.append({
                "type": "causal_confusion",
                "rule": "C2",
                "evidence": {
                    "design_quote": "结果节应报告关联/差异而非因果",
                    "design_locator": "results",
                    "claim_quote": s["text"],
                    "claim_locator": s["locator"],
                },
                "false_positive_guard": "若稿件为随机对照试验且该句仅复述统计检验结论，可驳回。",
            })

    # X1: 结论出现结果节从未出现的数值
    for s in sentences(doc_map, "conclusion"):
        for m in RE_NUMBER.finditer(s["text"]):
            token = m.group(0).strip()
            core = re.match(r"\d+(?:\.\d+)?", token).group(0)
            if core not in results_text:
                candidates.append({
                    "type": "unsupported_conclusion",
                    "rule": "X1",
                    "evidence": {
                        "claim_quote": s["text"],
                        "claim_locator": s["locator"],
                        "new_value": token,
                        "design_quote": "结果节全文未出现数值 '%s'" % core,
                        "design_locator": "results",
                    },
                    "false_positive_guard": "若该数值是结果节数值的显式换算（如由均值差直接算百分比）"
                                            "且稿件已说明算法，可驳回；核对 results 原文。",
                })

    # Q1: 引言问题未在结论中得到回应（重叠度低于阈值）
    for q in doc_map.get("intro_questions", []):
        if not q.get("answered_candidate", True):
            candidates.append({
                "type": "unanswered_question",
                "rule": "Q1",
                "evidence": {
                    "design_quote": q["question"],
                    "design_locator": q["question_locator"],
                    "claim_quote": q.get("best_conclusion_sentence") or "(结论节无匹配句)",
                    "claim_locator": q.get("best_conclusion_locator") or "conclusion",
                    "overlap_score": q.get("overlap_score"),
                },
                "false_positive_guard": "重叠度仅是词面信号；若结论以同义改写实质回答了该问题，"
                                        "或讨论节明确声明留待后续研究，可驳回或降级。",
            })

    # 稳定排序 -> 稳定编号（幂等）
    candidates.sort(key=lambda c: (c["rule"], c["type"],
                                   c["evidence"].get("claim_locator", ""),
                                   c["evidence"].get("new_value", "")))
    for i, c in enumerate(candidates, start=1):
        c["id"] = "CAND-%03d" % i
        c["candidate"] = True
        c["status"] = "pending_review"

    out = {"case_id": doc_map.get("case_id"),
           "note": "全部为机械候选（candidate=true），须 Agent 核对后在 "
                   "lint_dispositions.json 中 confirmed/rejected",
           "candidates": candidates}
    atomic_write_json(os.path.join(work, "lint_candidates.json"), out)
    print("lint_candidates.json 已生成: %d 条候选（C1/C2 因果, X1 无据数值, Q1 未答问题）"
          % len(candidates))
    return 0


def main():
    ap = argparse.ArgumentParser(description="论证链登记模板生成与机械候选扫描")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("scaffold", "lint"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True, help="工作目录（如 /app/work）")
    args = ap.parse_args()
    if args.command == "scaffold":
        return cmd_scaffold(args.work)
    return cmd_lint(args.work)


if __name__ == "__main__":
    sys.exit(main())
