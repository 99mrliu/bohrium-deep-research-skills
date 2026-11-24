#!/usr/bin/env python3
"""claimledger.py — 论点层引擎：句子锚定 + 主张清单骨架 + 清单门禁。

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
本引擎不做审查判断；它把论文锚定成可逐句核对的台账，把"哪些句子看起来像
主张"这一机械部分做成确定性候选，并在交付前对填好的主张清单做门禁校验
（quote 逐字、归因类型合法、每条都有结论或待复核），从机制上防止三类高频
失败：定位只到章节、凭印象引用、把转述/假设误当作者主张。

Subcommands:
  anchor    --paper PATH --work DIR     论文文本 -> sentences.jsonl + sections.json
  scaffold  --work DIR                  -> claims_skeleton.json（主张候选+归因提示）
  lint      --work DIR --claims PATH    校验填好的 claims.json；exit 4 = 有违规

Exit codes: 0 ok；2 有告警（可继续，须读 warnings）；3 输入失败；4 lint 违规。
所有失败向 stderr 打印显式原因，不静默。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

VERSION = "claimledger/1.0.0"

SECTION_RES = [
    ("abstract", re.compile(r"^\s*(abstract|摘要)\b[:：]?\s*$", re.I)),
    ("introduction", re.compile(r"^\s*(\d+\.?\s*)?(introduction|引言|绪论)\s*$", re.I)),
    ("methods", re.compile(r"^\s*(\d+\.?\s*)?(materials?\s+and\s+methods?|methods?|methodology|材料与方法|实验方法|方法)\s*$", re.I)),
    ("results", re.compile(r"^\s*(\d+\.?\s*)?(results?(\s+and\s+discussion)?|实验结果|结果与分析|结果)\s*$", re.I)),
    ("discussion", re.compile(r"^\s*(\d+\.?\s*)?(discussion|讨论)\s*$", re.I)),
    ("conclusion", re.compile(r"^\s*(\d+\.?\s*)?(conclusions?|结论)\s*$", re.I)),
    ("references", re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I)),
]

# 主张线索词：句子含这些谓词时列入主张候选。仅候选，不归因定案。
CLAIM_CUES = [
    "表明", "证明", "证实", "显示", "揭示", "导致", "促进", "抑制", "显著提高",
    "显著降低", "优于", "首次", "本文提出", "我们提出", "我们发现", "本研究",
    "show", "shows", "showed", "demonstrate", "demonstrates", "demonstrated",
    "reveal", "reveals", "confirm", "confirms", "establish", "establishes",
    "cause", "causes", "improve", "improves", "outperform", "outperforms",
    "we propose", "we found", "we conclude", "our results",
    # 转述/假设动词同样入册：清单的目的之一是先把它们请进来再正确归因，
    # 防止审查时把他人观点或假设情形误当作者主张。
    "认为", "指出", "reported", "argued", "claimed", "有望",
]
CITATION_MARK = re.compile(r"(\[\d+([\,\-\s]\d+)*\]|\([A-Z][A-Za-z\-]+(\s+et\s+al\.?)?,?\s+\d{4}[a-z]?\)|等\s*\[\d+\]|等（\d{4}）| et al\.)")
HYPOTHESIS_CUES = ["假设", "假定", "若", "如果成立", "有望", "可能", "或将",
                   "hypothes", "assume", "assuming", "suppose", "if ", "would ",
                   "we expect", "potentially", "may ", "might "]
ATTRIBUTION_CUES = ["报道", "指出", "认为", "提出", "发现", "reported", "argued",
                    "proposed", "found that", "showed that", "according to"]

ATTRIBUTION_TYPES = ["author_claim", "cited_view", "hypothesis", "control_or_design"]
VERDICTS = ["supported", "insufficient", "unsupported", "pending"]


def eprint(*a):
    print(*a, file=sys.stderr)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


_ABBR_RX = re.compile(
    r"\b(et al|e\.g|i\.e|cf|vs|Fig|Figs|Dr|Prof|Sr|Jr|Inc|Ltd|approx)\.\s")
_SENT_SPLIT_RX = re.compile(r"(?<=[。！？!?；;])\s*|(?<=[.])\s+(?=[A-Z0-9（(])")


def split_sentences(text):
    """按行保留偏移切句：先按行，再按句末标点。返回 [(offset, raw_text)]。
    et al. / e.g. / Fig. 等缩写句点用占位符保护，切完还原，保证存原文。"""
    out = []
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped:
            base = pos + (len(line) - len(line.lstrip()))
            protected = _ABBR_RX.sub(lambda m: m.group(0)[:-2] + "\x00 ", stripped)
            inner = 0
            for p in _SENT_SPLIT_RX.split(protected):
                p = p.strip()
                if not p:
                    continue
                idx = protected.find(p, inner)
                inner = idx + len(p)
                out.append((base + idx, p.replace("\x00", ".")))
        pos += len(line)
    return out


def detect_sections(text):
    """返回 (sections 列表, line->section 映射用的区间)。"""
    marks = []
    pos = 0
    for line in text.splitlines(keepends=True):
        for name, rx in SECTION_RES:
            if rx.match(line.strip()):
                marks.append({"section": name, "offset": pos,
                              "title": line.strip()})
                break
        pos += len(line)
    return marks


def section_of(offset, marks):
    cur = "front"
    for m in marks:
        if m["offset"] <= offset:
            cur = m["section"]
        else:
            break
    return cur


def cmd_anchor(args):
    text = read_text(args.paper)
    if not text.strip():
        eprint("FAIL: paper text is empty: %s" % args.paper)
        return 3
    os.makedirs(args.work, exist_ok=True)
    marks = detect_sections(text)
    sents = split_sentences(text)
    lines = []
    for i, (off, s) in enumerate(sents, 1):
        rec = {"id": "S%04d" % i, "offset": off,
               "section": section_of(off, marks), "text": s}
        lines.append(json.dumps(rec, ensure_ascii=False))
    atomic_write(os.path.join(args.work, "sentences.jsonl"), "\n".join(lines) + "\n")
    atomic_write(os.path.join(args.work, "sections.json"),
                 json.dumps({"sections": marks, "n_sentences": len(sents),
                             "engine": VERSION}, ensure_ascii=False, indent=2))
    found = {m["section"] for m in marks}
    missing = [s for s in ("abstract", "introduction", "results") if s not in found]
    if missing:
        eprint("WARN: canonical sections not detected: %s "
               "(section 字段退回 front/实际检测值；若属解析问题请在结果中标注)"
               % ",".join(missing))
        return 2
    print("anchored %d sentences, %d section marks" % (len(sents), len(marks)))
    return 0


def guess_attribution(sent):
    """机械归因提示：只给 hint，定案由审查者做。"""
    if CITATION_MARK.search(sent) and any(c in sent for c in ATTRIBUTION_CUES):
        return "cited_view?"
    low = sent.lower()
    if any(c in sent for c in HYPOTHESIS_CUES[:7]) or any(c in low for c in HYPOTHESIS_CUES[7:]):
        return "hypothesis?"
    return "author_claim?"


def cmd_scaffold(args):
    path = os.path.join(args.work, "sentences.jsonl")
    if not os.path.exists(path):
        eprint("FAIL: run anchor first (sentences.jsonl missing)")
        return 3
    claims = []
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            s = rec["text"]
            low = s.lower()
            if any(c in s for c in CLAIM_CUES[:21]) or any(c in low for c in CLAIM_CUES[21:]):
                n += 1
                claims.append({
                    "claim_id": "C%02d" % n,
                    "sentence_id": rec["id"],
                    "section": rec["section"],
                    "quote": s if len(s) <= 120 else s[:117] + "...",
                    "attribution_hint": guess_attribution(s),
                    "attribution": None, "verdict": None,
                    "evidence_sentence_ids": [], "note": ""})
    out = {"engine": VERSION,
           "instruction": "逐条定案：attribution 四选一(author_claim/cited_view/"
                          "hypothesis/control_or_design)；verdict 四选一(supported/"
                          "insufficient/unsupported/pending)；evidence_sentence_ids "
                          "填支撑句 id；pending 必须在 note 写清缺什么。hint 仅供参"
                          "考，允许推翻。无 cue 但实属主张的句子请自行补条。",
           "claims": claims}
    atomic_write(os.path.join(args.work, "claims_skeleton.json"),
                 json.dumps(out, ensure_ascii=False, indent=2))
    print("scaffold: %d claim candidates" % len(claims))
    return 0


def cmd_lint(args):
    spath = os.path.join(args.work, "sentences.jsonl")
    if not os.path.exists(spath):
        eprint("FAIL: sentences.jsonl missing; run anchor first")
        return 3
    sents = {}
    with open(spath, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            sents[r["id"]] = r
    try:
        claims = json.loads(read_text(args.claims))
    except Exception as exc:
        eprint("FAIL: cannot parse claims file %s: %s" % (args.claims, exc))
        return 3
    if isinstance(claims, dict):
        claims = claims.get("claims", [])
    problems = []
    seen = set()
    for i, c in enumerate(claims, 1):
        cid = c.get("claim_id", "row%d" % i)
        if cid in seen:
            problems.append({"claim_id": cid, "problem": "duplicate claim_id"})
        seen.add(cid)
        sid = c.get("sentence_id")
        if sid not in sents:
            problems.append({"claim_id": cid, "problem": "unknown sentence_id: %s" % sid})
            continue
        q = c.get("quote", "")
        if q and q not in sents[sid]["text"] and q.rstrip(".…") not in sents[sid]["text"]:
            problems.append({"claim_id": cid, "sentence_id": sid,
                             "problem": "quote is not a verbatim substring of the sentence",
                             "quote_head": q[:60]})
        at = c.get("attribution")
        if at not in ATTRIBUTION_TYPES:
            problems.append({"claim_id": cid, "problem": "attribution must be one of %s, got %r"
                             % (ATTRIBUTION_TYPES, at)})
        vd = c.get("verdict")
        if vd not in VERDICTS:
            problems.append({"claim_id": cid, "problem": "verdict must be one of %s, got %r"
                             % (VERDICTS, vd)})
        if vd == "pending" and not (c.get("note") or "").strip():
            problems.append({"claim_id": cid, "problem": "pending without note explaining what is missing"})
        if vd in ("supported", "insufficient", "unsupported") and at == "author_claim" \
                and not c.get("evidence_sentence_ids"):
            problems.append({"claim_id": cid,
                             "problem": "author_claim verdict requires evidence_sentence_ids (empty only allowed for pending)"})
        for eid in c.get("evidence_sentence_ids", []):
            if eid not in sents:
                problems.append({"claim_id": cid, "problem": "unknown evidence sentence_id: %s" % eid})
        # 反误报：被机械提示为转述/假设却仍按作者主张定 unsupported 的，要求 note 说明
        hint = c.get("attribution_hint", "")
        if hint in ("cited_view?", "hypothesis?") and at == "author_claim" \
                and vd == "unsupported" and not (c.get("note") or "").strip():
            problems.append({"claim_id": cid,
                             "problem": "sentence looks like %s but was judged as author_claim/unsupported without a note; "
                                        "转述他人观点或假设情形不得计为作者缺陷" % hint})
    atomic_write(os.path.join(args.work, "ledger_lint.json"),
                 json.dumps({"engine": VERSION, "n_claims": len(claims),
                             "n_problems": len(problems), "problems": problems},
                            ensure_ascii=False, indent=2))
    if problems:
        eprint("LINT FAIL: %d problem(s); see ledger_lint.json" % len(problems))
        return 4
    print("lint ok: %d claims, all verbatim/attributed/decided" % len(claims))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("anchor")
    p.add_argument("--paper", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_anchor)
    p = sub.add_parser("scaffold")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_scaffold)
    p = sub.add_parser("lint")
    p.add_argument("--work", required=True)
    p.add_argument("--claims", required=True)
    p.set_defaults(fn=cmd_lint)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
