#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_apply.py — 基线建图与变更集应用（增量更新核心）。

子命令：
  init   用 Agent 编写的 baseline 候选构建 v1 图并封存（sealed，之后永不改写）。
  apply  把 changeset 的 ADD/MERGE/KEEP_DISTINCT/UPDATE_EVIDENCE/CONFLICT
         应用到 v1 的深拷贝上，产出 v2 当前图 + changes.json/jsonl + 人类可读台账。

铁律：
- 既有节点/边的 ID 永不改号；新记录只在撞键时按确定性顺序追加 _2、_3…；
- 没有任何操作会删除记录（MERGE 只把被吸收者记为别名+证据，CONFLICT 双方并存）；
- 应用前自动调用 kg_verify 的确定性校验，任何 ERROR 直接退出且不落盘。
"""
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_common as K
import kg_verify as V


# ---------------------------------------------------------------- 构建辅助

def _node_sort_key(nd, sources):
    ev = (nd.get("evidence") or [{}])[0]
    return (K.source_rank(sources, ev.get("source_id", "")),
            str(ev.get("paragraph_id", "")), K.norm_label(nd.get("label", "")))


def _edge_sort_key(ed, sources):
    ev = (ed.get("evidence") or [{}])[0]
    frm = ed.get("from")
    frm = frm.get("label") if isinstance(frm, dict) else str(frm)
    return (K.source_rank(sources, ev.get("source_id", "")),
            str(ev.get("paragraph_id", "")), str(ed.get("relation", "")), frm)


def _mk_node(cand, nid, version, note):
    return {
        "id": nid,
        "type": cand["type"],
        "label": cand["label"],
        "aliases": [],
        "evidence": K.dedupe_evidence(cand.get("evidence") or []),
        "status": "active",
        "history": [{"version": version, "op": "ADD", "note": note}],
    }


def _mk_edge(cand, eid, frm, to, version, note, status="active"):
    return {
        "id": eid,
        "relation": cand["relation"],
        "from": frm,
        "to": to,
        "attributes": cand.get("attributes") or {},
        "evidence": K.dedupe_evidence(cand.get("evidence") or []),
        "status": status,
        "history": [{"version": version, "op": "ADD", "note": note}],
    }


def _add_edge(graph, cand, version, note, op_results, registry, status="active"):
    frm, err = K.resolve_ref(cand.get("from"), graph, op_results)
    if err:
        return None, "from: " + err
    to, err = K.resolve_ref(cand.get("to"), graph, op_results)
    if err:
        return None, "to: " + err
    eid = K.unique_id(K.base_edge_id(cand["relation"], frm, to, cand.get("attributes")),
                      K.edge_anchor(cand["relation"], frm, to, cand.get("attributes"),
                                    cand.get("evidence")), registry)
    if eid in {e["id"] for e in graph["edges"]}:
        return eid, "DUPLICATE"  # 幂等：同锚点边已存在
    registry[eid] = K.edge_anchor(cand["relation"], frm, to, cand.get("attributes"),
                                  cand.get("evidence"))
    e = _mk_edge(cand, eid, frm, to, version, note, status=status)
    graph["edges"].append(e)
    return eid, None


# ---------------------------------------------------------------- init

def cmd_init(args):
    case = K.read_case(args.input_dir)
    sources = K.load_sources(args.input_dir, case)
    paras = K.load_paragraphs(args.input_dir, sources)
    source_ids = {s["source_id"] for s in sources}
    cands = K.load_json(args.candidates)
    errors, warnings = V.verify_candidates(cands, case, paras, source_ids)
    for w in warnings:
        print("WARN: " + w, file=sys.stderr)
    if errors:
        for e in errors:
            print("ERROR: " + e, file=sys.stderr)
        return 1

    registry = {}
    nodes = []
    for cand in sorted(cands.get("nodes", []), key=lambda c: _node_sort_key(c, sources)):
        anchor = K.node_anchor(cand["type"], cand["label"], cand.get("evidence"))
        nid = K.unique_id(K.base_node_id(cand["type"], cand["label"]), anchor, registry)
        registry[nid] = anchor
        nodes.append(_mk_node(cand, nid, "v1", "baseline 建图（primary 论文封存）"))

    graph = {"schema": K.SCHEMA_GRAPH, "case_id": cands.get("case_id") or case.get("case_id"),
             "version": "v1", "sealed": True, "sources": sources,
             "nodes": nodes, "edges": [], "registry": registry}
    label2id = {}
    for n in nodes:
        label2id.setdefault(K.norm_label(n["label"]), []).append(n["id"])

    edges = []
    for cand in sorted(cands.get("edges", []), key=lambda c: _edge_sort_key(c, sources)):
        frm_lab = cand.get("from")
        frm_lab = frm_lab.get("label") if isinstance(frm_lab, dict) else frm_lab
        to_lab = cand.get("to")
        to_lab = to_lab.get("label") if isinstance(to_lab, dict) else to_lab
        frm = label2id[K.norm_label(frm_lab)][0]
        to = label2id[K.norm_label(to_lab)][0]
        anchor = K.edge_anchor(cand["relation"], frm, to, cand.get("attributes"),
                               cand.get("evidence"))
        eid = K.unique_id(K.base_edge_id(cand["relation"], frm, to, cand.get("attributes")),
                          anchor, registry)
        registry[eid] = anchor
        edges.append(_mk_edge(cand, eid, frm, to, "v1", "baseline 建图（primary 论文封存）"))
    graph["edges"] = edges

    os.makedirs(args.work_dir, exist_ok=True)
    K.dump_json(graph, os.path.join(args.work_dir, "graph-v1.json"))
    K.dump_jsonl([dict(kind="node", **K.node_summary(n)) for n in nodes]
                 + [dict(kind="edge", **K.edge_summary(e)) for e in edges],
                 os.path.join(args.work_dir, "graph-v1.jsonl"))
    print("baseline v1 已封存: %d 节点, %d 边 -> %s"
          % (len(nodes), len(edges), os.path.join(args.work_dir, "graph-v1.json")))
    return 0


# ---------------------------------------------------------------- apply

def _apply_op(g2, op, seq, registry, op_results, sources):
    """返回 (change_record, error)。"""
    kind = op.get("op")
    ver = g2["version"]
    base_rec = {"seq": seq, "op": kind, "before": None, "after": None,
                "reason": op.get("justification") or op.get("reason") or "",
                "evidence": []}

    if kind == "ADD":
        if op.get("kind") == "node" or "node" in op:
            cand = op.get("node") or op.get("candidate")
            anchor = K.node_anchor(cand["type"], cand["label"], cand.get("evidence"))
            nid = K.unique_id(K.base_node_id(cand["type"], cand["label"]), anchor, registry)
            if nid in {n["id"] for n in g2["nodes"]}:
                base_rec.update(target=nid, note="幂等跳过：同锚点节点已存在")
                op_results["op:%d" % seq] = nid
                return base_rec, None
            registry[nid] = anchor
            node = _mk_node(cand, nid, ver, "changeset seq=%d 新增" % seq)
            g2["nodes"].append(node)
            op_results["op:%d" % seq] = nid
            base_rec.update(target=nid, after=K.node_summary(node),
                            evidence=node["evidence"])
            return base_rec, None
        cand = op.get("edge") or op.get("candidate")
        eid, err = _add_edge(g2, cand, ver, "changeset seq=%d 新增" % seq,
                             op_results, registry)
        if err == "DUPLICATE":
            base_rec.update(target=eid, note="幂等跳过：同锚点边已存在")
            op_results["op:%d" % seq] = eid
            return base_rec, None
        if err:
            return None, err
        op_results["op:%d" % seq] = eid
        e = K.find_edge(g2, eid)
        base_rec.update(target=eid, after=K.edge_summary(e), evidence=e["evidence"])
        return base_rec, None

    if kind == "MERGE":
        cand = op["candidate"]
        into_id, err = K.resolve_ref(op.get("into"), g2, op_results)
        if err:
            return None, err
        surv = K.find_node(g2, into_id)
        before = copy.deepcopy(K.node_summary(surv))
        surv["aliases"].append({"label": cand["label"],
                                "evidence": cand.get("evidence") or [],
                                "note": op.get("justification", "")})
        surv["evidence"] = K.dedupe_evidence(surv["evidence"] + (cand.get("evidence") or []))
        surv["history"].append({"version": ver, "op": "MERGE",
                                "note": "吸收别名 %r：%s" % (cand["label"],
                                                           op.get("justification", ""))})
        # 被吸收标签登记进 registry，保证同名候选再次出现时解析到幸存者（幂等）
        anchor = K.node_anchor(cand["type"], cand["label"], cand.get("evidence"))
        registry.setdefault("merged:" + K.norm_label(cand["label"]), anchor)
        op_results["op:%d" % seq] = into_id
        base_rec.update(target=into_id, before=before, after=K.node_summary(surv),
                        absorbed_label=cand["label"],
                        evidence=cand.get("evidence") or [])
        return base_rec, None

    if kind == "KEEP_DISTINCT":
        cand = op["candidate"]
        other_id, err = K.resolve_ref(op.get("distinct_from"), g2, op_results)
        if err:
            return None, err
        anchor = K.node_anchor(cand["type"], cand["label"], cand.get("evidence"))
        nid = K.unique_id(K.base_node_id(cand["type"], cand["label"]), anchor, registry)
        if nid in {n["id"] for n in g2["nodes"]}:
            op_results["op:%d" % seq] = nid
            base_rec.update(target=nid, note="幂等跳过：同锚点节点已存在")
            return base_rec, None
        registry[nid] = anchor
        node = _mk_node(cand, nid, ver, "changeset seq=%d 新增（保持区分）" % seq)
        node["related_but_distinct"] = [{"node": other_id, "reason": op.get("reason", "")}]
        g2["nodes"].append(node)
        other = K.find_node(g2, other_id)
        other.setdefault("related_but_distinct", []).append(
            {"node": nid, "reason": op.get("reason", "")})
        other["history"].append({"version": ver, "op": "KEEP_DISTINCT",
                                 "note": "与 %s 保持区分：%s" % (nid, op.get("reason", ""))})
        op_results["op:%d" % seq] = nid
        base_rec.update(target=nid, distinct_from=other_id,
                        after=K.node_summary(node), evidence=node["evidence"])
        return base_rec, None

    if kind == "UPDATE_EVIDENCE":
        tid, err = K.resolve_ref(op.get("target"), g2, op_results)
        if err:
            return None, err
        rec = K.find_node(g2, tid) or K.find_edge(g2, tid)
        if rec is None:
            return None, "target 既不是节点也不是边: %s" % tid
        summary = K.node_summary if "label" in rec else K.edge_summary
        before = copy.deepcopy(summary(rec))
        rec["evidence"] = K.dedupe_evidence(rec.get("evidence", [])
                                            + (op.get("add_evidence") or []))
        rec["history"].append({"version": ver, "op": "UPDATE_EVIDENCE",
                               "note": "追加 %d 条证据（只增不改）"
                                       % len(op.get("add_evidence") or [])})
        base_rec.update(target=tid, before=before, after=summary(rec),
                        evidence=op.get("add_evidence") or [])
        return base_rec, None

    if kind == "CONFLICT":
        cand = op["candidate"]
        old_id, err = K.resolve_ref(op.get("conflicts_with"), g2, op_results)
        if err:
            return None, err
        old = K.find_edge(g2, old_id)
        if old is None:
            return None, "conflicts_with 目标不是边: %s" % old_id
        before = copy.deepcopy(K.edge_summary(old))
        eid, err = _add_edge(g2, cand, ver, "changeset seq=%d 冲突边" % seq,
                             op_results, registry, status="conflicted")
        if err and err != "DUPLICATE":
            return None, err
        grp = old.get("conflict_group") or "cf_" + K.h8(sorted([old_id, eid]).__str__())
        old["status"] = "conflicted"
        old["conflict_group"] = grp
        old["history"].append({"version": ver, "op": "CONFLICT",
                               "note": "与 %s 冲突保留（不覆盖）：%s"
                                       % (eid, op.get("reason", ""))})
        new = K.find_edge(g2, eid)
        new["status"] = "conflicted"
        new["conflict_group"] = grp
        new["history"].append({"version": ver, "op": "CONFLICT",
                               "note": "与 %s 冲突保留（不覆盖）：%s"
                                       % (old_id, op.get("reason", ""))})
        op_results["op:%d" % seq] = eid
        base_rec.update(target=eid, conflicts_with=old_id, conflict_group=grp,
                        before=before, after=K.edge_summary(new),
                        evidence=cand.get("evidence") or [])
        return base_rec, None

    return None, "未知操作 %r" % kind


def cmd_apply(args):
    g1_path = os.path.join(args.work_dir, "graph-v1.json")
    if not os.path.exists(g1_path):
        print("ERROR: 缺少 %s，请先运行 kg_apply.py init" % g1_path, file=sys.stderr)
        return 2
    g1 = K.load_json(g1_path)  # 只读封存基线，绝不回写
    case = K.read_case(args.input_dir)
    sources = K.load_sources(args.input_dir, case)
    paras = K.load_paragraphs(args.input_dir, sources)
    source_ids = {s["source_id"] for s in sources}
    cs = K.load_json(args.changeset)
    errors, warnings = V.verify_changeset(cs, g1, paras, source_ids)
    for w in warnings:
        print("WARN: " + w, file=sys.stderr)
    if errors:
        for e in errors:
            print("ERROR: " + e, file=sys.stderr)
        return 1

    g2 = copy.deepcopy(g1)
    g2["version"] = "v2"
    g2["sealed"] = False
    g2["base_version"] = "v1"
    registry = dict(g1.get("registry") or {})
    op_results, changes = {}, []
    for seq, op in enumerate(cs.get("operations", []), 1):
        rec, err = _apply_op(g2, op, seq, registry, op_results, sources)
        if err:
            print("ERROR: operations[%d] %s: %s" % (seq - 1, op.get("op"), err),
                  file=sys.stderr)
            return 1
        changes.append(rec)
    g2["registry"] = registry

    summary = {}
    for c in changes:
        summary[c["op"]] = summary.get(c["op"], 0) + 1
    changes_doc = {"schema": K.SCHEMA_CHANGES, "case_id": g2.get("case_id"),
                   "base_version": "v1", "new_version": "v2",
                   "synthetic": bool(case.get("synthetic")),
                   "summary": summary, "operations": changes}

    K.dump_json(g2, os.path.join(args.work_dir, "graph-v2.json"))
    K.dump_jsonl([dict(kind="node", **K.node_summary(n)) for n in g2["nodes"]]
                 + [dict(kind="edge", **K.edge_summary(e)) for e in g2["edges"]],
                 os.path.join(args.work_dir, "graph-v2.jsonl"))
    K.dump_json(changes_doc, os.path.join(args.work_dir, "changes.json"))
    K.dump_jsonl(changes, os.path.join(args.work_dir, "changes.jsonl"))
    _write_ledger(changes_doc, g2, os.path.join(args.work_dir, "change-ledger.md"))
    print("变更集已应用: v1 -> v2, %d 个操作 %s；当前图 %d 节点 %d 边"
          % (len(changes), summary, len(g2["nodes"]), len(g2["edges"])))
    return 0


def _write_ledger(changes_doc, g2, path):
    L = []
    L.append("# 变更台账（change ledger）%s" %
             ("【SYNTHETIC 合成示例】" if changes_doc.get("synthetic") else ""))
    L.append("")
    L.append("- case_id: %s" % changes_doc.get("case_id"))
    L.append("- 版本: %s → %s（基线封存不改写，所有变更为追加式）"
             % (changes_doc["base_version"], changes_doc["new_version"]))
    L.append("- 操作统计: %s" % changes_doc.get("summary"))
    L.append("")
    for c in changes_doc["operations"]:
        L.append("## seq %d · %s → %s" % (c["seq"], c["op"], c.get("target")))
        if c.get("reason"):
            L.append("- 依据/理由: %s" % c["reason"])
        if c.get("absorbed_label"):
            L.append("- 被吸收别名: %s（幸存者保留原 ID，别名与证据追加，不删除记录）"
                     % c["absorbed_label"])
        if c.get("distinct_from"):
            L.append("- 与 %s 保持区分（同名/通用术语不强制合并）" % c["distinct_from"])
        if c.get("conflicts_with"):
            L.append("- 与 %s 冲突，conflict_group=%s；两条边都保留，均未覆盖"
                     % (c["conflicts_with"], c.get("conflict_group")))
        if c.get("note"):
            L.append("- 备注: %s" % c["note"])
        for ev in c.get("evidence") or []:
            L.append("- 证据 [%s/%s]: \"%s\""
                     % (ev.get("source_id"), ev.get("paragraph_id"), ev.get("quote")))
        L.append("")
    L.append("## 当前图规模")
    L.append("- 节点 %d，边 %d（含 conflicted 状态边，双方证据并列保留）"
             % (len(g2["nodes"]), len(g2["edges"])))
    L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser(description="基线建图 / 变更集应用")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("init", help="构建并封存 baseline v1")
    p1.add_argument("--input-dir", required=True)
    p1.add_argument("--candidates", required=True)
    p1.add_argument("--work-dir", required=True)
    p2 = sub.add_parser("apply", help="应用 changeset 生成 v2")
    p2.add_argument("--input-dir", required=True)
    p2.add_argument("--work-dir", required=True)
    p2.add_argument("--changeset", required=True)
    args = ap.parse_args(argv)
    return cmd_init(args) if args.cmd == "init" else cmd_apply(args)


if __name__ == "__main__":
    sys.exit(main())
