#!/usr/bin/env python3
"""bench.py — 可验证性引擎：内置合成基准 + 评分器 + 真实案例门禁。

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
多数审查 Skill 只声称"更好"，无法证明。本引擎把证明做成机制：三篇带已知
植入缺陷的合成小论文（p1/p2/p3，p3 为干净对照）+ 确定性评分器。审查者
先用同一套 finding schema 跑基准，得到可复核的召回率/精确率，再跑真实
案例——增益证据与正式结果同构、可复跑。

Subcommands:
  anchor --paper PATH --work DIR         任意论文文本 -> sentences.jsonl
  grade  --bench DIR --paper ID --findings F --runs PATH
                                         对照 key.json 评分并追加运行台账
  verify --work DIR --findings F         真实案例门禁：quote 逐字 + 字段齐全
Exit codes: 0 ok；2 有告警（如召回低于阈值）；3 输入失败；4 verify 违规。
"""
import argparse
import glob
import json
import os
import re
import sys
import time

VERSION = "bench/1.0.0"
RECALL_FLOOR = 0.6  # 基准召回低于此值时 exit 2：提示先修审查协议再跑真实案例

SEC_RX = [
    ("abstract", re.compile(r"^\s*(abstract|摘要)\b[:：]?\s*$", re.I)),
    ("introduction", re.compile(r"^\s*(\d+\.?\s*)?(introduction|引言|绪论)\s*$", re.I)),
    ("methods", re.compile(r"^\s*(\d+\.?\s*)?(materials?\s+and\s+methods?|methods?|methodology|材料与方法|方法)\s*$", re.I)),
    ("results", re.compile(r"^\s*(\d+\.?\s*)?(results?|实验结果|结果)\s*$", re.I)),
    ("discussion", re.compile(r"^\s*(\d+\.?\s*)?(discussion|讨论)\s*$", re.I)),
    ("references", re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I)),
]


def eprint(*a):
    print(*a, file=sys.stderr)


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def anchor_text(text):
    text = re.sub(r"\b(et al|e\.g|i\.e|cf|vs|Fig|Dr|Prof)\.\s",
                  lambda m: m.group(0)[:-2] + "\x04 ", text)
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
                          "section": sec, "text": p.replace("\x04", ".")})
        pos += len(line)
    return sents


def cmd_anchor(args):
    with open(args.paper, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        eprint("FAIL: empty paper text")
        return 3
    os.makedirs(args.work, exist_ok=True)
    sents = anchor_text(text)
    atomic_write(os.path.join(args.work, "sentences.jsonl"),
                 "\n".join(json.dumps(s, ensure_ascii=False) for s in sents) + "\n")
    print("anchored %d sentences" % len(sents))
    return 0


def load_findings(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("findings", d) if isinstance(d, dict) else d


def cmd_grade(args):
    key_p = os.path.join(args.bench, "key.json")
    paper_p = os.path.join(args.bench, "%s.txt" % args.paper)
    if not os.path.exists(key_p) or not os.path.exists(paper_p):
        eprint("FAIL: bench dir must contain key.json and %s.txt" % args.paper)
        return 3
    key = json.load(open(key_p, encoding="utf-8"))
    defects = key.get("papers", {}).get(args.paper, {}).get("defects")
    if defects is None:
        eprint("FAIL: no key for paper %s" % args.paper)
        return 3
    with open(paper_p, encoding="utf-8") as fh:
        paper_text = fh.read()
    try:
        findings = load_findings(args.findings)
    except Exception as exc:
        eprint("FAIL: cannot parse findings: %s" % exc)
        return 3

    # 1) 每条 finding 先做逐字校验（对基准论文原文）
    verbatim_bad = []
    for f in findings:
        q = f.get("quote", "")
        if q and q not in paper_text and q.rstrip(".…") not in paper_text:
            verbatim_bad.append(f.get("id"))

    # 2) 匹配：finding.quote 含 key 的 quote_contains 片段即命中；一对一
    hits, used = {}, set()
    for d in defects:
        frag = d["quote_contains"]
        for i, f in enumerate(findings):
            if i in used:
                continue
            if frag in (f.get("quote") or "") or frag in (f.get("basis") or ""):
                hits[d["defect_id"]] = f.get("id")
                used.add(i)
                break
    missed = [d["defect_id"] for d in defects if d["defect_id"] not in hits]
    false_alarms = [f.get("id") for i, f in enumerate(findings) if i not in used]
    precision = (len(hits) / len(findings)) if findings else (1.0 if not defects else 0.0)
    recall = len(hits) / len(defects) if defects else (1.0 if not findings else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    grade = {
        "engine": VERSION, "paper": args.paper, "ts": int(time.time()),
        "n_defects": len(defects), "n_findings": len(findings),
        "hits": hits, "missed": missed, "false_alarms": false_alarms,
        "verbatim_violations": verbatim_bad,
        "precision": round(precision, 4), "recall": round(recall, 4),
        "f1": round(f1, 4),
    }
    if args.paper == "p3" and findings:
        grade["note"] = "p3 为干净对照：任何 finding 都计 false_alarm，考察误报率"
    out_p = os.path.join(os.path.dirname(args.runs) or ".",
                         "grade_%s.json" % args.paper)
    atomic_write(out_p, json.dumps(grade, ensure_ascii=False, indent=2))
    # 3) 运行台账：同一 paper 多次运行比较 STABLE/DRIFT
    runs = []
    if os.path.exists(args.runs):
        with open(args.runs, encoding="utf-8") as fh:
            runs = [json.loads(l) for l in fh if l.strip()]
    prev = [r for r in runs if r.get("paper") == args.paper]
    stability = None
    if prev:
        last = prev[-1]
        stability = "STABLE" if (last["hits"] == hits and last["false_alarms"] == false_alarms) else "DRIFT"
    grade["stability_vs_previous"] = stability
    atomic_write(out_p, json.dumps(grade, ensure_ascii=False, indent=2))
    with open(args.runs, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"paper": args.paper, "hits": hits,
                             "false_alarms": false_alarms, "recall": recall,
                             "precision": precision, "ts": grade["ts"]},
                            ensure_ascii=False) + "\n")
    print("grade %s: recall=%.2f precision=%.2f f1=%.2f hits=%d missed=%d false_alarms=%d verbatim_bad=%d%s"
          % (args.paper, recall, precision, f1, len(hits), len(missed),
             len(false_alarms), len(verbatim_bad),
             (" stability=" + stability) if stability else ""))
    if verbatim_bad:
        eprint("WARN: %d finding(s) with non-verbatim quote" % len(verbatim_bad))
    if defects and recall < RECALL_FLOOR:
        eprint("WARN: recall %.2f below floor %.2f — 先修审查协议再跑真实案例"
               % (recall, RECALL_FLOOR))
        return 2
    return 0


def cmd_verify(args):
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
        findings = load_findings(args.findings)
    except Exception as exc:
        eprint("FAIL: cannot parse findings: %s" % exc)
        return 3
    problems = []
    REQUIRED = ("id", "type", "severity", "sentence_id", "quote", "basis", "suggestion")
    for i, f in enumerate(findings, 1):
        fid = f.get("id", "row%d" % i)
        for k in REQUIRED:
            if k not in f:
                problems.append({"id": fid, "problem": "missing field %s" % k})
        sid = f.get("sentence_id")
        if sid and sid not in sents:
            problems.append({"id": fid, "problem": "unknown sentence_id: %s" % sid})
        elif sid:
            q = f.get("quote", "")
            if q and q not in sents[sid]["text"] and q.rstrip(".…") not in sents[sid]["text"]:
                problems.append({"id": fid, "problem": "quote not verbatim",
                                 "quote_head": q[:60]})
        if f.get("severity") not in ("critical", "major", "minor", "info"):
            problems.append({"id": fid, "problem": "severity 须为 critical/major/minor/info"})
        if len(f.get("suggestion") or "") < 15:
            problems.append({"id": fid, "problem": "suggestion 过短（空话门禁）"})
    atomic_write(os.path.join(args.work, "bench_verify.json"),
                 json.dumps({"engine": VERSION, "n_findings": len(findings),
                             "n_problems": len(problems), "problems": problems},
                            ensure_ascii=False, indent=2))
    if problems:
        eprint("VERIFY FAIL: %d problem(s)" % len(problems))
        return 4
    print("verify ok: %d findings" % len(findings))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("anchor")
    p.add_argument("--paper", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_anchor)
    p = sub.add_parser("grade")
    p.add_argument("--bench", required=True)
    p.add_argument("--paper", required=True)
    p.add_argument("--findings", required=True)
    p.add_argument("--runs", required=True)
    p.set_defaults(fn=cmd_grade)
    p = sub.add_parser("verify")
    p.add_argument("--work", required=True)
    p.add_argument("--findings", required=True)
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
