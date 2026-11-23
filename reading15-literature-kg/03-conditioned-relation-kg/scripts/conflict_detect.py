#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冲突检测器：同源或跨源冲突一律保留，绝不静默仲裁。

检测两类冲突：
  K1 数值冲突：同 (subject, relation, object, 条件签名) 下，kind+unit 相同
     而 value 不同的 measurement（典型：两篇论文对同一模型在同一
     数据集/指标/条件下报告了不同数值）。
  K2 极性冲突：同 (subject, object, 条件签名) 下存在互相矛盾的关系
     （supports vs contradicts，或 outperforms 方向相反）。
输出 conflicts.json；被卷入的边保持原样并加注 in_conflict=true。
用法：
  python3 conflict_detect.py --relations relations_linted.json --out conflicts.json
"""
import argparse
import sys

from relation_common import condition_signature, load_json, dump_json

OPPOSED = {frozenset(("supports", "contradicts"))}


def detect(edges):
    conflicts = []
    # K1 数值冲突
    groups = {}
    for e in edges:
        meas = e.get("measurement") or {}
        if meas.get("value") is None:
            continue
        key = (e.get("subject"), e.get("relation"), e.get("object"),
               condition_signature(e.get("conditions")),
               meas.get("kind"), meas.get("unit"))
        groups.setdefault(key, []).append(e)
    for key, grp in groups.items():
        values = {g["measurement"]["value"] for g in grp}
        if len(values) > 1:
            conflicts.append({
                "kind": "K1_numeric",
                "status": "unresolved",
                "policy": "保留全部冲突记录，不取平均、不选赢家",
                "signature": {"subject": key[0], "relation": key[1],
                              "object": key[2], "conditions": key[3],
                              "kind": key[4], "unit": key[5]},
                "edges": [{"edge_id": g["edge_id"],
                           "value": g["measurement"]["value"],
                           "sources": [ev.get("source_id")
                                       for ev in g.get("evidence", [])]}
                          for g in grp],
            })
    # K2 极性/方向冲突
    pairs = {}
    for e in edges:
        key = (e.get("subject"), e.get("object"),
               condition_signature(e.get("conditions")))
        pairs.setdefault(key, []).append(e)
    for key, grp in pairs.items():
        rels = {g.get("relation") for g in grp}
        if any(o <= rels for o in OPPOSED):
            conflicts.append({
                "kind": "K2_polarity",
                "status": "unresolved",
                "policy": "supports/contradicts 并存时全部保留",
                "signature": {"subject": key[0], "object": key[1],
                              "conditions": key[2]},
                "edges": [{"edge_id": g["edge_id"], "relation": g.get("relation"),
                           "sources": [ev.get("source_id")
                                       for ev in g.get("evidence", [])]}
                          for g in grp if g.get("relation") in
                          ("supports", "contradicts")],
            })
        # outperforms 反向冲突：A outperforms B 与 B outperforms A 同条件
    fwd = {}
    for e in edges:
        if e.get("relation") == "outperforms":
            key = (frozenset((e.get("subject"), e.get("object"))),
                   condition_signature(e.get("conditions")))
            fwd.setdefault(key, []).append(e)
    for key, grp in fwd.items():
        dirs = {(g.get("subject"), g.get("object")) for g in grp}
        if len(dirs) > 1:
            conflicts.append({
                "kind": "K2_direction",
                "status": "unresolved",
                "policy": "反向 outperforms 并存时全部保留并显式标注",
                "signature": {"node_pair": sorted(key[0]), "conditions": key[1]},
                "edges": [{"edge_id": g["edge_id"],
                           "direction": "%s->%s" % (g.get("subject"), g.get("object")),
                           "sources": [ev.get("source_id")
                                       for ev in g.get("evidence", [])]}
                          for g in grp],
            })
    return conflicts


def main(argv=None):
    ap = argparse.ArgumentParser(description="关系冲突检测器")
    ap.add_argument("--relations", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    doc = load_json(args.relations)
    edges = doc.get("edges", [])
    conflicts = detect(edges)
    in_conflict = {c["edge_id"] for c in conflicts for c in c["edges"]}
    for e in edges:
        if e.get("edge_id") in in_conflict:
            e["in_conflict"] = True
    dump_json(doc, args.relations)  # 回写 in_conflict 标记
    dump_json({"n_conflicts": len(conflicts),
               "policy": "源内/跨源冲突一律保留，绝不静默解决",
               "conflicts": conflicts}, args.out)
    print("conflicts: %d found -> %s" % (len(conflicts), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
