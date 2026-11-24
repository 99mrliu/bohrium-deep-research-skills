#!/usr/bin/env python3
"""chainlint.py — 推理层引擎：设计—措辞对齐 + 前提覆盖 + 推理链候选。

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
本引擎不判定推理正误；它把推理链上可机械化的四处断裂做成候选（R1–R4），
每条候选同时锚定"前提端"与"结论端"句子，由审查者定案。堵的失败模式：
相关写成因果、结论的前提在结果章根本没交付、替代解释不讨论、小样本
配全称结论。

Subcommands:
  scan       --paper PATH --work DIR    -> sentences.jsonl + reasoning_map.json
  candidates --work DIR                 -> chain_candidates.json（R1–R4）
  verify     --work DIR --findings F    门禁：quote 逐字 + 每条 finding 必须
                                        两端锚定（结论句 + 前提句 id）
Exit codes: 0 ok；2 告警；3 输入失败；4 verify 违规。stderr 显式报错。
"""
import argparse
import json
import os
import re
import sys

VERSION = "chainlint/1.0.0"

SEC_RX = [
    ("abstract", re.compile(r"^\s*(abstract|摘要)\b[:：]?\s*$", re.I)),
    ("introduction", re.compile(r"^\s*(\d+\.?\s*)?(introduction|引言|绪论)\s*$", re.I)),
    ("methods", re.compile(r"^\s*(\d+\.?\s*)?(materials?\s+and\s+methods?|methods?|methodology|材料与方法|实验方法|方法)\s*$", re.I)),
    ("results", re.compile(r"^\s*(\d+\.?\s*)?(results?(\s+and\s+discussion)?|实验结果|结果与分析|结果)\s*$", re.I)),
    ("discussion", re.compile(r"^\s*(\d+\.?\s*)?(discussion|讨论)\s*$", re.I)),
    ("conclusion", re.compile(r"^\s*(\d+\.?\s*)?(conclusions?|结论)\s*$", re.I)),
    ("references", re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I)),
]

CAUSAL = ["导致", "促使", "驱动", "决定", "引发", "造成", "从而", "使得",
          "cause", "causes", "caused", "drive", "drives", "lead to", "leads to",
          "led to", "result in", "results in", "therefore improves",
          "determines", "因而提高", "由此提升"]
OBSERV_DESIGN = ["横断面", "回顾性", "观察性", "相关性分析", "问卷调查",
                 "cross-sectional", "retrospective", "observational",
                 "correlational", "survey-based"]
EXPER_DESIGN = ["随机", "随机分组", "随机对照", "双盲", "rct", "randomized",
                "randomised", "controlled trial", "placebo"]
LIMIT_CUES = ["局限", "不足", "限制", "替代解释", "另一种可能", "混杂",
              "limitation", "limitations", "shortcoming", "caveat",
              "alternative explanation", "confound"]
UNIVERSAL = ["所有", "任何", "普遍", "总是", "均", "一切", "all ", "any ",
             "always", "every", "universal"]
SMALL_N_RX = re.compile(r"n\s*=\s*(\d+)", re.I)
CORREL_WORDS = ["相关", "关联", "伴随", "correlat", "associat", "accompan"]


def eprint(*a):
    print(*a, file=sys.stderr)


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def anchor(text):
    """行内切句 + 章节检测；缩写句点受保护。"""
    text = re.sub(r"\b(et al|e\.g|i\.e|cf|vs|Fig|Dr|Prof)\.\s",
                  lambda m: m.group(0)[:-2] + "\x02 ", text)
    marks, pos = [], 0
    for line in text.splitlines(keepends=True):
        raw = line.strip()
        for name, rx in SEC_RX:
            if rx.match(raw):
                marks.append({"section": name, "offset": pos})
                break
        pos += len(line)
    sents, pos = [], 0
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
                          "section": sec, "text": p.replace("\x02", ".")})
        pos += len(line)
    return sents, marks


def load_sents(work):
    with open(os.path.join(work, "sentences.jsonl"), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


def has_any(text, cues, casefold=True):
    t = text.lower() if casefold else text
    return [c for c in cues if (c.lower() if casefold else c) in t]


HAN_RX = re.compile(r"[一-鿿]+")
ENG_RX = re.compile(r"[A-Za-z]{4,}")


def key_tokens(sent):
    toks = set()
    for chunk in HAN_RX.findall(sent):
        for i in range(len(chunk) - 1):
            g = chunk[i:i + 2]
            if g not in ("本文", "我们", "本研", "研究", "实验", "表明", "证明",
                         "结果", "讨论", "方法", "摘要", "引言", "因此", "所以",
                         "这一", "这些", "上述"):
                toks.add(g)
    for w in ENG_RX.findall(sent.lower()):
        if w not in ("this", "that", "these", "with", "from", "thus", "hence",
                     "therefore", "study", "results", "show", "shows"):
            toks.add(w)
    return toks


def cmd_scan(args):
    with open(args.paper, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        eprint("FAIL: empty paper text")
        return 3
    os.makedirs(args.work, exist_ok=True)
    sents, marks = anchor(text)
    atomic_write(os.path.join(args.work, "sentences.jsonl"),
                 "\n".join(json.dumps(s, ensure_ascii=False) for s in sents) + "\n")
    causal_hits = [{"sentence_id": s["id"], "section": s["section"],
                    "cues": has_any(s["text"], CAUSAL)}
                   for s in sents if has_any(s["text"], CAUSAL)]
    small_n = []
    for s in sents:
        for m in SMALL_N_RX.finditer(s["text"]):
            small_n.append({"sentence_id": s["id"], "n": int(m.group(1))})
    rmap = {
        "engine": VERSION,
        "n_sentences": len(sents),
        "sections": marks,
        "design": {
            "observational_cues": has_any(text, OBSERV_DESIGN),
            "experimental_cues": has_any(text, EXPER_DESIGN),
            "correlation_words": has_any(text, CORREL_WORDS),
        },
        "causal_sentences": causal_hits,
        "limitation_sentences": [s["id"] for s in sents if has_any(s["text"], LIMIT_CUES)],
        "universal_sentences": [s["id"] for s in sents if has_any(s["text"], UNIVERSAL, casefold=True)],
        "sample_sizes": small_n,
    }
    atomic_write(os.path.join(args.work, "reasoning_map.json"),
                 json.dumps(rmap, ensure_ascii=False, indent=2))
    print("scan: %d sentences; causal=%d limitation=%d universal=%d; design=%s"
          % (len(sents), len(causal_hits), len(rmap["limitation_sentences"]),
             len(rmap["universal_sentences"]), rmap["design"]))
    return 0


def cmd_candidates(args):
    rpath = os.path.join(args.work, "reasoning_map.json")
    if not os.path.exists(rpath):
        eprint("FAIL: run scan first")
        return 3
    rmap = json.load(open(rpath, encoding="utf-8"))
    sents = {s["id"]: s for s in load_sents(args.work)}
    by_sec = {}
    for s in sents.values():
        by_sec.setdefault(s["section"], []).append(s)
    results_sents = by_sec.get("results", [])
    cands = []
    obs = rmap["design"]["observational_cues"]
    exp = rmap["design"]["experimental_cues"]
    # R1: 观察性/相关性设计 + 结论位因果措辞
    if obs and not exp:
        for h in rmap["causal_sentences"]:
            s = sents[h["sentence_id"]]
            if s["section"] in ("abstract", "discussion", "conclusion", "front"):
                cands.append({"rule": "R1", "type": "因果措辞超出设计",
                              "conclusion_sentence_id": s["id"],
                              "section": s["section"],
                              "quote": s["text"][:160],
                              "basis": "设计线索为 %s 且无随机/对照线索，此句用因果动词 %s"
                                       % ("/".join(obs), "/".join(h["cues"])),
                              "premise_hint": "核对结果章是否只有相关/组间比较证据"})
    # R2: 讨论/结论句的关键词在结果章零覆盖 → 前提未交付
    for sec in ("discussion", "conclusion"):
        for s in by_sec.get(sec, []):
            toks = key_tokens(s["text"])
            if len(toks) < 3:
                continue
            covered = set()
            for r in results_sents:
                covered |= (toks & key_tokens(r["text"]))
            missing = toks - covered
            if toks and len(missing) / len(toks) >= 0.7:
                cands.append({"rule": "R2", "type": "前提未交付",
                              "conclusion_sentence_id": s["id"],
                              "section": sec,
                              "quote": s["text"][:160],
                              "basis": "该句关键词 %.0f%% 在结果章无覆盖（缺失例：%s）"
                                       % (100 * len(missing) / len(toks),
                                          "、".join(sorted(missing)[:6])),
                              "premise_hint": "回结果章找前提句；找不到即推理跳跃"})
    # R3: 全文无局限性/替代解释讨论（论文级）
    if not rmap["limitation_sentences"]:
        cands.append({"rule": "R3", "type": "替代解释未讨论",
                      "conclusion_sentence_id": None,
                      "section": "paper",
                      "quote": "",
                      "basis": "全文未检出 局限/不足/替代解释/confound/limitation 等表述",
                      "premise_hint": "确认讨论章是否排除主要替代解释；未排除即成立"})
    # R4: 小样本 + 全称结论
    ns = [x["n"] for x in rmap["sample_sizes"]]
    if ns and min(ns) <= 5:
        for sid in rmap["universal_sentences"]:
            s = sents[sid]
            if s["section"] in ("abstract", "discussion", "conclusion"):
                cands.append({"rule": "R4", "type": "小样本全称结论",
                              "conclusion_sentence_id": s["id"],
                              "section": s["section"],
                              "quote": s["text"][:160],
                              "basis": "检出样本量 n=%d，该句用全称表述" % min(ns),
                              "premise_hint": "全称结论需总体代表性论证；否则限缩适用范围"})
    out = {"engine": VERSION,
           "instruction": "机械候选，须回原文定案：成立转 finding（必须同时给"
                          "conclusion_sentence_id 与 premise_sentence_ids 两端"
                          "锚定），不成立记驳回理由，无法确认标待复核。",
           "n_candidates": len(cands), "candidates": cands}
    atomic_write(os.path.join(args.work, "chain_candidates.json"),
                 json.dumps(out, ensure_ascii=False, indent=2))
    print("candidates: R1=%d R2=%d R3=%d R4=%d" % tuple(
        sum(1 for c in cands if c["rule"] == r) for r in ("R1", "R2", "R3", "R4")))
    return 0


def cmd_verify(args):
    spath = os.path.join(args.work, "sentences.jsonl")
    if not os.path.exists(spath):
        eprint("FAIL: sentences.jsonl missing")
        return 3
    sents = {s["id"]: s for s in load_sents(args.work)}
    try:
        findings = json.load(open(args.findings, encoding="utf-8"))
    except Exception as exc:
        eprint("FAIL: cannot parse findings: %s" % exc)
        return 3
    if isinstance(findings, dict):
        findings = findings.get("findings", [])
    problems = []
    for i, f in enumerate(findings, 1):
        fid = f.get("id", "row%d" % i)
        cid = f.get("conclusion_sentence_id")
        if cid not in sents:
            problems.append({"id": fid, "problem": "unknown conclusion_sentence_id: %s" % cid})
            continue
        q = f.get("quote", "")
        if q and q not in sents[cid]["text"] and q.rstrip(".…") not in sents[cid]["text"]:
            problems.append({"id": fid, "problem": "quote not verbatim",
                             "quote_head": q[:60]})
        prem = f.get("premise_sentence_ids")
        if f.get("status") != "待复核" and not prem:
            problems.append({"id": fid,
                             "problem": "推理链 finding 必须给 premise_sentence_ids（前提端锚定）；"
                                        "前提是'无前提'时填空数组并设 status=待复核 或在 basis 说明"})
        for pid in prem or []:
            if pid not in sents:
                problems.append({"id": fid, "problem": "unknown premise sentence_id: %s" % pid})
        if not (f.get("basis") or "").strip():
            problems.append({"id": fid, "problem": "missing basis（推理步骤断裂点必须写明）"})
        sug = f.get("suggestion") or ""
        if len(sug) < 15:
            problems.append({"id": fid, "problem": "suggestion 过短，须落到改哪句/补什么推理环节"})
    atomic_write(os.path.join(args.work, "chain_verify.json"),
                 json.dumps({"engine": VERSION, "n_findings": len(findings),
                             "n_problems": len(problems), "problems": problems},
                            ensure_ascii=False, indent=2))
    if problems:
        eprint("VERIFY FAIL: %d problem(s)" % len(problems))
        return 4
    print("verify ok: %d findings, all two-end anchored" % len(findings))
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
