#!/usr/bin/env python3
"""map_criteria.py -- 纳入/排除标准与概念块的映射核验。

输入：
  --question  research_question.json（含 concept_blocks）
  --criteria  criteria.json：
    {"inclusion": [{"criterion_id":"I1","text":"...","blocks":["P","I"]}],
     "exclusion": [{"criterion_id":"E1","text":"...","blocks":["S"]}]}
  --protocol  search_protocol.json（可选；给出则核验每个被引用块都进入了
              全部数据库检索式）

检查：
  M1 每条标准引用的 block_id 必须存在于概念块表（悬空引用=ERROR）；
  M2 标准未引用任何概念块=WARN（该标准与检索式脱节，靠筛选阶段兜底）；
  M3 概念块未被任何纳入标准引用=WARN（可能引入噪声或标准覆盖不全）；
  M4 给出 protocol 时，被引用块的 clause 必须出现在每条数据库检索式中。

产物 criteria_map.json + criteria_map.md。退出码 0=无 ERROR；3=有 ERROR；2=输入缺失。
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(description="标准—概念块映射核验")
    ap.add_argument("--question", required=True)
    ap.add_argument("--criteria", required=True)
    ap.add_argument("--protocol", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    for p in (args.question, args.criteria):
        if not os.path.isfile(p):
            print("MAP-INPUT-MISSING: %s" % p, file=sys.stderr)
            sys.exit(2)
    q = json.load(open(args.question, encoding="utf-8"))
    crit = json.load(open(args.criteria, encoding="utf-8"))
    proto = None
    if args.protocol:
        if not os.path.isfile(args.protocol):
            print("MAP-INPUT-MISSING: %s" % args.protocol, file=sys.stderr)
            sys.exit(2)
        proto = json.load(open(args.protocol, encoding="utf-8"))

    blocks = {b["block_id"]: b for b in q.get("concept_blocks", [])}
    issues, mapping = [], []

    def add(rule, severity, where, message):
        issues.append({"rule": rule, "severity": severity,
                       "where": where, "message": message})

    referenced = set()
    for kind in ("inclusion", "exclusion"):
        for c in crit.get(kind, []):
            cid = c.get("criterion_id", "?")
            cblocks = c.get("blocks") or []
            row = {"criterion_id": cid, "kind": kind, "text": c.get("text", ""),
                   "blocks": cblocks, "block_status": {}}
            if not cblocks:
                add("M2", "WARN", cid, "标准未引用概念块，检索式层面对应关系缺失")
            for bid in cblocks:
                if bid not in blocks:
                    add("M1", "ERROR", cid, "引用了不存在的概念块 %s" % bid)
                    row["block_status"][bid] = "dangling"
                else:
                    referenced.add(bid)
                    row["block_status"][bid] = "ok"
            mapping.append(row)

    for bid in blocks:
        if bid not in referenced:
            add("M3", "WARN", bid, "概念块未被任何纳入标准引用")

    if proto:
        for row in mapping:
            for bid, st in row["block_status"].items():
                if st != "ok":
                    continue
                for qitem in proto.get("queries", []):
                    clauses = [t["clause"] for t in qitem.get("block_trace", [])
                               if t["block_id"] == bid]
                    if not clauses or clauses[0] not in qitem["query"]:
                        add("M4", "ERROR", row["criterion_id"],
                            "概念块 %s 的子句未出现在 %s 检索式中"
                            % (bid, qitem["database"]))

    overall = "FAIL" if any(i["severity"] == "ERROR" for i in issues) else (
        "WARN" if issues else "PASS")
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "criteria_map.json"), "w", encoding="utf-8") as fh:
        json.dump({"overall": overall, "mapping": mapping, "issues": issues},
                  fh, ensure_ascii=False, indent=2)
    lines = ["# 标准—概念块映射报告", "", "总体：**%s**" % overall, "",
             "| 标准 | 类型 | 引用块 | 状态 |", "|---|---|---|---|"]
    for row in mapping:
        lines.append("| %s | %s | %s | %s |" % (
            row["criterion_id"], row["kind"],
            ", ".join(row["blocks"]) or "（无）",
            "; ".join("%s=%s" % kv for kv in row["block_status"].items()) or "-"))
    if issues:
        lines += ["", "## 问题清单"]
        for i in issues:
            lines.append("- [%s/%s] %s：%s" % (i["rule"], i["severity"],
                                               i["where"], i["message"]))
    with open(os.path.join(args.out, "criteria_map.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("MAP %s (%d criteria, %d issues) -> %s"
          % (overall, len(mapping), len(issues), args.out))
    sys.exit(0 if overall != "FAIL" else 3)


if __name__ == "__main__":
    main()
