#!/usr/bin/env python3
"""merge_family.py — 专利同族归并：简单族与扩展族双口径（仅标准库）。

输入：一个或多个 JSON 文件，每个含 records 列表：
  [{"id": ..., "numbers": ["US...", ...], "priorities": ["US15/654,321", ...],
    "title": ..., "locator": "file:line"}]
用法：
  python3 merge_family.py --records rec1.json [rec2.json ...] --out family.json
口径（详见 rules/family_scope.md）：
  简单族 simple  = 优先权集合完全相同；
  扩展族 extended = 共享至少一项优先权（并查集连通分量）。
仅依据观察到的号码/优先权归并；优先权缺失的记录单列并告警，
不据此断言"完整同族"或"等效权利要求范围"。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patent_numbers


def norm_priority(raw, warnings, rec_id):
    p = patent_numbers.normalize(raw)
    if not p["ok"]:
        warnings.append({"record": rec_id, "raw": raw,
                         "warning": "优先权号无法规范化，该记录不计入任何优先权键"})
        return None
    # 优先权跨种类可比：用 国家+序号 作为比较键（忽略 app/pub 之分）
    return "%s|%s" % (p["country"], p["serial"])


def load_records(paths):
    records, warnings = [], []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            warnings.append({"file": path, "warning": "记录文件无法读取: %s" % e})
            continue
        for rec in data.get("records", data if isinstance(data, list) else []):
            rec = dict(rec)
            rec.setdefault("id", "%s#%d" % (os.path.basename(path), len(records)))
            rec["_source_file"] = path
            records.append(rec)
    return records, warnings


def merge(records):
    warnings = []
    # 去重：按规范化公开/授权号
    seen_keys = {}
    dedup, dup_events = [], []
    for rec in records:
        keys = set()
        for raw in rec.get("numbers", []):
            p = patent_numbers.normalize(raw)
            if p["ok"]:
                keys.add(p["key"])
        rec["_keys"] = sorted(keys)
        dup_of = next((k for k in keys if k in seen_keys), None)
        if dup_of is not None:
            dup_events.append({"key": dup_of, "kept": seen_keys[dup_of],
                               "dropped": rec["id"],
                               "note": "同一规范化号码重复出现，保留首条，双方 locator 可追溯"})
            # 冲突字段检测：同号不同题名
            continue
        for k in keys:
            seen_keys[k] = rec["id"]
        dedup.append(rec)

    # 冲突字段：同号不同题名（在去重前比较）
    conflicts = []
    by_key = {}
    for rec in records:
        for k in rec.get("_keys", []):
            if k in by_key:
                prev = by_key[k]
                t1, t2 = prev.get("title"), rec.get("title")
                if t1 and t2 and t1 != t2:
                    conflicts.append({"key": k, "titles": [t1, t2],
                                      "records": [prev["id"], rec["id"]],
                                      "locators": [prev.get("locator"), rec.get("locator")],
                                      "note": "同一号码对应不同题名，字段冲突，保留双方定位"})
            else:
                by_key[k] = rec

    # 优先权键
    no_prio = []
    for rec in dedup:
        pk = set()
        for raw in rec.get("priorities", []):
            k = norm_priority(raw, warnings, rec["id"])
            if k:
                pk.add(k)
        rec["_pkeys"] = sorted(pk)
        if not pk:
            no_prio.append(rec["id"])

    # 简单族：优先权集合完全相同
    simple = {}
    for rec in dedup:
        if rec["_pkeys"]:
            simple.setdefault(tuple(rec["_pkeys"]), []).append(rec["id"])
    simple_families = [sorted(v) for v in simple.values()]

    # 扩展族：共享≥1 优先权的并查集
    parent = {r["id"]: r["id"] for r in dedup}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    prio_owner = {}
    for rec in dedup:
        for pk in rec["_pkeys"]:
            if pk in prio_owner:
                union(prio_owner[pk], rec["id"])
            else:
                prio_owner[pk] = rec["id"]
    ext = {}
    for rec in dedup:
        ext.setdefault(find(rec["id"]), []).append(rec["id"])
    extended_families = [sorted(v) for v in ext.values()]

    if no_prio:
        warnings.append({"records": no_prio,
                         "warning": "以下记录无可用优先权，族归属不确定；"
                                    "本结果仅为观察到的链接，不构成完整同族，"
                                    "不代表等效权利要求范围"})
    return {"scope_note": {
                "simple": "简单族口径：优先权集合完全相同",
                "extended": "扩展族口径：共享至少一项优先权的连通分量",
                "limitation": "仅基于输入记录中观察到的优先权/号码链接；"
                              "未观察到的族成员不存在于本结果，不得据此声明完整同族"},
            "records": [{"id": r["id"], "numbers": r.get("numbers", []),
                         "normalized_keys": r["_keys"],
                         "priority_keys": r["_pkeys"],
                         "title": r.get("title"), "locator": r.get("locator"),
                         "source_file": r["_source_file"]} for r in dedup],
            "simple_families": simple_families,
            "extended_families": extended_families,
            "dedup_events": dup_events, "conflicts": conflicts,
            "records_without_priority": no_prio, "warnings": warnings}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv[1:])
    records, w = load_records(args.records)
    result = merge(records)
    result["warnings"] = w + result["warnings"]
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"records": len(result["records"]),
                      "simple_families": len(result["simple_families"]),
                      "extended_families": len(result["extended_families"]),
                      "conflicts": len(result["conflicts"]),
                      "warnings": len(result["warnings"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
