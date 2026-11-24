#!/usr/bin/env python3
"""xcheck.py — 结构层引擎：跨章节一致性的确定性核查。

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
长文审查最容易漏的是跨章节矛盾：摘要数字与结果对不上、引言承诺在结果章
没交付、图表引用与标题不配对、缩写通篇未定义。本引擎把这四类做成确定性
候选（X1–X4），每条候选锚定两侧句子（如摘要句 ↔ 结果句），审查者定案。

Subcommands:
  scan    --paper PATH --work DIR     -> sentences.jsonl + structure_map.json
  xcheck  --work DIR                  -> xcheck_candidates.json（X1–X4）
  verify  --work DIR --findings F     门禁：quote 逐字 + 跨章条必须双侧锚定
Exit codes: 0 ok；2 告警；3 输入失败；4 verify 违规。stderr 显式报错。
"""
import argparse
import json
import os
import re
import sys

VERSION = "xcheck/1.0.0"

SEC_RX = [
    ("abstract", re.compile(r"^\s*(abstract|摘要)\b[:：]?\s*$", re.I)),
    ("introduction", re.compile(r"^\s*(\d+\.?\s*)?(introduction|引言|绪论)\s*$", re.I)),
    ("methods", re.compile(r"^\s*(\d+\.?\s*)?(materials?\s+and\s+methods?|methods?|methodology|材料与方法|实验方法|方法)\s*$", re.I)),
    ("results", re.compile(r"^\s*(\d+\.?\s*)?(results?(\s+and\s+discussion)?|实验结果|结果与分析|结果)\s*$", re.I)),
    ("discussion", re.compile(r"^\s*(\d+\.?\s*)?(discussion|讨论)\s*$", re.I)),
    ("conclusion", re.compile(r"^\s*(\d+\.?\s*)?(conclusions?|结论)\s*$", re.I)),
    ("references", re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I)),
]

NUM_RX = re.compile(r"\d+(?:\.\d+)?(?:\s*(?:%|％|倍|周次|小时|例|个|分|mm|cm|μm|nm|mpa|kpa|h|ms|s))?")
PROMISE_RX = re.compile(
    r"(本文(将|旨在|拟|目标)|本研究(将|旨在|拟)|我们(将|旨在)|拟解决|"
    r"we (aim|aimed|will|set out)|this (paper|study) (aims|aimed|seeks))", re.I)
FIGREF_RX = re.compile(r"(图|表|figure|fig\.?|table)\s*(\d+)", re.I)
CAPTION_RX = re.compile(r"^\s*(图|表|figure|fig\.?|table)\s*(\d+)[\s:：.．]", re.I)
ACR_RX = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
ACR_DEF_RX = re.compile(r"([A-Z][A-Z0-9]{1,7})\s*[（(]|[（(][^)）]*[)）]\s*([A-Z][A-Z0-9]{1,7})|"
                        r"(?:（|\()([A-Z][A-Z0-9]{1,7})(?:）|\))")
STOP_ACR = {"A", "I", "OK", "S", "N", "P", "T", "R", "D", "E", "C", "B", "F",
            "H", "K", "L", "M", "G", "W", "V", "U", "X", "Y", "Z"}


def eprint(*a):
    print(*a, file=sys.stderr)


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def anchor(text):
    text = re.sub(r"\b(et al|e\.g|i\.e|cf|vs|Fig|Dr|Prof)\.\s",
                  lambda m: m.group(0)[:-2] + "\x03 ", text)
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
                          "section": sec, "text": p.replace("\x03", ".")})
        pos += len(line)
    return sents, marks


def load_sents(work):
    with open(os.path.join(work, "sentences.jsonl"), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


def norm_num(s):
    return re.sub(r"\s+", "", s).replace("％", "%")


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
    abs_nums, body_nums = [], []
    for s in sents:
        for m in NUM_RX.finditer(s["text"]):
            v = norm_num(m.group(0))
            if not v or not any(ch.isdigit() for ch in v):
                continue
            rec = {"value": v, "sentence_id": s["id"], "section": s["section"]}
            if s["section"] in ("abstract", "front"):
                abs_nums.append(rec)
            else:
                body_nums.append(rec)
    promises = [{"sentence_id": s["id"], "section": s["section"],
                 "text": s["text"][:160]}
                for s in sents if PROMISE_RX.search(s["text"])
                and s["section"] in ("introduction", "abstract", "front")]
    captions, refs = {}, []
    for s in sents:
        m = CAPTION_RX.match(s["text"])
        if m:
            captions[m.group(1).lower() + m.group(2)] = s["id"]
        for m in FIGREF_RX.finditer(s["text"]):
            refs.append({"key": m.group(1).lower() + m.group(2),
                         "sentence_id": s["id"],
                         "in_caption": bool(CAPTION_RX.match(s["text"]))})
    acr_count, acr_first = {}, {}
    defined = set()
    for m in ACR_DEF_RX.finditer(text):
        for g in m.groups():
            if g:
                defined.add(g)
    for s in sents:
        for m in ACR_RX.finditer(s["text"]):
            t = m.group(0)
            if t in STOP_ACR or len(t) < 2:
                continue
            acr_count[t] = acr_count.get(t, 0) + 1
            acr_first.setdefault(t, s["id"])
    smap = {"engine": VERSION, "n_sentences": len(sents), "sections": marks,
            "abstract_numbers": abs_nums, "body_numbers": body_nums,
            "promises": promises, "captions": captions, "figure_refs": refs,
            "acronyms": [{"token": t, "count": c, "first_sentence": acr_first[t],
                          "defined": t in defined}
                         for t, c in sorted(acr_count.items()) if c >= 2]}
    atomic_write(os.path.join(args.work, "structure_map.json"),
                 json.dumps(smap, ensure_ascii=False, indent=2))
    print("scan: %d sentences; abs_nums=%d body_nums=%d promises=%d captions=%d refs=%d acronyms=%d"
          % (len(sents), len(abs_nums), len(body_nums), len(promises),
             len(captions), len(refs), len(smap["acronyms"])))
    return 0


def cmd_xcheck(args):
    spath = os.path.join(args.work, "structure_map.json")
    if not os.path.exists(spath):
        eprint("FAIL: run scan first")
        return 3
    smap = json.load(open(spath, encoding="utf-8"))
    sents = {s["id"]: s for s in load_sents(args.work)}
    cands = []
    body_vals = {b["value"] for b in smap["body_numbers"]}
    # X1: 摘要数字在正文找不到同值（按句聚合）
    miss_by_sent = {}
    seen = set()
    for a in smap["abstract_numbers"]:
        if a["value"] in seen or len(a["value"].rstrip("%")) < 2:
            continue
        seen.add(a["value"])
        if a["value"] not in body_vals:
            miss_by_sent.setdefault(a["sentence_id"], []).append(a["value"])
    for sid, vals in miss_by_sent.items():
        cands.append({"rule": "X1", "type": "摘要—正文数值不一致",
                      "side_a": sid, "side_b": None,
                      "quote": sents[sid]["text"][:160],
                      "basis": "摘要数值 %s 在正文（方法/结果/讨论）未检出同值"
                               % "、".join(vals),
                      "hint": "回正文找该指标的实际数值句作为 side_b 后定案"})
    # X2: 引言承诺在结果/讨论章零关键词覆盖
    results_sents = [s for s in sents.values()
                     if s["section"] in ("results", "discussion")]
    HAN = re.compile(r"[一-鿿]+")
    ENG = re.compile(r"[A-Za-z]{4,}")

    STOPCH = set("的将并与回分答析此在也来被评评估其")
    def toks(t):
        out = set()
        for chunk in HAN.findall(t):
            for i in range(len(chunk) - 1):
                g = chunk[i:i + 2]
                if g not in ("本文", "我们", "本研", "研究", "旨在", "目标",
                             "解决", "回答", "分析") \
                        and g[0] not in STOPCH and g[1] not in STOPCH:
                    out.add(g)
        for w in ENG.findall(t.lower()):
            if w not in ("this", "paper", "study", "aims", "aimed", "will"):
                out.add(w)
        return out

    res_toks = set()
    for r in results_sents:
        res_toks |= toks(r["text"])
    for p in smap["promises"]:
        pt = toks(sents[p["sentence_id"]]["text"])
        if len(pt) < 3:
            continue
        missing = pt - res_toks
        if len(missing) / len(pt) >= 0.7:
            cands.append({"rule": "X2", "type": "引言承诺未交付",
                          "side_a": p["sentence_id"], "side_b": None,
                          "quote": sents[p["sentence_id"]]["text"][:160],
                          "basis": "承诺句关键词 %.0f%% 在结果/讨论章零覆盖（缺失例：%s）"
                                   % (100 * len(missing) / len(pt),
                                      "、".join(sorted(missing)[:6])),
                          "hint": "通读结果/讨论确认是否真的未交付；交付处句子作为 side_b"})
    # X3: 图表引用与标题不配对（双向）
    cap_keys = set(smap["captions"].keys())
    ref_keys = {r["key"] for r in smap["figure_refs"] if not r["in_caption"]}
    for r in smap["figure_refs"]:
        if not r["in_caption"] and r["key"] not in cap_keys:
            cands.append({"rule": "X3", "type": "引用无标题图表",
                          "side_a": r["sentence_id"], "side_b": None,
                          "quote": sents[r["sentence_id"]]["text"][:160],
                          "basis": "正文引用 %s 但全文无该图表标题" % r["key"],
                          "hint": "补图表或修编号"})
    for k, sid in smap["captions"].items():
        if k not in ref_keys:
            cands.append({"rule": "X3", "type": "图表从未被正文引用",
                          "side_a": sid, "side_b": None,
                          "quote": sents[sid]["text"][:160],
                          "basis": "%s 有标题但正文从未引用" % k,
                          "hint": "在正文补引用或删除该图表"})
    # X4: 高频缩写未定义
    for a in smap["acronyms"]:
        if not a["defined"] and a["count"] >= 3:
            cands.append({"rule": "X4", "type": "缩写未定义",
                          "side_a": a["first_sentence"], "side_b": None,
                          "quote": sents[a["first_sentence"]]["text"][:160],
                          "basis": "缩写 %s 出现 %d 次，全文未见括号定义"
                                   % (a["token"], a["count"]),
                          "hint": "首次出现处补全称定义"})
    # 去重
    out_c, seenk = [], set()
    for c in cands:
        k = (c["rule"], c["type"], c["side_a"], c["basis"][:30])
        if k not in seenk:
            seenk.add(k)
            out_c.append(c)
    atomic_write(os.path.join(args.work, "xcheck_candidates.json"),
                 json.dumps({"engine": VERSION,
                             "instruction": "机械候选；定案须回原文两侧核对，"
                                            "成立转 finding（side_a/side_b 双锚定），"
                                            "不成立记驳回理由，无法确认标待复核。",
                             "n_candidates": len(out_c), "candidates": out_c},
                            ensure_ascii=False, indent=2))
    print("candidates: X1=%d X2=%d X3=%d X4=%d" % tuple(
        sum(1 for c in out_c if c["rule"] == r) for r in ("X1", "X2", "X3", "X4")))
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
        for side in ("side_a", "side_b"):
            sid = f.get(side)
            if side == "side_a" and sid not in sents:
                problems.append({"id": fid, "problem": "unknown side_a: %s" % sid})
                continue
            if sid is None:
                basis = f.get("basis") or ""
                if f.get("status") != "待复核" and side == "side_b" \
                        and f.get("type") in ("摘要—正文数值不一致", "引言承诺未交付") \
                        and not any(w in basis for w in ("未交付", "未检出", "无对应")):
                    problems.append({"id": fid,
                                     "problem": "跨章 finding 定案必须给 side_b（另一侧句子）；"
                                                "另一侧确认不存在时 basis 须写明'未交付/未检出'，"
                                                "无法确认设 status=待复核"})
                continue
            if sid not in sents:
                problems.append({"id": fid, "problem": "unknown %s: %s" % (side, sid)})
        q = f.get("quote", "")
        sa = f.get("side_a")
        if q and sa in sents and q not in sents[sa]["text"] \
                and q.rstrip(".…") not in sents[sa]["text"]:
            problems.append({"id": fid, "problem": "quote not verbatim",
                             "quote_head": q[:60]})
        if not (f.get("basis") or "").strip():
            problems.append({"id": fid, "problem": "missing basis"})
        if len(f.get("suggestion") or "") < 15:
            problems.append({"id": fid, "problem": "suggestion 过短，须落到改哪一侧哪一句"})
    atomic_write(os.path.join(args.work, "xcheck_verify.json"),
                 json.dumps({"engine": VERSION, "n_findings": len(findings),
                             "n_problems": len(problems), "problems": problems},
                            ensure_ascii=False, indent=2))
    if problems:
        eprint("VERIFY FAIL: %d problem(s)" % len(problems))
        return 4
    print("verify ok: %d findings, both sides anchored" % len(findings))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--paper", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("xcheck")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_xcheck)
    p = sub.add_parser("verify")
    p.add_argument("--work", required=True)
    p.add_argument("--findings", required=True)
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
