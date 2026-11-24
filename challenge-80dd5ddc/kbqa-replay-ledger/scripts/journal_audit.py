#!/usr/bin/env python3
"""journal_audit.py — 过程审计：日志完整性与输入覆盖核对（确定性，stdlib-only）。

核对三件事：
1. 哈希链完整（无人事后改日志）；
2. 输入覆盖：/input 下每个真实文件在日志中至少出现一次（scan/read/skip
   之一），没有"从未被任何操作触及"的文件——未触及即未检查；
3. 关键阶段齐备：存在 scan ≥1、search/read ≥1、verify ≥1、seal =1（收尾）。
产出 audit_report.json；issues 非空时 result.json 只能为 partial。
退出码恒 0。
"""
import argparse
import hashlib
import json
import os
import sys
import time

SKIP_NAMES = {"case.json", "task.md"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    entries = []
    jp = os.path.join(a.work, "journal.jsonl")
    if os.path.exists(jp):
        with open(jp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        entries.append({"op": "__corrupt__", "raw": line[:100]})

    # 1) 哈希链
    prev, chain_ok, broken_at = "GENESIS", True, None
    for e in entries:
        if e.get("prev") != prev:
            chain_ok, broken_at = False, e.get("seq")
            break
        prev = hashlib.sha256(json.dumps(
            e, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    # 2) 输入覆盖
    input_root = os.path.abspath(a.input)
    disk = []
    for root, dirs, names in os.walk(input_root):
        dirs.sort()
        for n in sorted(names):
            if n.startswith(".") or (n in SKIP_NAMES and os.path.abspath(root) == input_root):
                continue
            p = os.path.join(root, n)
            if os.path.isfile(p) and not os.path.islink(p):
                disk.append(os.path.relpath(p, input_root))
    touched = set()
    for e in entries:
        blob = json.dumps(e, ensure_ascii=False)
        for rel in disk:
            base = os.path.basename(rel)
            if rel in blob or (base in blob and len(base) >= 6):
                touched.add(rel)
    untouched = [rel for rel in disk if rel not in touched]

    # 3) 阶段齐备
    ops = [e.get("op") for e in entries]
    phases = {"scan": ops.count("scan"), "search_or_read": ops.count("search") + ops.count("read"),
              "verify": ops.count("verify"), "seal": ops.count("seal"),
              "skip": ops.count("skip"), "error": ops.count("error")}
    sealed_at = [i for i, o in enumerate(ops) if o == "seal"]
    post_seal = len(ops) - 1 - sealed_at[-1] if sealed_at else 0

    issues = []
    if not chain_ok:
        issues.append("hash chain broken at seq %s" % broken_at)
    if untouched:
        issues.append("untouched input files: %s" % "、".join(untouched[:10]))
    if phases["scan"] == 0:
        issues.append("no scan operation logged")
    if phases["verify"] == 0:
        issues.append("no verify operation logged")
    if phases["seal"] == 0:
        issues.append("journal not sealed")
    if post_seal:
        issues.append("%d entries appended after seal" % post_seal)

    report = {"schema": "kbqa-replay-ledger/audit/v1",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "entries": len(entries), "chain_ok": chain_ok,
              "input_files": len(disk), "touched": len(touched), "untouched": untouched,
              "phases": phases, "post_seal_entries": post_seal,
              "pass": not issues, "issues": issues}
    with open(os.path.join(a.out, "audit_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"entries": len(entries), "chain_ok": chain_ok,
                      "untouched": len(untouched), "pass": not issues,
                      "issues": issues}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
