#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""change_ledger.py -- 声明改动账本：差异必须逐条有声明，否则视为事故。

原则：格式适配**允许**任务要求的改动（改样式、修题注、统一参考文献），
但每一处改动必须事先/当场声明（unit/before/after/reason），
census_diff 报出的每个差异都必须被账本条目覆盖。覆盖判定是保守启发式：
- text_mismatch：存在条目其 before 是源文本的子串（或 after 是产物文本子串）；
- numeric/citation token：存在条目的 before/after 含该 token；
- object_count/unit_count：存在条目 kind=object/unit 且 detail 点名对象名。

用法:
  change_ledger.py init ledger.json
  change_ledger.py add ledger.json --unit "unit 3" --before "0.85" --after "0.86" --reason "按任务更新测量值"
  change_ledger.py verify ledger.json diff.json        # 退出码 0=全覆盖; 1=有未声明差异
"""
import argparse, json, sys, time

def cmd_init(path):
    json.dump({"ledger_version": "1.0", "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "entries": []}, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("ledger initialized ->", path)

def cmd_add(path, unit, before, after, reason):
    ld = json.load(open(path, encoding="utf-8"))
    ld["entries"].append({"seq": len(ld["entries"]) + 1, "unit": unit,
                          "before": before, "after": after, "reason": reason,
                          "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    json.dump(ld, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("entry %d added" % len(ld["entries"]))

def covered(d, entries):
    kind = d["kind"]
    for e in entries:
        b, a = e.get("before", ""), e.get("after", "")
        if kind == "text_mismatch":
            st, ot = d.get("source_text", ""), d.get("output_text", "")
            if (b and b in st) or (a and a in ot):
                return e
        elif kind.startswith(("numeric", "citation")):
            try:
                toks = json.loads(d["detail"])
            except (json.JSONDecodeError, TypeError):
                toks = {}
            if any((t in b or t in a) for t in toks):
                return e
        elif kind == "object_count":
            obj = d.get("locator", "").replace("objects.", "")
            if obj and any(obj in (e.get("unit", "") + e.get("reason", "") + b + a) for _ in [0]):
                return e
        elif kind == "unit_count":
            # 单元数变化必须有明确的删除/插入声明（after 空=删，before 空=增）
            if (b and not a) or (a and not b):
                return e
    return None

def cmd_verify(path, diff_path):
    ld = json.load(open(path, encoding="utf-8"))
    diff = json.load(open(diff_path, encoding="utf-8"))
    uncovered = []
    for d in diff.get("diffs", []):
        if d["kind"] == "truncated":
            continue
        if covered(d, ld["entries"]) is None:
            uncovered.append(d)
    verdict = {"ledger": path, "diff": diff_path,
               "entries": len(ld["entries"]),
               "diffs": diff.get("diff_count", 0),
               "uncovered": uncovered,
               "verdict": "COVERED" if not uncovered else "UNDECLARED_CHANGES"}
    out_path = diff_path.replace(".json", "") + ".coverage.json"
    json.dump(verdict, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if uncovered:
        print("UNDECLARED_CHANGES: %d 处差异无账本声明 -> %s" % (len(uncovered), out_path))
        for d in uncovered[:10]:
            print("  - [%s] %s @%s" % (d["kind"], d["detail"][:100], d["locator"]))
        sys.exit(1)
    print("COVERED: %d 处差异均有声明（%d 条账本）-> %s" % (diff.get("diff_count", 0), len(ld["entries"]), out_path))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("ledger")
    p = sub.add_parser("add"); p.add_argument("ledger")
    p.add_argument("--unit", required=True); p.add_argument("--before", default="")
    p.add_argument("--after", default=""); p.add_argument("--reason", required=True)
    p = sub.add_parser("verify"); p.add_argument("ledger"); p.add_argument("diff")
    a = ap.parse_args()
    if a.cmd == "init":
        cmd_init(a.ledger)
    elif a.cmd == "add":
        cmd_add(a.ledger, a.unit, a.before, a.after, a.reason)
    else:
        cmd_verify(a.ledger, a.diff)

if __name__ == "__main__":
    main()
