#!/usr/bin/env python3
"""citescan.py — 引用支持核查引擎 for paper-audit skills.

Pure Python 3.8+ standard library. Deterministic. Zero dependencies.
Maps every in-text citation to its host sentence and to the reference list,
reconciles the two sides deterministically, and classifies citation function
heuristically. It CANNOT read the cited sources: whether a reference
actually supports the citing sentence is agent work (or external-tool work);
this engine prepares the worksheet and guards honesty.

Subcommands:
  parse      --input PATH --work DIR  -> sentences.jsonl, citations.jsonl, references.jsonl
  reconcile  --work DIR               -> reconcile.json (cited-not-listed, listed-not-cited,
                                       numbering gaps, duplicate entries)
  worksheet  --work DIR               -> worksheet.json (per-citation host sentence, function
                                       guess, claim-strength flags, ref entry text)
  verify     --work DIR --findings F  quote gate: finding quotes must be verbatim substrings

Exit codes: 0 ok; 3 fatal input error; verify 4 = violations.
"""
import argparse
import json
import os
import re
import sys

# "et al." must not terminate a sentence; decimals must not either.
SENT = re.compile(r".*?(?:[。！？；;!?]+|(?<!\bal)\.+(?!\d)|\n|$)")
REF_HEAD = re.compile(r"^\s*(references|bibliography|参考文献)\s*$", re.I)
NUM_CITE = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")
AUTH_CITE_PAREN = re.compile(r"\(([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+et\s+al\.?)?(?:\s*(?:&|and)\s+[A-Z][A-Za-zÀ-ÿ'\-]+)?),?\s+((?:19|20)\d{2})[a-z]?\)")
AUTH_CITE_NARR = re.compile(r"\b([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+et\s+al\.?)?)\s*\(((?:19|20)\d{2})[a-z]?\)")
# Both "[1] text" and "1. text" / "1) text" reference-entry styles.
REF_NUM_ENTRY = re.compile(r"^\s*(?:\[(\d{1,3})\]\s*|(\d{1,3})[.)]\s+)(.+)")
REF_AUTH_ENTRY = re.compile(r"^\s*([A-Z][A-Za-zÀ-ÿ'\-]+).*?\b((?:19|20)\d{2})[a-z]?\b")

SUPPORT_CUES = re.compile(r"\b(showed|demonstrated|found|reported|established|proved|confirmed|observed|表明|证实|证明)\b", re.I)
CONTRAST_CUES = re.compile(r"\b(however|in contrast|unlike|whereas|contrary|failed to|相反|不同)\b", re.I)
METHOD_CUES = re.compile(r"\b(using|following|as described|adapted from|according to the method|protocol|依据|按照)\b", re.I)
BACKGROUND_CUES = re.compile(r"\b(widely|well[- ]known|known|reviewed|commonly|通常|广泛|已知)\b", re.I)
STRONG_CLAIM = re.compile(r"\b(cures?|eliminates?|proves?|demonstrates?|establishes?|causes?|leads? to|guarantees?|治愈|根除|证明了|导致)\b", re.I)


def eprint(*a):
    print(*a, file=sys.stderr)


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def expand_numspec(spec):
    nums = set()
    for part in re.split(r"\s*,\s*", spec):
        m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b and b - a <= 200:
                nums.update(range(a, b + 1))
        elif part.strip().isdigit():
            nums.add(int(part.strip()))
    return sorted(nums)


# ------------------------------------------------------------------- parse
def cmd_parse(args):
    if not os.path.isfile(args.input):
        eprint("FATAL: input not found: %s" % args.input)
        return 3
    os.makedirs(args.work, exist_ok=True)
    with open(args.input, encoding="utf-8") as fh:
        text = fh.read()
    raw_lines = text.split("\n")

    # reference list = lines after the references heading
    ref_start = None
    for i, ln in enumerate(raw_lines):
        if REF_HEAD.match(ln):
            ref_start = i
    body_lines = raw_lines[:ref_start] if ref_start is not None else raw_lines
    ref_lines = raw_lines[ref_start + 1:] if ref_start is not None else []

    joined = " ".join(body_lines)
    line_starts, pos = [], 0
    for ln in body_lines:
        line_starts.append(pos)
        pos += len(ln) + 1
    import bisect

    sents, cites = [], []
    idx = 0
    for m in SENT.finditer(joined):
        s = m.group(0).strip()
        if len(s) < 4:
            continue
        idx += 1
        sid = "S%04d" % idx
        ln_no = bisect.bisect_right(line_starts, m.start())
        sents.append({"id": sid, "line": ln_no, "text": s})
        for cm in NUM_CITE.finditer(s):
            for n in expand_numspec(cm.group(1)):
                cites.append({"sentence_id": sid, "kind": "numbered",
                              "key": n, "raw": cm.group(0)})
        for cm in AUTH_CITE_PAREN.finditer(s):
            cites.append({"sentence_id": sid, "kind": "author_year",
                          "key": "%s %s" % (cm.group(1), cm.group(2)),
                          "raw": cm.group(0)})
        for cm in AUTH_CITE_NARR.finditer(s):
            # narrative form Author (2020); avoid double-counting parenthetical
            if "(%s" % cm.group(2) in s and cm.start() > 0 and s[cm.start() - 1] == "(":
                continue
            cites.append({"sentence_id": sid, "kind": "author_year_narrative",
                          "key": "%s %s" % (cm.group(1), cm.group(2)),
                          "raw": cm.group(0)})

    refs = []
    for i, ln in enumerate(ref_lines):
        if not ln.strip():
            continue
        m = REF_NUM_ENTRY.match(ln)
        if m:
            refs.append({"kind": "numbered", "key": int(m.group(1) or m.group(2)),
                         "text": m.group(3).strip(), "ref_line": ref_start + 2 + i})
            continue
        m = REF_AUTH_ENTRY.match(ln)
        if m and not ln.strip().startswith(("http", "doi", "DOI")):
            refs.append({"kind": "author_year", "key": "%s %s" % (m.group(1), m.group(2)),
                         "text": ln.strip(), "ref_line": ref_start + 2 + i})

    atomic_write(os.path.join(args.work, "sentences.jsonl"),
                 "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sents))
    atomic_write(os.path.join(args.work, "citations.jsonl"),
                 "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cites))
    atomic_write(os.path.join(args.work, "references.jsonl"),
                 "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in refs))
    print(json.dumps({"status": "ok", "sentences": len(sents),
                      "citations": len(cites), "references": len(refs),
                      "references_section_found": ref_start is not None},
                     ensure_ascii=False))
    return 0


def _load(work, name):
    rows = []
    with open(os.path.join(work, name), encoding="utf-8") as fh:
        for ln in fh:
            rows.append(json.loads(ln))
    return rows


# --------------------------------------------------------------- reconcile
def cmd_reconcile(args):
    try:
        cites = _load(args.work, "citations.jsonl")
        refs = _load(args.work, "references.jsonl")
    except OSError:
        eprint("FATAL: run parse first")
        return 3
    def norm_ay(key):
        # match on first-author surname + year; "Zhang et al. 2018" == "Zhang 2018"
        return re.sub(r"\s+et\s+al\.?", "", key).strip()

    cited_num = sorted({c["key"] for c in cites if c["kind"] == "numbered"})
    listed_num = sorted({r["key"] for r in refs if r["kind"] == "numbered"})
    cited_ay = sorted({norm_ay(c["key"]) for c in cites if c["kind"].startswith("author_year")})
    listed_ay = sorted({norm_ay(r["key"]) for r in refs if r["kind"] == "author_year"})

    out = {
        "numbered": {
            "cited_not_listed": sorted(set(cited_num) - set(listed_num)),
            "listed_not_cited": sorted(set(listed_num) - set(cited_num)),
            "numbering_gaps": sorted(set(range(1, max(listed_num) + 1)) - set(listed_num)) if listed_num else [],
        },
        "author_year": {
            "cited_not_listed": sorted(set(cited_ay) - set(listed_ay)),
            "listed_not_cited": sorted(set(listed_ay) - set(cited_ay)),
        },
        "duplicates": {},
        "notes": [],
    }
    seen = {}
    for r in refs:
        seen.setdefault(r["key"], []).append(r["ref_line"])
    out["duplicates"] = {str(k): v for k, v in seen.items() if len(v) > 1}
    if not refs:
        out["notes"].append("reference_entries_detected=0：参考文献区解析失败或缺失；"
                            "引用齐全性不可判定，必须标待复核，禁止宣称引用齐全")
    if out["numbered"]["cited_not_listed"] or out["author_year"]["cited_not_listed"]:
        out["notes"].append("cited_not_listed 为确定性缺陷候选：正文引用了文献表中不存在的条目")
    atomic_write_json(os.path.join(args.work, "reconcile.json"), out)
    print(json.dumps({"status": "ok",
                      "cited_not_listed": (out["numbered"]["cited_not_listed"] +
                                           out["author_year"]["cited_not_listed"]),
                      "listed_not_cited": (out["numbered"]["listed_not_cited"] +
                                           out["author_year"]["listed_not_cited"])},
                     ensure_ascii=False))
    return 0


# --------------------------------------------------------------- worksheet
def cmd_worksheet(args):
    try:
        sents = {s["id"]: s for s in _load(args.work, "sentences.jsonl")}
        cites = _load(args.work, "citations.jsonl")
        refs = _load(args.work, "references.jsonl")
    except OSError:
        eprint("FATAL: run parse first")
        return 3
    def norm_ay(key):
        return re.sub(r"\s+et\s+al\.?", "", str(key)).strip()

    ref_by_key = {}
    for r in refs:
        ref_by_key.setdefault(r["key"] if r["kind"] == "numbered"
                              else norm_ay(r["key"]), r)
    rows = []
    for c in cites:
        sent = sents.get(c["sentence_id"], {})
        t = sent.get("text", "")
        if CONTRAST_CUES.search(t):
            fn = "contrast"
        elif METHOD_CUES.search(t):
            fn = "method_source"
        elif SUPPORT_CUES.search(t):
            fn = "support"
        elif BACKGROUND_CUES.search(t):
            fn = "background"
        else:
            fn = "mention"
        lookup = c["key"] if c["kind"] == "numbered" else norm_ay(c["key"])
        ref = ref_by_key.get(lookup)
        rows.append({
            "sentence_id": c["sentence_id"],
            "citation_raw": c["raw"],
            "citation_key": c["key"],
            "function_guess": fn,
            "strong_claim_with_citation": bool(STRONG_CLAIM.search(t)),
            "host_sentence": t,
            "reference_entry": ref["text"] if ref else None,
            "reference_found": ref is not None,
            "agent_tasks": ([
                "该句为强主张且带引用：核对被引文献是否真支持该强度（能获取原文则用外部工具，不能则标待复核，禁止凭空断言不支持）",
            ] if STRONG_CLAIM.search(t) else []),
        })
    atomic_write_json(os.path.join(args.work, "worksheet.json"), {
        "citation_count": len(rows),
        "strong_claim_citations": sum(1 for r in rows if r["strong_claim_with_citation"]),
        "worksheet": rows,
        "honesty_rule": "无法获取被引原文时，引用支持度一律标待复核并写明原因；只允许对 cited_not_listed 这类文本内确定性缺陷直接定案",
    })
    print(json.dumps({"status": "ok", "citations": len(rows)}, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ verify
def cmd_verify(args):
    try:
        sents = {s["id"]: s["text"] for s in _load(args.work, "sentences.jsonl")}
    except OSError:
        eprint("FATAL: run parse first")
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
    p = sub.add_parser("parse")
    p.add_argument("--input", required=True)
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_parse)
    p = sub.add_parser("reconcile")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_reconcile)
    p = sub.add_parser("worksheet")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_worksheet)
    p = sub.add_parser("verify")
    p.add_argument("--work", required=True)
    p.add_argument("--findings", required=True)
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
