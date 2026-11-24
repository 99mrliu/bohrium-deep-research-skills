#!/usr/bin/env python3
"""link_check.py — 引用链接校验（bundle D 签名脚本 2）。

校验 work/review_draft.md 与 work/evidence_ledger.jsonl 之间的链接完整性：
  失败（退出码 1）：
    - 草稿中 [E#] 标记指向不存在的证据行（unresolved_markers）；
    - 证据表 evidence_id 重复；
    - 证据行缺必填字段（evidence_id/doc_id/locator/verbatim_quote/supports/theme/strength）。
  警告（只报告，不阻断）：
    - 从未被草稿引用的证据行（unused_evidence）；
    - 无证据标记的实质句（长度 > 20 且非标题/列表/引用/推断/缺口行）。
产物：out/link_check_report.json。stdout 打印一行 JSON 摘要。
"""
import json
import os
import re
import sys

MARK_RE = re.compile(r"\[E\d+(?:;E\d+)*\]")
EID_RE = re.compile(r"E\d+")
REQUIRED_EVIDENCE_FIELDS = ["evidence_id", "doc_id", "locator", "verbatim_quote",
                            "supports", "theme", "strength"]


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def unsupported_sentences(draft, min_len=20):
    out = []
    for line in draft.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", ">", "-", "*")) or re.match(r"^\d+[.)]", s):
            continue
        if s.startswith("[推断]") or s.startswith("[证据缺口]"):
            continue
        if MARK_RE.search(s):
            continue
        if len(s) > min_len:
            out.append(s)
    return out


def run(work, out):
    os.makedirs(out, exist_ok=True)
    ledger = load_jsonl(os.path.join(work, "evidence_ledger.jsonl"))
    draft_path = os.path.join(work, "review_draft.md")
    draft = open(draft_path, encoding="utf-8").read() if os.path.exists(draft_path) else ""

    failures, warnings = [], []

    seen, dup_ids, bad_rows = set(), [], []
    for i, r in enumerate(ledger, 1):
        eid = r.get("evidence_id")
        if eid in seen:
            dup_ids.append(eid)
        seen.add(eid)
        missing = [k for k in REQUIRED_EVIDENCE_FIELDS if not r.get(k)]
        if missing:
            bad_rows.append({"line": i, "evidence_id": eid, "missing": missing})
    if dup_ids:
        failures.append(f"证据表 evidence_id 重复：{sorted(set(map(str, dup_ids)))}")
    for b in bad_rows:
        failures.append(f"证据表第 {b['line']} 行（{b['evidence_id']}）缺必填字段：{b['missing']}")

    ledger_ids = {r.get("evidence_id") for r in ledger}
    marks_in_order = []
    for m in MARK_RE.finditer(draft):
        for eid in EID_RE.findall(m.group(0)):
            marks_in_order.append(eid)
    referenced = set(marks_in_order)
    unresolved = sorted(referenced - ledger_ids,
                        key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
    if unresolved:
        failures.append(f"草稿引用了不存在的证据行：{unresolved}")
    if not draft.strip():
        warnings.append("review_draft.md 缺失或为空")

    unused = sorted((r.get("evidence_id") for r in ledger
                     if r.get("evidence_id") not in referenced),
                    key=lambda x: int(str(x)[1:]) if str(x)[1:].isdigit() else 0)
    if unused:
        warnings.append(f"{len(unused)} 条证据行未被草稿引用：{unused}")
    unsupported = unsupported_sentences(draft)
    if unsupported:
        warnings.append(f"{len(unsupported)} 句实质句无证据标记（已公示于审计报告）")

    referenced_counts = {}
    for eid in marks_in_order:
        referenced_counts[eid] = referenced_counts.get(eid, 0) + 1

    report = {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "draft_file": draft_path,
        "marks_total": len(marks_in_order),
        "referenced_counts": referenced_counts,
        "unresolved_markers": unresolved,
        "unused_evidence": unused,
        "unsupported_sentences": unsupported,
    }
    with open(os.path.join(out, "link_check_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": report["ok"], "failures": len(failures),
                      "warnings": len(warnings), "unresolved": unresolved,
                      "unused": len(unused), "unsupported": len(unsupported)},
                     ensure_ascii=False))
    return 0 if report["ok"] else 1


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    sys.exit(run(args.work, args.out))


if __name__ == "__main__":
    main(sys.argv[1:])
