#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate.py — 对 judgments.jsonl 做逐字摘录门控。

输入行格式: {"doc_id","claim_id","judgment","quote","locator","rationale"}

用法:
    python3 gate.py --workdir /app/work --judgments /app/work/judgments.jsonl

产物:
    <workdir>/gated.jsonl       每行原始行 + verdict/final_locator/reason/notes
    <workdir>/gate_report.md    各裁决计数、每篇文档覆盖率

退出码: 0 = 正常（允许弃权）; 1 = 存在畸形输入行（全部列出）; 2 = argparse 用法错误。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

REQUIRED_FIELDS = ("doc_id", "claim_id", "judgment", "quote", "locator")

VERIFIED = "verified"
VERIFIED_SPAN = "verified_span"
REPAIRED = "repaired_locator"
ABSTAIN_UNVERIFIABLE = "abstain_unverifiable"
ABSTAIN_NO_TEXT = "abstain_no_text_layer"


def eprint(*a):
    print(*a, file=sys.stderr)


def normalize(s):
    """NFKC → 断行连字符重接 → 空白折叠 → casefold。"""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"-\s*\n\s*", "", s)          # 行尾断词重接
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


LOC_RE = re.compile(
    r"^(?:p(?:age)?\s*\.?\s*)(\d+)\s*[.¶]?\s*[¶p]?\s*(?:para(?:graph)?\s*)?(\d+)$",
    re.IGNORECASE)


def parse_locator(loc):
    """容忍 p2.¶3 / P2.¶3 / p2.para3 / page 2 para 3 等写法。"""
    if not isinstance(loc, str):
        return None
    m = LOC_RE.match(loc.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def load_doc_pages(workdir, doc_id):
    path = os.path.join(workdir, "pages", doc_id + ".jsonl")
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def gate_row(row, index_docs, workdir):
    """返回 (gated_record, change_record_or_none)。"""
    doc_id = row["doc_id"]
    doc = index_docs.get(doc_id)
    base = dict(row)
    base["verdict"] = None
    base["final_locator"] = None
    base["reason"] = None
    base["notes"] = []
    change = None

    if doc is None:
        base["verdict"] = ABSTAIN_UNVERIFIABLE
        base["reason"] = "unknown doc_id: not present in index"
        return base, None
    if not doc.get("text_layer"):
        base["verdict"] = ABSTAIN_NO_TEXT
        base["reason"] = "document has no usable text layer (%s)" % (
            doc.get("note") or "unknown")
        return base, None

    quote = row.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        base["verdict"] = ABSTAIN_UNVERIFIABLE
        base["reason"] = "empty quote"
        return base, None
    nq = normalize(quote)

    rows = load_doc_pages(workdir, doc_id)
    if not rows:
        base["verdict"] = ABSTAIN_UNVERIFIABLE
        base["reason"] = "pages file missing for doc_id %s" % doc_id
        return base, None
    norm_rows = [(r, normalize(r["text"])) for r in rows]
    by_pp = {(r["page"], r["para"]): (r, nt) for r, nt in norm_rows}

    def span_text(r1, r2):
        return normalize(r1["text"] + "\n" + r2["text"])

    # 1) 声称定位符段落
    pp = parse_locator(row.get("locator"))
    if pp and pp in by_pp:
        r, nt = by_pp[pp]
        if nq in nt:
            base["verdict"] = VERIFIED
            base["final_locator"] = r["anchor"]
            return base, None
        nxt = by_pp.get((pp[0], pp[1] + 1))
        if nxt and nq in span_text(r, nxt[0]):
            base["verdict"] = VERIFIED_SPAN
            base["final_locator"] = "%s-%s" % (r["anchor"], nxt[0]["anchor"])
            if row.get("locator") != base["final_locator"]:
                change = _repair_change(row, base["final_locator"])
            return base, change

    # 2) 全篇搜索
    hits, span_hits = [], []
    for r, nt in norm_rows:
        if nq in nt:
            hits.append(r["anchor"])
    if not hits:
        for i in range(len(rows) - 1):
            r1, r2 = rows[i], rows[i + 1]
            if (r1["page"], r1["para"] + 1) == (r2["page"], r2["para"]) \
                    and nq in span_text(r1, r2):
                span_hits.append("%s-%s" % (r1["anchor"], r2["anchor"]))

    if hits:
        base["verdict"] = REPAIRED
        base["final_locator"] = hits[0]
        if len(hits) > 1:
            base["notes"].append("multiple hits: %s" % ", ".join(hits))
        base["reason"] = "quote found at %s instead of claimed locator %s" % (
            hits[0], row.get("locator"))
        change = _repair_change(row, hits[0])
        return base, change
    if span_hits:
        base["verdict"] = VERIFIED_SPAN
        base["final_locator"] = span_hits[0]
        if len(span_hits) > 1:
            base["notes"].append("multiple span hits: %s" % ", ".join(span_hits))
        base["reason"] = "quote spans adjacent paragraphs at %s (claimed %s)" % (
            span_hits[0], row.get("locator"))
        change = _repair_change(row, span_hits[0])
        return base, change

    base["verdict"] = ABSTAIN_UNVERIFIABLE
    base["reason"] = ("quote not found as substring anywhere in extracted text "
                      "of doc %s; possible paraphrase or fabrication" % doc_id)
    return base, None


def _repair_change(row, new_loc):
    return {"type": "locator_repair",
            "doc_id": row.get("doc_id"),
            "claim_id": row.get("claim_id"),
            "old_locator": row.get("locator"),
            "new_locator": new_loc}


def main(argv=None):
    ap = argparse.ArgumentParser(description="verbatim-quote gate")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--judgments", required=True, help="judgments.jsonl 路径")
    args = ap.parse_args(argv)

    index_path = os.path.join(args.workdir, "index.json")
    if not os.path.exists(index_path):
        eprint("fatal: %s not found; run build_index.py first" % index_path)
        return 1
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    index_docs = {d["doc_id"]: d for d in index.get("documents", [])}

    rows, malformed = [], []
    with open(args.judgments, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                malformed.append((lineno, "invalid JSON: %s" % exc))
                continue
            if not isinstance(obj, dict):
                malformed.append((lineno, "row is not a JSON object"))
                continue
            missing = [k for k in REQUIRED_FIELDS
                       if k not in obj or obj[k] in (None, "")]
            if missing:
                malformed.append((lineno, "missing/empty fields: %s"
                                  % ", ".join(missing)))
                continue
            rows.append(obj)

    if malformed:
        eprint("malformed input rows (%d):" % len(malformed))
        for lineno, msg in malformed:
            eprint("  line %d: %s" % (lineno, msg))
        return 1

    gated, changes = [], []
    for row in rows:
        rec, change = gate_row(row, index_docs, args.workdir)
        gated.append(rec)
        if change:
            changes.append(change)

    gated_path = os.path.join(args.workdir, "gated.jsonl")
    with open(gated_path, "w", encoding="utf-8") as f:
        for rec in gated:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 报告
    counts = {}
    for rec in gated:
        counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
    per_doc = {}
    for rec in gated:
        d = per_doc.setdefault(rec["doc_id"], {"total": 0, "anchored": 0})
        d["total"] += 1
        if rec["verdict"] in (VERIFIED, VERIFIED_SPAN, REPAIRED):
            d["anchored"] += 1

    lines = ["# Gate Report", "",
             "| verdict | count |", "|---|---|"]
    for v in (VERIFIED, VERIFIED_SPAN, REPAIRED,
              ABSTAIN_UNVERIFIABLE, ABSTAIN_NO_TEXT):
        lines.append("| %s | %d |" % (v, counts.get(v, 0)))
    lines += ["", "total judgment rows: %d" % len(gated), "",
              "## Per-doc coverage", "",
              "| doc_id | judgments | anchored (verified/span/repaired) |",
              "|---|---|---|"]
    for doc_id in sorted(per_doc):
        d = per_doc[doc_id]
        lines.append("| %s | %d | %d |" % (doc_id, d["total"], d["anchored"]))
    report_path = os.path.join(args.workdir, "gate_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("gated %d rows -> %s" % (len(gated), gated_path))
    print("verdicts: %s" % json.dumps(counts, ensure_ascii=False))
    print("report: %s" % report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
