#!/usr/bin/env python3
"""quote_gate.py — 引用门控（bundle A）。

校验 work/evidence_ledger.jsonl 与草稿（默认 work/review_draft.md）：
  1. quote-at-locator：verbatim_quote 归一化后必须是所声称页文本的子串。
  2. 信任强制：strength=established 的证据行，其来源 trust_tier 必须为 T1；
     T2 来源 strength ≤ suggestive；T3 来源一律判失败。
  3. 草稿标记 [E#] 必须解析到通过校验的证据行。
失败的证据行移出；草稿中依赖失败证据的句子被降级：句中标记替换为 [推断]，并记录。
产物（out 目录）：gate_report.json；就地修订后的草稿写回 out/review_draft.md。
"""
import json
import os
import re
import sys

MARK_RE = re.compile(r"\[E\d+(;E\d+)*\]")


def norm(s):
    s = re.sub(r"-\s*\n\s*", "", s)               # 断词连字符
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"[–—]", "-", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def page_text(work, doc_id, page_no):
    path = os.path.join(work, "pages", f"{doc_id}.jsonl")
    for row in load_jsonl(path):
        if row["page"] == page_no:
            return row["text"]
    return None


def check_evidence(work, row, trust):
    eid = row.get("evidence_id", "?")
    did = row.get("doc_id")
    loc = str(row.get("locator", ""))
    m = re.match(r"p(\d+)", loc)
    if not did or not m:
        return False, "locator_unparseable"
    t = trust.get(did, "T3")
    if t == "T3":
        return False, f"source_trust_T3"
    text = page_text(work, did, int(m.group(1)))
    if text is None:
        return False, "page_missing"
    if norm(row.get("verbatim_quote", "")) not in norm(text):
        return False, "quote_not_at_locator"
    if row.get("strength") == "established" and t != "T1":
        return False, f"established_on_{t}"
    return True, "ok"


def revise_draft(draft, failed_ids):
    """把引用失败证据的标记降级为 [推断]，返回 (新文本, 降级句数)。"""
    downgraded = 0
    out_lines = []
    for line in draft.splitlines():
        ids = set(re.findall(r"E\d+", line))
        if ids & failed_ids and MARK_RE.search(line):
            line = MARK_RE.sub("[推断]", line)
            if not line.lstrip().startswith(">"):
                line = line + "（原引用未通过门控，已降级为推断）"
            downgraded += 1
        out_lines.append(line)
    return "\n".join(out_lines), downgraded


def run(work, out, ledger_rel="evidence_ledger.jsonl", draft_rel="review_draft.md"):
    ledger = load_jsonl(os.path.join(work, ledger_rel))
    manifest_path = os.path.join(work, "source_manifest.json")
    trust = {}
    if os.path.exists(manifest_path):
        for e in json.load(open(manifest_path, encoding="utf-8")):
            trust[e["doc_id"]] = e["trust_tier"]

    results, verified_ids, failed_ids = [], set(), set()
    for row in ledger:
        ok, reason = check_evidence(work, row, trust)
        results.append({"evidence_id": row.get("evidence_id"), "ok": ok, "reason": reason})
        (verified_ids if ok else failed_ids).add(row.get("evidence_id"))

    draft_path = os.path.join(work, draft_rel)
    draft = open(draft_path, encoding="utf-8").read() if os.path.exists(draft_path) else ""
    unresolved = sorted(set(re.findall(r"E\d+", draft)) -
                        {r.get("evidence_id") for r in ledger})
    revised, downgraded = revise_draft(draft, failed_ids | set(unresolved))

    os.makedirs(out, exist_ok=True)
    if draft:
        with open(os.path.join(out, "review_draft.md"), "w", encoding="utf-8") as f:
            f.write(revised)
    verified_rows = [r for r in ledger if r.get("evidence_id") in verified_ids]
    with open(os.path.join(out, "evidence_ledger.verified.jsonl"), "w", encoding="utf-8") as f:
        for r in verified_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = {
        "total_evidence": len(ledger),
        "verified": len(verified_ids),
        "failed": sorted(failed_ids),
        "unresolved_markers": unresolved,
        "downgraded_sentences": downgraded,
        "details": results,
        "gate_passed": not failed_ids and not unresolved,
    }
    with open(os.path.join(out, "gate_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    r = run(args.work, args.out)
    print(json.dumps({"verified": r["verified"], "failed": len(r["failed"]),
                      "gate_passed": r["gate_passed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
