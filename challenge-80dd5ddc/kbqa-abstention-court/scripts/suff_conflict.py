#!/usr/bin/env python3
"""suff_conflict.py — 充分性法庭第 3 步：跨文件/跨版本冲突登记（确定性，stdlib-only）。

基于 suff_index 预抽的数值事实，检测"同一语境键、不同数值"的冲突：
两个文件的 facts 中，语境键高度相似（token 集合 Jaccard ≥ 0.5 或互为子串）
而数值不同，即登记为冲突候选，附双方坐标（file_id:L行）与原文。
冲突不是结论错误——历史版本与当前版本本来就会不同——但它是充分性裁决的
必要输入：答案必须指明采用哪个来源、为什么。退出码恒 0。
"""
import argparse
import json
import os
import re
import sys
import time


def key_tokens(key):
    return set(re.sub(r"[^\w一-鿿]+", " ", key.lower()).split())


def similar(k1, k2):
    if not k1 or not k2:
        return False
    if k1 in k2 or k2 in k1:
        return len(k1) >= 4 and len(k2) >= 4
    t1, t2 = key_tokens(k1), key_tokens(k2)
    if not t1 or not t2:
        return False
    return len(t1 & t2) / len(t1 | t2) >= 0.5


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.work, "suff_index.json"), encoding="utf-8") as f:
        index = json.load(f)

    facts = []  # (file_id, fact)
    for e in index["files"]:
        if e["text_status"] != "ok":
            continue
        fp = os.path.join(a.work, os.path.dirname(e["extracted"]),
                          e["file_id"] + ".facts.json")
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8") as f:
            for fact in json.load(f):
                if fact.get("key"):
                    facts.append((e["file_id"], e["relpath"], fact))

    conflicts = []
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            f1, r1, x1 = facts[i]
            f2, r2, x2 = facts[j]
            if f1 == f2:
                continue
            if x1["unit"] != x2["unit"]:
                continue
            if x1["value"] == x2["value"]:
                continue
            if similar(x1["key"], x2["key"]):
                conflicts.append({
                    "subject": x1["key"] or x2["key"], "unit": x1["unit"],
                    "side_a": {"file_id": f1, "relpath": r1, "value": x1["value"],
                               "line": x1["line"], "context": x1["context"]},
                    "side_b": {"file_id": f2, "relpath": r2, "value": x2["value"],
                               "line": x2["line"], "context": x2["context"]},
                    "note": "同一语境数值不一致；若为版本差异，须以当前版本为准并明示"})
    out = {"schema": "kbqa-abstention-court/conflict-registry/v1",
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "conflicts": conflicts}
    with open(os.path.join(a.out, "conflict_registry.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"conflicts": len(conflicts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
