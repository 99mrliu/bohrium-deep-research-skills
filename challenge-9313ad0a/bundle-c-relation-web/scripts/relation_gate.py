#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""relation_gate.py — 思维导图关系边的证据与形式校验闸门（Python 3.10+ 标准库）。

用法：
    python3 relation_gate.py --nodes nodes.json --relations relations.json \
        --material pages.jsonl --report gate_report.json --rejected rejected.json

输入：
    nodes.json      {"nodes":[{"id","label","kind","parent"}]}
    relations.json  {"relations":[{"id","from","to","type","basis",
                                   "evidence":{"file","page","quote"}|null,
                                   "note":str}]}
    pages.jsonl     每行 {"file","page","text"}

输出：
    gate_report.json {"summary":{"relations":N,"accepted":a,"rejected":r,"warnings":w},
                      "accepted":[ids],
                      "findings":[{"relation_id","check","verdict","detail"}]}
    rejected.json    {"rejected":[{"relation":<原对象>,"reasons":[...]}]}

退出码：存在虚构证据（fabricated）或时间环（temporal cycle）时为 1，否则为 0。
全部输出按确定顺序生成（无随机性、无时间戳）。
"""

import argparse
import json
import os
import re
import sys
import unicodedata

RELATION_TYPES = [
    "causes", "depends_on", "supports", "contrasts_with", "conflicts_with",
    "cites", "precedes", "addresses", "measures", "mitigates",
]
SYMMETRIC_TYPES = {"contrasts_with", "conflicts_with"}

REJECT = "reject"
WARNING = "warning"
ERROR = "error"
OK = "ok"


def normalize_text(s):
    """折叠空白、统一 Unicode 破折号与引号，用于逐字证据比对。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    # 统一各类破折号/连字符
    for ch in "‐‑‒–—―−":
        s = s.replace(ch, "-")
    # 统一弯引号为直引号
    for ch in "‘’‚‛":
        s = s.replace(ch, "'")
    for ch in "“”„‟":
        s = s.replace(ch, '"')
    # 折叠一切空白（含换行、制表、不间断空格已由 NFKC 转换）
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def load_nodes(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes", [])
    by_id = {}
    for n in nodes:
        by_id[n["id"]] = n
    return by_id


def load_relations(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("relations", [])


def load_material(path):
    """返回 {(file, page): normalized_text} 以及 file -> sorted page list。"""
    pages = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = (rec["file"], rec["page"])
            text = normalize_text(rec.get("text", ""))
            pages[key] = (pages.get(key, "") + " " + text).strip()
    # 证据中常写裸文件名，而 pages.jsonl 记录调用时传入的路径；
    # 为基本文件名建立别名（同名不同目录时保留先出现者，属已知限制）。
    for (fname, pno) in list(pages):
        base = os.path.basename(fname)
        if base and base != fname:
            pages.setdefault((base, pno), pages[(fname, pno)])
    return pages


def build_parent_map(nodes_by_id):
    return {nid: (n.get("parent") or None) for nid, n in nodes_by_id.items()}


def ancestors_of(nid, parent_map):
    """从 nid 沿 parent 链向上的全部祖先（不含自身），防环。"""
    result = set()
    seen = set()
    cur = parent_map.get(nid)
    while cur is not None and cur not in seen:
        seen.add(cur)
        result.add(cur)
        cur = parent_map.get(cur)
    return result


def descendants_of(nid, parent_map):
    children = {}
    for k, p in parent_map.items():
        if p is not None:
            children.setdefault(p, []).append(k)
    result = set()
    stack = list(children.get(nid, []))
    while stack:
        cur = stack.pop()
        if cur in result:
            continue
        result.add(cur)
        stack.extend(children.get(cur, []))
    return result


def check_relations(nodes_by_id, relations, pages):
    findings = []
    rejected = []
    accepted_ids = []
    parent_map = build_parent_map(nodes_by_id)
    seen_edges = {}  # (from,to,type) -> first relation id

    reject_flags = {}  # relation id -> bool（本次扫描是否被拒绝）

    for rel in relations:
        rid = rel.get("id", "")
        reasons = []
        frm, to = rel.get("from"), rel.get("to")
        rtype = rel.get("type")
        basis = rel.get("basis")

        # (1) 端点存在
        if frm not in nodes_by_id or to not in nodes_by_id:
            missing = [x for x in (frm, to) if x not in nodes_by_id]
            findings.append({"relation_id": rid, "check": "endpoints",
                             "verdict": REJECT,
                             "detail": "端点不存在: %s" % ", ".join(map(str, missing))})
            reasons.append("端点不存在: %s" % ", ".join(map(str, missing)))

        # (2) 类型在词表内
        if rtype not in RELATION_TYPES:
            findings.append({"relation_id": rid, "check": "type_vocabulary",
                             "verdict": REJECT,
                             "detail": "关系类型不在词表内: %r" % rtype})
            reasons.append("关系类型不在词表内: %r" % rtype)

        # (3) 无自环
        if frm is not None and frm == to:
            findings.append({"relation_id": rid, "check": "self_loop",
                             "verdict": REJECT,
                             "detail": "自环: from == to == %r" % frm})
            reasons.append("自环")

        # (4) 层级冗余：from 是 to 的祖先或后代
        if frm in nodes_by_id and to in nodes_by_id and frm != to:
            if to in ancestors_of(frm, parent_map) or frm in ancestors_of(to, parent_map):
                findings.append({"relation_id": rid, "check": "hierarchy_redundant",
                                 "verdict": REJECT,
                                 "detail": "from 与 to 存在父子层级关系（%r 与 %r 互为祖先/后代），"
                                           "该内容属于主题树而非横向边" % (frm, to)})
                reasons.append("层级冗余：端点互为祖先/后代")

        # (5)(6) 证据与依据
        if basis == "fact":
            ev = rel.get("evidence")
            if not ev or not isinstance(ev, dict) or not (ev.get("quote") or "").strip():
                findings.append({"relation_id": rid, "check": "evidence",
                                 "verdict": REJECT,
                                 "detail": "basis=fact 但 evidence 缺失或引句为空"})
                reasons.append("basis=fact 但证据缺失")
            else:
                q = normalize_text(ev.get("quote"))
                key = (ev.get("file"), ev.get("page"))
                if key in pages and q in pages[key]:
                    pass  # 逐字命中
                else:
                    # 判定 fabricated 或 mislocated
                    hit_pages = [pg for (fl, pg), txt in pages.items()
                                 if fl == ev.get("file") and q in txt]
                    if hit_pages:
                        findings.append({"relation_id": rid, "check": "evidence_verbatim",
                                         "verdict": REJECT,
                                         "detail": "mislocated: 引句未出现在 %s 第 %s 页，"
                                                   "而出现于第 %s 页"
                                                   % (ev.get("file"), ev.get("page"),
                                                      ", ".join(str(p) for p in sorted(hit_pages, key=str)))})
                        reasons.append("mislocated: 引句在所引页不存在，正确页为 %s"
                                       % ", ".join(str(p) for p in sorted(hit_pages, key=str)))
                    else:
                        # 同名文件不存在亦视为 fabricated（材料中无任何出处）
                        findings.append({"relation_id": rid, "check": "evidence_verbatim",
                                         "verdict": ERROR,
                                         "detail": "fabricated: 引句在全部材料中均不存在: %r"
                                                   % ev.get("quote")})
                        reasons.append("fabricated: 引句在材料中不存在")
        elif basis == "inference":
            if not (rel.get("note") or "").strip():
                findings.append({"relation_id": rid, "check": "inference_note",
                                 "verdict": REJECT,
                                 "detail": "basis=inference 但 note 为空"})
                reasons.append("basis=inference 但 note 为空")
        else:
            findings.append({"relation_id": rid, "check": "basis",
                             "verdict": REJECT,
                             "detail": "basis 必须为 fact 或 inference: %r" % basis})
            reasons.append("basis 非法: %r" % basis)

        # (7) 重复边 (from,to,type)：保留首条，标记其余
        ekey = (frm, to, rtype)
        if ekey in seen_edges:
            findings.append({"relation_id": rid, "check": "duplicate_edge",
                             "verdict": REJECT,
                             "detail": "重复边 (from,to,type)，首条为 %r" % seen_edges[ekey]})
            reasons.append("重复边，首条为 %r" % seen_edges[ekey])
        else:
            seen_edges[ekey] = rid

        if reasons:
            rejected.append({"relation": rel, "reasons": reasons})
            reject_flags[rid] = True
        else:
            accepted_ids.append(rid)
            reject_flags[rid] = False

    # (8) 对称语义：contrasts_with / conflicts_with 应互逆；缺失仅警告（不拒绝）
    accepted_edge_set = {(r.get("from"), r.get("to"), r.get("type"))
                         for r in relations if not reject_flags.get(r.get("id"), True)}
    for (frm, to, rtype) in sorted(accepted_edge_set, key=str):
        if rtype in SYMMETRIC_TYPES and (to, frm, rtype) not in accepted_edge_set:
            findings.append({"relation_id": seen_edges.get((frm, to, rtype), ""),
                             "check": "symmetry",
                             "verdict": WARNING,
                             "detail": "%s 边 (%r -> %r) 缺少互逆边 (%r -> %r)"
                                       % (rtype, frm, to, to, frm)})

    # (9) 时间无环：被接受的 precedes 边构成的子图必须是 DAG
    prec_edges = [(r.get("from"), r.get("to"), r.get("id"))
                  for r in relations
                  if r.get("type") == "precedes" and not reject_flags.get(r.get("id"), True)]
    cycle = find_cycle(prec_edges)
    if cycle:
        cyc_nodes, cyc_ids = cycle
        for rid in cyc_ids:
            findings.append({"relation_id": rid, "check": "temporal_acyclicity",
                             "verdict": ERROR,
                             "detail": "时间环: precedes 子图存在环 %s"
                                       % " -> ".join(cyc_nodes)})
            # 将环上各边移入 rejected
            rel_obj = next((r for r in relations if r.get("id") == rid), None)
            if rel_obj is not None:
                existing = next((x for x in rejected if x["relation"].get("id") == rid), None)
                if existing is None:
                    rejected.append({"relation": rel_obj,
                                     "reasons": ["时间环: precedes 子图存在环"]})
                else:
                    existing["reasons"].append("时间环: precedes 子图存在环")
            if rid in accepted_ids:
                accepted_ids.remove(rid)

    return findings, rejected, accepted_ids


def find_cycle(edges):
    """在 (from,to,rid) 边列表中找一个环。返回 (环节点序列, 环上关系 id 列表) 或 None。"""
    adj = {}
    for frm, to, rid in edges:
        adj.setdefault(frm, []).append((to, rid))
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}
    path = []  # [(node, rid_used_to_enter)]

    def dfs(u, via):
        color[u] = GRAY
        path.append((u, via))
        for v, rid in adj.get(u, []):
            if color.get(v, WHITE) == GRAY:
                idx = next(i for i, (n, _) in enumerate(path) if n == v)
                cyc_nodes = [n for n, _ in path[idx:]] + [v]
                cyc_ids = [r for _, r in path[idx + 1:]] + [rid]
                return (cyc_nodes, cyc_ids)
            if color.get(v, WHITE) == WHITE:
                res = dfs(v, rid)
                if res:
                    return res
        path.pop()
        color[u] = BLACK
        return None

    for node in sorted(adj.keys()):
        if color.get(node, WHITE) == WHITE:
            res = dfs(node, None)
            if res:
                return res
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="关系边证据与形式校验闸门")
    ap.add_argument("--nodes", required=True)
    ap.add_argument("--relations", required=True)
    ap.add_argument("--material", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--rejected", required=True)
    args = ap.parse_args(argv)

    nodes_by_id = load_nodes(args.nodes)
    relations = load_relations(args.relations)
    pages = load_material(args.material)

    findings, rejected, accepted_ids = check_relations(nodes_by_id, relations, pages)

    rejected_ids = {x["relation"].get("id") for x in rejected}
    accepted_ids = [rid for rid in accepted_ids if rid not in rejected_ids]

    n_warn = sum(1 for f in findings if f["verdict"] == WARNING)
    report = {
        "summary": {
            "relations": len(relations),
            "accepted": len(accepted_ids),
            "rejected": len(rejected),
            "warnings": n_warn,
        },
        "accepted": accepted_ids,
        "findings": findings,
    }

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(args.rejected, "w", encoding="utf-8") as f:
        json.dump({"rejected": rejected}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    has_fatal = any(f["verdict"] == ERROR for f in findings)
    return 1 if has_fatal else 0


if __name__ == "__main__":
    sys.exit(main())
