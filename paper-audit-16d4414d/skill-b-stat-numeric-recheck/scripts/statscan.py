#!/usr/bin/env python3
"""statscan.py — 统计与数值一致性的确定性机审引擎 for paper-audit skills.

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
Recomputes every numeric claim that can be recomputed from the text itself
and emits CANDIDATES (never verdicts); the agent confirms each candidate by
reading the sentence in context before upgrading it to a finding.

Subcommands:
  scan    --input PATH --work DIR   paper text -> sentences.jsonl + mentions.jsonl
  check   --work DIR                mentions -> candidates.json (rules C1..C6)
  verify  --work DIR --findings F   quote gate: every finding quote must be a
                                    verbatim substring of its sentence

Exit codes: scan/check 0 ok (even with zero candidates), 3 fatal input error;
verify 0 pass, 4 violations. All failures explain themselves on stderr.
"""
import argparse
import hashlib
import json
import os
import re
import sys

# ------------------------------------------------------------------ shared
SENT = re.compile(r".*?(?:[。！？；;!?]+|(?<!\bal)\.+(?!\d)|\n|$)")

SECTION_HEADS = [
    ("abstract", re.compile(r"^\s*(abstract|摘要)\s*$", re.I)),
    ("introduction", re.compile(r"^\s*(\d+\.?\s+)?(introduction|引言|绪论)\s*$", re.I)),
    ("methods", re.compile(r"^\s*(\d+\.?\s+)?(materials?\s+and\s+methods|methods?|methodology|方法|材料与方法)\s*$", re.I)),
    ("results", re.compile(r"^\s*(\d+\.?\s+)?(results?|结果)\s*$", re.I)),
    ("discussion", re.compile(r"^\s*(\d+\.?\s+)?(discussion|讨论)\s*$", re.I)),
    ("references", re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I)),
]

# General signed decimal so impossible values (p>1, p<0) are captured and
# flagged by C4 instead of being silently truncated by a restrictive pattern.
PVAL = re.compile(r"\bp\s*([<>=≤≥])\s*(-?\d+(?:\.\d+)?)", re.I)
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)")
FRACTION = re.compile(r"\(\s*(\d+)\s*/\s*(\d+)\s*\)")
CI = re.compile(r"(\d+(?:\.\d+)?)\s*[^\d\n]{0,40}?\(\s*(?:95\s*%\s*)?CI[,:]?\s*"
                r"(-?\d+(?:\.\d+)?)\s*(?:[-–—,;]|to)\s*(-?\d+(?:\.\d+)?)\s*\)", re.I)
MEANSD = re.compile(r"(-?\d+(?:\.\d+)?)\s*±\s*(-?\d+(?:\.\d+)?)")
NUMUNIT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(cm|mm|kg|g|mg|mL|L|h|hours?|days?|weeks?|°C|bp|kDa)\b")
VS = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:vs\.?|versus|compared\s+(?:to|with))\s*(-?\d+(?:\.\d+)?)", re.I)

SIG_POS = re.compile(r"\b(statistically\s+)?significant\b", re.I)
SIG_NEG = re.compile(r"\b(not|no|non[- ]?significant|failed to reach)\b", re.I)
GUARD_DEF = re.compile(r"\b(threshold|considered|defined|cutoff|criterion|level of significance|was set at)\b", re.I)
HIGHER = re.compile(r"\b(higher|greater|larger|increased|elevated|longer)\b", re.I)
LOWER = re.compile(r"\b(lower|smaller|reduced|decreased|shorter|fewer)\b", re.I)


def eprint(*a):
    print(*a, file=sys.stderr)


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def load_sentences(work):
    path = os.path.join(work, "sentences.jsonl")
    sents = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            sents.append(json.loads(ln))
    return sents


# -------------------------------------------------------------------- scan
def cmd_scan(args):
    if not os.path.isfile(args.input):
        eprint("FATAL: input not found: %s" % args.input)
        return 3
    os.makedirs(args.work, exist_ok=True)
    with open(args.input, encoding="utf-8") as fh:
        text = fh.read()

    raw_lines = text.split("\n")
    heads = []
    for ln_no, ln in enumerate(raw_lines):
        for name, pat in SECTION_HEADS:
            if pat.match(ln):
                heads.append((name, ln_no))

    def section_of(ln_no):
        cur = "front_matter"
        for name, at in heads:
            if ln_no >= at:
                cur = name
        return cur

    # Join wrapped lines into a flow so sentences spanning line breaks stay
    # whole; remember each line's start offset in the joined text so every
    # sentence still maps back to its source line and section.
    joined = " ".join(raw_lines)
    line_starts = []
    pos = 0
    for ln in raw_lines:
        line_starts.append(pos)
        pos += len(ln) + 1

    import bisect
    sents, mentions = [], []
    idx = 0
    for m in SENT.finditer(joined):
        s = m.group(0).strip()
        if len(s) < 4:
            continue
        idx += 1
        sid = "S%04d" % idx
        ln_no = bisect.bisect_right(line_starts, m.start())  # 1-based line
        sents.append({"id": sid, "line": ln_no,
                      "section": section_of(ln_no - 1), "text": s})

        def add(kind, value, extra=None):
            r = {"sentence_id": sid, "kind": kind, "value": value}
            if extra:
                r.update(extra)
            mentions.append(r)
        for mm in PVAL.finditer(s):
            add("pvalue", float(mm.group(2)), {"op": mm.group(1)})
        for mm in PERCENT.finditer(s):
            add("percent", float(mm.group(1)))
        for mm in FRACTION.finditer(s):
            add("fraction", [int(mm.group(1)), int(mm.group(2))])
        for mm in CI.finditer(s):
            add("ci", [float(mm.group(1)), float(mm.group(2)), float(mm.group(3))])
        for mm in MEANSD.finditer(s):
            add("meansd", [float(mm.group(1)), float(mm.group(2))])
        for mm in NUMUNIT.finditer(s):
            add("numunit", [float(mm.group(1)), mm.group(2)])
        if VS.search(s):
            mm = VS.search(s)
            add("vs_pair", [float(mm.group(1)), float(mm.group(2))])

    atomic_write(os.path.join(args.work, "sentences.jsonl"),
                 "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sents))
    atomic_write(os.path.join(args.work, "mentions.jsonl"),
                 "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in mentions))
    print(json.dumps({"status": "ok", "sentences": len(sents),
                      "mentions": len(mentions)}, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------- check
def cmd_check(args):
    try:
        sents = load_sentences(args.work)
    except OSError:
        eprint("FATAL: sentences.jsonl missing in %s; run scan first" % args.work)
        return 3
    mentions = {}
    with open(os.path.join(args.work, "mentions.jsonl"), encoding="utf-8") as fh:
        for ln in fh:
            r = json.loads(ln)
            mentions.setdefault(r["sentence_id"], []).append(r)

    cands = []

    def add(rule, sent, detail, severity_hint):
        cands.append({
            "rule": rule,
            "sentence_id": sent["id"],
            "section": sent["section"],
            "quote": sent["text"],
            "deterministic_detail": detail,
            "severity_hint": severity_hint,
            "agent_must_confirm": True,
        })

    for s in sents:
        t = s["text"]
        ms = mentions.get(s["id"], [])
        kinds = {m["kind"] for m in ms}

        # C1 p-value vs significance wording
        pv = [m for m in ms if m["kind"] == "pvalue"]
        if pv and SIG_POS.search(t) and not GUARD_DEF.search(t):
            neg = bool(SIG_NEG.search(t))
            for m in pv:
                v, op = m["value"], m["op"]
                sig_by_value = (v < 0.05) if op in ("<", "=", "≤") else (v >= 0.05)
                if op == ">" :
                    sig_by_value = False
                if sig_by_value and neg:
                    add("C1_pvalue_wording", s,
                        "p %s %s 按 0.05 阈值不显著，但措辞含显著性表述且带否定"
                        % (op, v), "major")
                elif not sig_by_value and not neg and SIG_POS.search(t):
                    add("C1_pvalue_wording", s,
                        "p %s %s 按 0.05 阈值不显著，但句子声称 significant"
                        % (op, v), "major")

        # C2 percent vs fraction
        pcs = [m for m in ms if m["kind"] == "percent"]
        frs = [m for m in ms if m["kind"] == "fraction" and m["value"][1] > 0]
        for p in pcs:
            for f in frs:
                a, b = f["value"]
                recomputed = 100.0 * a / b
                if abs(recomputed - p["value"]) > 1.0:
                    add("C2_percent_fraction", s,
                        "句内 %.1f%% 与 (%d/%d)=%.1f%% 不符（容差 ±1.0pp）"
                        % (p["value"], a, b, recomputed), "major")

        # C3 CI coherence
        for m in [m for m in ms if m["kind"] == "ci"]:
            est, lo, hi = m["value"]
            if lo > hi:
                add("C3_ci_inverted", s, "CI 下限 %.3g > 上限 %.3g" % (lo, hi), "major")
            elif not (lo <= est <= hi):
                add("C3_ci_point_outside", s,
                    "点估计 %.3g 落在 CI [%.3g, %.3g] 之外" % (est, lo, hi), "major")
            else:
                half = (hi - lo) / 2.0
                if half > 0 and abs((est - lo) - (hi - est)) > 0.25 * half:
                    add("C3_ci_asymmetric", s,
                        "CI 相对点估计明显不对称：%.3g 距下限 %.3g、距上限 %.3g"
                        "（正态近似 CI 应近似对称；偏态数据请确认后忽略）"
                        % (est, est - lo, hi - est), "minor")

        # C4 impossible values
        for m in pv:
            if m["value"] > 1.0 or m["value"] < 0.0:
                add("C4_impossible_pvalue", s,
                    "p 值 %.3g 落在 [0,1] 之外，数学上不可能" % m["value"], "critical")
        for m in [m for m in ms if m["kind"] == "percent"]:
            if m["value"] > 100.0 and not re.search(r"\b(increase|growth|rise|fold|of baseline|relative)\b", t, re.I):
                add("C4_impossible_percent", s,
                    "百分比 %.3g%% > 100%% 且句内无相对/增长语境" % m["value"], "major")
        for m in [m for m in ms if m["kind"] == "meansd"]:
            if m["value"][1] < 0:
                add("C4_negative_sd", s,
                    "mean±SD 中 SD 为负：%s" % m["value"], "major")

        # C6 direction of effect vs numeric order
        pair = [m for m in ms if m["kind"] == "vs_pair"]
        if pair:
            a, b = pair[0]["value"]
            if HIGHER.search(t) and a < b:
                add("C6_direction_conflict", s,
                    "句内有 higher/greater 类表述，但数值顺序 %.3g vs %.3g 为前者更小"
                    % (a, b), "major")
            if LOWER.search(t) and a > b:
                add("C6_direction_conflict", s,
                    "句内有 lower/reduced 类表述，但数值顺序 %.3g vs %.3g 为前者更大"
                    % (a, b), "major")

    # C5 same quantity, different value across sections (numunit keys)
    by_key = {}
    for s in sents:
        for m in mentions.get(s["id"], []):
            if m["kind"] != "numunit":
                continue
            key = m["value"][1]
            by_key.setdefault(key, []).append((s, m["value"][0]))
    for key, rows in by_key.items():
        secs = {}
        for s, v in rows:
            secs.setdefault(s["section"], set()).add(v)
        for sec_a in secs:
            for sec_b in secs:
                if sec_a >= sec_b:
                    continue
                if sec_a in ("abstract", "results") and sec_b in ("abstract", "results"):
                    diff = secs[sec_a] ^ secs[sec_b]
                    if diff:
                        add("C5_crosssection_value", {"id": "multiple", "section": "%s+%s" % (sec_a, sec_b), "text": ""},
                            "单位 %s 的取值集合在 %s=%s 与 %s=%s 不一致；回 sentences.jsonl 逐句核对是否同一量"
                            % (key, sec_a, sorted(secs[sec_a]), sec_b, sorted(secs[sec_b])),
                            "needs_review")

    atomic_write_json(os.path.join(args.work, "candidates.json"), {
        "candidate_count": len(cands),
        "rules": {r: sum(1 for c in cands if c["rule"] == r) for r in
                  sorted({c["rule"] for c in cands})},
        "candidates": cands,
        "note": "全部为确定性候选；agent 必须回到 sentences.jsonl 读原句确认后才可升级为 finding",
    })
    print(json.dumps({"status": "ok", "candidates": len(cands)}, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ verify
def cmd_verify(args):
    try:
        sents = {s["id"]: s["text"] for s in load_sentences(args.work)}
    except OSError:
        eprint("FATAL: sentences.jsonl missing in %s; run scan first" % args.work)
        return 3
    with open(args.findings, encoding="utf-8") as fh:
        findings = json.load(fh)
    problems = []
    for f in findings:
        fid, sid, q = f.get("id", "?"), f.get("sentence_id"), f.get("quote", "")
        if sid not in sents:
            problems.append({"id": fid, "problem": "unknown sentence_id %r" % sid})
        elif not q or q not in sents[sid]:
            problems.append({"id": fid, "problem": "quote not verbatim substring of %s" % sid})
    if problems:
        atomic_write_json(os.path.join(args.work, "verify_problems.json"), problems)
        for p in problems:
            eprint("VIOLATION %(id)s: %(problem)s" % p)
        return 4
    print(json.dumps({"status": "ok", "checked": len(findings)}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--input", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("check")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("verify")
    p.add_argument("--work", required=True)
    p.add_argument("--findings", required=True)
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
