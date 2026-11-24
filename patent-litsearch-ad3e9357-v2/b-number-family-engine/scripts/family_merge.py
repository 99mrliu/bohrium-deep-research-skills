#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""family_merge.py — 双口径确定性同族合并（stdlib only）。

输入 records.json：list of
  {"record_id": str, "numbers": [str], "priorities": [str],
   "source_locator": str}

口径（详见 references/family_scope.md）：
  - simple 简单同族：优先权集合完全相同的记录归为一族；
  - extended 扩展同族：共享 ≥1 件优先权的记录构成连通分量。
  两种口径并排输出，并附 scope_note 说明差异。

纪律：
  - 仅基于本次观察到的优先权链接，绝不声称族已穷尽；
  - 不声称族成员权利要求范围一致；
  - 无优先权的记录单列，附 warning"族归属不确定，观察到的链接非完整同族"；
  - 优先权号经 patent_numbers 确定性规范化；无法解析的原文保留并记 warning。

退出码：0 正常；2 用法/输入错误。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patent_numbers as pn

SCOPE_NOTE = (
    "simple（简单同族）= 优先权集合完全相同的记录归为一族；"
    "extended（扩展同族）= 至少共享一件优先权的记录构成的连通分量。"
    "两种口径均仅基于本次观察到的优先权链接：不保证穷尽（可能存在未观察到"
    "的成员或链接），不代表族成员权利要求范围一致，亦不包含任何法律状态"
    "判断。族归属变化须以官方登记为准。")

NO_PRIORITY_WARNING = "族归属不确定，观察到的链接非完整同族"


def _normalize_priorities(raw_prios, record_id, warnings):
    prios = []
    for p in raw_prios:
        res = pn.normalize_token(str(p))
        if res["ok"]:
            prios.append(res["normalized"])
        else:
            prios.append(str(p).strip())
            warnings.append("记录 %s：优先权 %r 无法解析，原文保留参与匹配"
                            % (record_id, p))
    return sorted(set(prios))


def merge(records):
    """records 为 list[dict]，返回 family 结果 dict。"""
    warnings = []
    norm = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            warnings.append("第 %d 条记录不是对象，已跳过" % i)
            continue
        rid = str(rec.get("record_id") or "record-%d" % i)
        prios = _normalize_priorities(rec.get("priorities") or [], rid, warnings)
        norm.append({
            "record_id": rid,
            "numbers": [str(n) for n in (rec.get("numbers") or [])],
            "priorities": prios,
            "source_locator": rec.get("source_locator"),
        })

    with_p = [r for r in norm if r["priorities"]]
    without_p = [r for r in norm if not r["priorities"]]

    # ---- simple：优先权集合完全相同 ----
    groups = {}
    for r in with_p:
        groups.setdefault(tuple(r["priorities"]), []).append(r)
    simple_families = []
    for i, (pset, members) in enumerate(sorted(groups.items()), 1):
        simple_families.append({
            "family_id": "SIMPLE-%03d" % i,
            "scope": "simple",
            "priority_set": sorted(pset),
            "members": [{"record_id": m["record_id"],
                         "numbers": m["numbers"],
                         "source_locator": m["source_locator"]}
                        for m in members],
        })

    # ---- extended：共享 ≥1 件优先权的连通分量（并查集）----
    parent = {r["record_id"]: r["record_id"] for r in with_p}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_prio = {}
    for r in with_p:
        for p in r["priorities"]:
            by_prio.setdefault(p, []).append(r["record_id"])
    for owners in by_prio.values():
        for other in owners[1:]:
            union(owners[0], other)

    comps = {}
    for r in with_p:
        comps.setdefault(find(r["record_id"]), []).append(r)
    extended_families = []
    for i, members in enumerate(
            sorted(comps.values(), key=lambda ms: sorted(
                m["record_id"] for m in ms)), 1):
        pset = sorted({p for m in members for p in m["priorities"]})
        extended_families.append({
            "family_id": "EXTENDED-%03d" % i,
            "scope": "extended",
            "priority_union": pset,
            "members": [{"record_id": m["record_id"],
                         "numbers": m["numbers"],
                         "priorities": m["priorities"],
                         "source_locator": m["source_locator"]}
                        for m in sorted(members,
                                        key=lambda m: m["record_id"])],
        })

    return {
        "simple_families": simple_families,
        "extended_families": extended_families,
        "records_without_priorities": [{
            "record_id": r["record_id"], "numbers": r["numbers"],
            "source_locator": r["source_locator"],
            "warning": NO_PRIORITY_WARNING,
        } for r in without_p],
        "scope_note": SCOPE_NOTE,
        "warnings": warnings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="family_merge.py",
                                 description="双口径确定性同族合并")
    ap.add_argument("--records", required=True, help="records.json 路径")
    ap.add_argument("--out", required=True, help="输出 family.json 路径")
    args = ap.parse_args(argv)

    if not os.path.exists(args.records):
        sys.stderr.write("records 文件不存在：%s\n" % args.records)
        return 2
    try:
        with open(args.records, "r", encoding="utf-8") as fh:
            records = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("records 读取失败：%s\n" % exc)
        return 2
    if not isinstance(records, list):
        sys.stderr.write("records.json 顶层必须是 list\n")
        return 2

    result = merge(records)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    sys.stderr.write("族合并完成：simple=%d，extended=%d，无优先权记录=%d\n"
                     % (len(result["simple_families"]),
                        len(result["extended_families"]),
                        len(result["records_without_priorities"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
