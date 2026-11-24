#!/usr/bin/env python3
"""rerun_diff.py -- 两次筛选判定运行的语义级差异对比。

输入两个判定文件（JSON 数组，元素至少含 record_id、decision；
可选 reason_code、evidence_snippet）。集合语义对比，与文件内顺序无关：
  D1 record_id 集合一致（missing_in_a / missing_in_b）
  D2 共有记录的 decision 一致（label_flips 列表）
  D3 共有记录且 decision 一致时 reason_code 一致（reason_changes）
  D4 证据片段一致（evidence_changes；仅在一侧缺失时记 WARN 级）

产物 rerun_report.json：{deterministic: bool, diffs: {...}}。
deterministic=false 时 exit 3——复跑不确定的判定不可交付，须查明
（输入变了？判定用了非确定采样？人工介入未留痕？）。
"""
import argparse
import json
import os
import sys


def load(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("decisions", "records", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    table = {}
    for row in data:
        rid = row.get("record_id")
        if rid is None:
            continue
        table[rid] = {
            "decision": row.get("decision"),
            "reason_code": row.get("reason_code"),
            "evidence_snippet": row.get("evidence_snippet"),
        }
    return table


def main():
    ap = argparse.ArgumentParser(description="复跑判定差异对比")
    ap.add_argument("--a", required=True, help="第一次运行 decisions.json")
    ap.add_argument("--b", required=True, help="第二次运行 decisions.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    for p in (args.a, args.b):
        if not os.path.isfile(p):
            print("DIFF-ERROR: 文件缺失：%s" % p, file=sys.stderr)
            sys.exit(2)
    ta, tb = load(args.a), load(args.b)

    only_a = sorted(set(ta) - set(tb))
    only_b = sorted(set(tb) - set(ta))
    flips, reason_changes, evidence_changes = [], [], []
    for rid in sorted(set(ta) & set(tb)):
        ra, rb = ta[rid], tb[rid]
        if ra["decision"] != rb["decision"]:
            flips.append({"record_id": rid, "a": ra["decision"], "b": rb["decision"]})
        elif ra["reason_code"] != rb["reason_code"]:
            reason_changes.append({"record_id": rid, "a": ra["reason_code"],
                                   "b": rb["reason_code"]})
        if ra["evidence_snippet"] != rb["evidence_snippet"]:
            evidence_changes.append({"record_id": rid,
                                     "a_present": ra["evidence_snippet"] is not None,
                                     "b_present": rb["evidence_snippet"] is not None})

    deterministic = not (only_a or only_b or flips or reason_changes)
    report = {
        "deterministic": deterministic,
        "counts": {"a": len(ta), "b": len(tb), "common": len(set(ta) & set(tb))},
        "diffs": {
            "missing_in_b": only_a,
            "missing_in_a": only_b,
            "label_flips": flips,
            "reason_changes": reason_changes,
            "evidence_changes": evidence_changes,
        },
        "note": "evidence_changes 不单独判定非确定性（模型措辞可微调），但须人工过目。",
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("RERUN %s: a=%d b=%d flips=%d reason_changes=%d evidence_changes=%d"
          % ("DETERMINISTIC" if deterministic else "NONDETERMINISTIC",
             len(ta), len(tb), len(flips), len(reason_changes),
             len(evidence_changes)))
    sys.exit(0 if deterministic else 3)


if __name__ == "__main__":
    main()
