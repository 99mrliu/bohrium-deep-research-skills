#!/usr/bin/env python3
"""evmap.py — 证据层引擎：证据清单 + 主张—证据对齐候选 + 交付门禁。

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
本引擎不判断论文对错；它把"文中到底有什么证据"（数值、统计量、图表、设计
标签）做成确定性清单，再用四条机械规则生成"主张—证据错位"候选（E1–E4），
每条候选都带句子 id 与逐字 quote，由审查者定案。它堵的正是"结论超出数据"
这条最高频逻辑裂缝：主张读得通顺，但证据层根本没有对应物。

Subcommands:
  scan       --paper PATH --work DIR    论文文本 -> sentences.jsonl + evidence_map.json
  candidates --work DIR                 -> candidates.json（E1–E4 错位候选）
  verify     --work DIR --findings F    交付门禁：quote 逐字 + 证据不足条必填缺口
                                        exit 4 = 有违规

Exit codes: 0 ok；2 有告警；3 输入失败；4 verify 违规。stderr 显式报错。
"""
import argparse
import json
import os
import re
import sys

VERSION = "evmap/1.0.0"

SEC_RX = [
    ("abstract", re.compile(r"^\s*(abstract|摘要)\b[:：]?\s*$", re.I)),
    ("introduction", re.compile(r"^\s*(\d+\.?\s*)?(introduction|引言|绪论)\s*$", re.I)),
    ("methods", re.compile(r"^\s*(\d+\.?\s*)?(materials?\s+and\s+methods?|methods?|methodology|材料与方法|实验方法|方法)\s*$", re.I)),
    ("results", re.compile(r"^\s*(\d+\.?\s*)?(results?(\s+and\s+discussion)?|实验结果|结果与分析|结果)\s*$", re.I)),
    ("discussion", re.compile(r"^\s*(\d+\.?\s*)?(discussion|讨论)\s*$", re.I)),
    ("conclusion", re.compile(r"^\s*(\d+\.?\s*)?(conclusions?|结论)\s*$", re.I)),
    ("references", re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I)),
]

STRONG = ["证明", "证实", "导致", "决定", "确立", "首次实现", "显著优于",
          "demonstrate", "demonstrated", "prove", "proven", "establish",
          "established", "cause", "caused", "determines", "conclusively"]
MID = ["表明", "显示", "揭示", "提升", "提高", "降低", "改善", "优于",
       "show", "shows", "showed", "reveal", "improve", "improved",
       "enhance", "enhanced", "outperform"]
WEAK = ["提示", "初步", "可能", "有望", "suggest", "suggests", "indicate",
        "indicates", "preliminary", "potentially", "may", "might"]
SIG_WORDS = ["显著", "significant", "significantly", "p <", "p<", "p =", "p=",
             "置信区间", "confidence interval", "95% ci", "检验"]
STAT_MARK_RX = re.compile(
    r"(p\s*[<=>]\s*0?\.\d+|95\s*%\s*(ci|置信)|置信区间|confidence interval|"
    r"n\s*=\s*\d+|±|标准差|standard deviation|sd\s*=|t\s*检验|方差分析|anova|"
    r"mann-whitney|wilcoxon|卡方|chi-square)", re.I)
NUM_RX = re.compile(r"\d+(\.\d+)?\s*(%|％|倍|x|×|周次|小时|h|ms|s|mpa|μm|um|nm|"
                    r"mm|cm|kg|mg|g|ml|l|°c|k|周|天|例|个)?", re.I)
FIGREF_RX = re.compile(r"(图|表|figure|fig\.?|table)\s*(\d+)", re.I)
CAPTION_RX = re.compile(r"^\s*(图|表|figure|fig\.?|table)\s*(\d+)\s*[:：.．]", re.I)
DESIGN_WEAK = ["预实验", "试点", "可行性", "初步探索", "pilot", "feasibility",
               "proof-of-concept", "proof of concept", "exploratory"]
OBSERV = ["横断面", "回顾性", "队列观察", "相关性分析", "cross-sectional",
          "retrospective", "observational", "correlational"]

CANDIDATE_TYPES = ["overclaim_no_evidence", "strength_design_mismatch",
                   "significance_without_stats", "dangling_figref"]


def eprint(*a):
    print(*a, file=sys.stderr)


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def load_sents(work):
    out = []
    with open(os.path.join(work, "sentences.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            out.append(json.loads(line))
    return out


def split_and_anchor(text):
    """独立实现的锚定：行内按中英文句末标点切，et al. 等缩写受保护。"""
    text = re.sub(r"\b(et al|e\.g|i\.e|cf|vs|Fig|Dr|Prof)\.\s",
                  lambda m: m.group(0)[:-2] + "\x01 ", text)
    sents, marks, pos = [], [], 0
    for line in text.splitlines(keepends=True):
        raw = line.strip()
        if raw:
            for name, rx in SEC_RX:
                if rx.match(raw):
                    marks.append({"section": name, "offset": pos})
                    break
        pos += len(line)
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            pos += len(line)
            continue
        base = pos + (len(line) - len(line.lstrip()))
        inner = 0
        for p in re.split(r"(?<=[。！？!?；;])\s*|(?<=[.])\s+(?=[A-Z0-9（(])", stripped):
            p = p.strip()
            if not p:
                continue
            idx = stripped.find(p, inner)
            inner = idx + len(p)
            sec = "front"
            for m in marks:
                if m["offset"] <= base + idx:
                    sec = m["section"]
            sents.append({"id": "S%04d" % (len(sents) + 1), "offset": base + idx,
                          "section": sec, "text": p.replace("\x01", ".")})
        pos += len(line)
    return sents, marks


def strength(sent):
    low = sent.lower()
    if any(w in sent for w in STRONG[:7]) or any(w in low for w in STRONG[7:]):
        return "strong"
    if any(w in sent for w in MID[:12]) or any(w in low for w in MID[12:]):
        return "mid"
    if any(w in sent for w in WEAK[:5]) or any(w in low for w in WEAK[5:]):
        return "weak"
    return "none"


def cmd_scan(args):
    with open(args.paper, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        eprint("FAIL: empty paper text: %s" % args.paper)
        return 3
    os.makedirs(args.work, exist_ok=True)
    sents, marks = split_and_anchor(text)
    atomic_write(os.path.join(args.work, "sentences.jsonl"),
                 "\n".join(json.dumps(s, ensure_ascii=False) for s in sents) + "\n")
    captions, figrefs = {}, []
    numeric, stat_hits = [], []
    for s in sents:
        m = CAPTION_RX.match(s["text"])
        if m:
            captions["%s%s" % (m.group(1).lower().replace("figure", "fig").replace("fig.", "fig"), m.group(2))] = s["id"]
        for m in FIGREF_RX.finditer(s["text"]):
            kind = m.group(1).lower().replace("figure", "fig").replace("fig.", "fig")
            figrefs.append({"kind": kind, "num": m.group(2), "sentence_id": s["id"],
                            "in_caption": bool(CAPTION_RX.match(s["text"]))})
        nums = NUM_RX.findall(s["text"])
        if nums:
            numeric.append({"sentence_id": s["id"], "section": s["section"],
                            "n_numbers": len(nums)})
        if STAT_MARK_RX.search(s["text"]):
            stat_hits.append(s["id"])
    low_all = text.lower()
    emap = {
        "engine": VERSION,
        "n_sentences": len(sents),
        "sections": marks,
        "captions": captions,
        "figure_refs": figrefs,
        "numeric_sentences": numeric,
        "stat_sentences": stat_hits,
        "design_flags": {
            "weak_design": [w for w in DESIGN_WEAK if w in text or w in low_all],
            "observational": [w for w in OBSERV if w in text or w in low_all],
        },
        "strength_index": [{"sentence_id": s["id"], "section": s["section"],
                            "strength": strength(s["text"])}
                           for s in sents if strength(s["text"]) != "none"],
    }
    atomic_write(os.path.join(args.work, "evidence_map.json"),
                 json.dumps(emap, ensure_ascii=False, indent=2))
    print("scan: %d sentences, %d captions, %d figrefs, %d numeric, %d stat, %d strength-marked"
          % (len(sents), len(captions), len(figrefs), len(numeric),
             len(stat_hits), len(emap["strength_index"])))
    return 0


HAN_RX = re.compile(r"[一-鿿]+")
ENG_RX = re.compile(r"[A-Za-z]{4,}")


def key_tokens(sent):
    """主张关键词：中文实义 2-gram + 英文长词，去停用。"""
    toks = set()
    for chunk in HAN_RX.findall(sent):
        for i in range(len(chunk) - 1):
            g = chunk[i:i + 2]
            if g not in ("本文", "我们", "本研", "研究", "实验", "表明", "证明",
                         "结果", "讨论", "方法", "摘要", "引言"):
                toks.add(g)
    for w in ENG_RX.findall(sent.lower()):
        if w not in ("this", "that", "with", "from", "show", "shows", "study",
                     "results", "paper"):
            toks.add(w)
    return toks


def cmd_candidates(args):
    emap_p = os.path.join(args.work, "evidence_map.json")
    if not os.path.exists(emap_p):
        eprint("FAIL: run scan first (evidence_map.json missing)")
        return 3
    emap = json.load(open(emap_p, encoding="utf-8"))
    sents = {s["id"]: s for s in load_sents(args.work)}
    results_num_sents = [sents[n["sentence_id"]] for n in emap["numeric_sentences"]
                         if n["section"] in ("results", "discussion")
                         and n["sentence_id"] in sents]
    has_stats = bool(emap["stat_sentences"])
    cap_keys = set(emap["captions"].keys())
    cands = []
    # E1: abstract/discussion/conclusion 中的 strong 主张，与结果章任何数值句
    #     无关键词重叠，且自身不挂图表引用 → 结论超出数据候选
    for e in emap["strength_index"]:
        s = sents[e["sentence_id"]]
        if e["strength"] != "strong" or s["section"] not in (
                "abstract", "discussion", "conclusion", "front"):
            continue
        toks = key_tokens(s["text"])
        has_figref = any(r["sentence_id"] == s["id"] for r in emap["figure_refs"])
        overlap = any(toks & key_tokens(r["text"]) for r in results_num_sents)
        if not overlap and not has_figref:
            cands.append({"type": "overclaim_no_evidence", "rule": "E1",
                          "sentence_id": s["id"], "section": s["section"],
                          "strength": e["strength"],
                          "quote": s["text"][:160],
                          "basis": "结果/讨论章的数值句与该强主张无关键词重叠，"
                                   "且无图表引用可挂——结论可能超出数据",
                          "needed": "指出支撑该主张的具体数据句或图表；否则降级表述强度"})
    # E2: 强主张 × 弱设计标签（限摘要/讨论/结论，引言背景句不算）
    flags = emap["design_flags"]["weak_design"]
    if flags:
        for e in emap["strength_index"]:
            if e["strength"] == "strong":
                s = sents[e["sentence_id"]]
                if s["section"] not in ("abstract", "discussion", "conclusion", "front"):
                    continue
                cands.append({"type": "strength_design_mismatch", "rule": "E2",
                              "sentence_id": s["id"], "section": s["section"],
                              "quote": s["text"][:160],
                              "basis": "研究自标 %s，但此句用强断言措辞" % "/".join(flags),
                              "needed": "强断言需确证性设计支撑；否则改用提示性措辞"})
    # E3: “显著”主张 × 全文无统计量
    if not has_stats:
        for s in sents.values():
            if any(w in s["text"] for w in ("显著",)) or "significant" in s["text"].lower():
                cands.append({"type": "significance_without_stats", "rule": "E3",
                              "sentence_id": s["id"], "section": s["section"],
                              "quote": s["text"][:160],
                              "basis": "句称“显著”但全文未检出 p 值/置信区间/检验名",
                              "needed": "补统计检验与 p/CI；或将“显著”改为“提高了/降低了”"})
    # E4: 引用了不存在的图表编号
    for r in emap["figure_refs"]:
        if not r["in_caption"] and "%s%s" % (r["kind"], r["num"]) not in cap_keys:
            cands.append({"type": "dangling_figref", "rule": "E4",
                          "sentence_id": r["sentence_id"],
                          "quote": sents[r["sentence_id"]]["text"][:160],
                          "basis": "正文引用 %s%s 但全文无对应图表标题" % (r["kind"], r["num"]),
                          "needed": "补图表或修正编号"})
    # 去重（同句同规则）
    seen, uniq = set(), []
    for c in cands:
        k = (c["rule"], c["sentence_id"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    out = {"engine": VERSION,
           "instruction": "以下均为机械候选，不是结论。逐条定案：成立则转 finding "
                          "（带严重度与可执行建议），不成立则记驳回理由；无法确认标"
                          "待复核并写明缺什么。",
           "n_candidates": len(uniq), "candidates": uniq}
    atomic_write(os.path.join(args.work, "candidates.json"),
                 json.dumps(out, ensure_ascii=False, indent=2))
    print("candidates: E1=%d E2=%d E3=%d E4=%d" % (
        sum(1 for c in uniq if c["rule"] == "E1"),
        sum(1 for c in uniq if c["rule"] == "E2"),
        sum(1 for c in uniq if c["rule"] == "E3"),
        sum(1 for c in uniq if c["rule"] == "E4")))
    return 0


def cmd_verify(args):
    spath = os.path.join(args.work, "sentences.jsonl")
    if not os.path.exists(spath):
        eprint("FAIL: sentences.jsonl missing; run scan first")
        return 3
    sents = {s["id"]: s for s in load_sents(args.work)}
    try:
        findings = json.load(open(args.findings, encoding="utf-8"))
    except Exception as exc:
        eprint("FAIL: cannot parse findings %s: %s" % (args.findings, exc))
        return 3
    if isinstance(findings, dict):
        findings = findings.get("findings", [])
    problems = []
    for i, f in enumerate(findings, 1):
        fid = f.get("id", "row%d" % i)
        sid = f.get("sentence_id")
        if sid not in sents:
            problems.append({"id": fid, "problem": "unknown sentence_id: %s" % sid})
        else:
            q = f.get("quote", "")
            if q and q not in sents[sid]["text"] and q.rstrip(".…") not in sents[sid]["text"]:
                problems.append({"id": fid, "problem": "quote not verbatim",
                                 "quote_head": q[:60]})
        if f.get("type") == "证据不足" and not (f.get("needed_evidence") or "").strip():
            problems.append({"id": fid,
                             "problem": "证据不足条目必须填 needed_evidence（补什么证据才能闭环）"})
        if not (f.get("suggestion") or "").strip():
            problems.append({"id": fid, "problem": "missing suggestion"})
        elif len(f["suggestion"]) < 15:
            problems.append({"id": fid,
                             "problem": "suggestion too vague (<15 chars)；须落到改哪句、补什么"})
    atomic_write(os.path.join(args.work, "verify_report.json"),
                 json.dumps({"engine": VERSION, "n_findings": len(findings),
                             "n_problems": len(problems), "problems": problems},
                            ensure_ascii=False, indent=2))
    if problems:
        eprint("VERIFY FAIL: %d problem(s); see verify_report.json" % len(problems))
        return 4
    print("verify ok: %d findings" % len(findings))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--paper", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("candidates")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_candidates)
    p = sub.add_parser("verify")
    p.add_argument("--work", required=True)
    p.add_argument("--findings", required=True)
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
