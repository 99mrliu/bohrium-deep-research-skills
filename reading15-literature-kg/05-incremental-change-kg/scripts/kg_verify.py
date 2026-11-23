#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_verify.py — 确定性校验器。

对 Agent 编写的语义候选（baseline-candidates）与变更集（changeset）做纯机器校验：
1. 每条证据的 source_id 必须存在于 corpus-manifest（或兜底来源表）；
2. paragraph_id 必须存在于该来源的 JATS 段落表；
3. quote 经空白规范化后必须是该段落原文的精确子串，且长度 <= 280 字符；
4. 禁止 evidence 中出现 page 字段（本包无 PDF 页码，不得自称页码）；
5. 节点类型必须在词表内；关系名必须 snake_case；
6. 变更集操作语义：MERGE 的通用别名防护、CONFLICT/KEEP_DISTINCT/UPDATE_EVIDENCE
   的目标存在性与理由长度。

任何 ERROR 退出码为 1，且不写任何图文件。校验不含模型调用、无随机性。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_common as K

GENERIC_NORMS = {K.norm_label(g) for g in K.GENERIC_TERMS}
OPS = {"ADD", "MERGE", "KEEP_DISTINCT", "UPDATE_EVIDENCE", "CONFLICT"}


def check_evidence(ev, paras, source_ids, where, errors):
    if not isinstance(ev, dict):
        errors.append("%s: evidence 必须是对象" % where)
        return
    if "page" in ev:
        errors.append("%s: 禁止 page 字段——本包无 PDF 页码，定位只能用 JATS paragraph_id" % where)
    sid = ev.get("source_id")
    pid = ev.get("paragraph_id")
    quote = ev.get("quote")
    if sid not in source_ids:
        errors.append("%s: 未知 source_id=%r（不在 corpus-manifest）" % (where, sid))
        return
    if (sid, pid) not in paras:
        errors.append("%s: 来源 %s 中不存在 paragraph_id=%r" % (where, sid, pid))
        return
    if not quote:
        errors.append("%s: 缺少 quote" % where)
        return
    if len(quote) > K.MAX_QUOTE_LEN:
        errors.append("%s: quote 超过 %d 字符，请截取精确短引" % (where, K.MAX_QUOTE_LEN))
        return
    if K.norm_ws(quote) not in K.norm_ws(paras[(sid, pid)]["text"]):
        errors.append("%s: quote 未命中 %s/%s 原文（逐字不匹配）: %r"
                      % (where, sid, pid, quote[:80]))


def verify_node(nd, where, paras, source_ids, errors, warnings):
    if not isinstance(nd, dict):
        errors.append("%s: 节点必须是对象" % where)
        return
    t = nd.get("type")
    if t not in K.NODE_TYPES:
        errors.append("%s: 非法节点类型 %r，允许值: %s"
                      % (where, t, ",".join(K.NODE_TYPES)))
    if not nd.get("label"):
        errors.append("%s: 缺少 label" % where)
    evs = nd.get("evidence") or []
    if not evs:
        errors.append("%s: 实质节点必须至少绑定一条证据" % where)
    for j, ev in enumerate(evs):
        check_evidence(ev, paras, source_ids, "%s.evidence[%d]" % (where, j), errors)


def verify_edge(ed, where, paras, source_ids, errors, warnings):
    if not isinstance(ed, dict):
        errors.append("%s: 边必须是对象" % where)
        return
    rel = ed.get("relation")
    if not rel or not K.REL_RE.match(rel):
        errors.append("%s: relation 必须为 snake_case，得到 %r" % (where, rel))
    if not ed.get("from") or not ed.get("to"):
        errors.append("%s: 边缺少 from/to 端点" % where)
    evs = ed.get("evidence") or []
    if not evs:
        errors.append("%s: 实质边必须至少绑定一条证据" % where)
    for j, ev in enumerate(evs):
        check_evidence(ev, paras, source_ids, "%s.evidence[%d]" % (where, j), errors)


def verify_candidates(cands, case, paras, source_ids):
    errors, warnings = [], []
    cid_c = cands.get("case_id")
    if case.get("case_id") and cid_c and cid_c != case["case_id"]:
        errors.append("case_id 不一致: candidates=%r case=%r" % (cid_c, case["case_id"]))
    labels = {}
    for i, nd in enumerate(cands.get("nodes", [])):
        verify_node(nd, "nodes[%d]" % i, paras, source_ids, errors, warnings)
        nl = K.norm_label(nd.get("label", "")) if isinstance(nd, dict) else ""
        if nl:
            labels[nl] = labels.get(nl, 0) + 1
    for nl, cnt in sorted(labels.items()):
        if cnt > 1:
            warnings.append("baseline 内同名候选 %r 出现 %d 次，将按确定性顺序追加 _2/_3 后缀"
                            % (nl, cnt))
    cand_labels = set(labels.keys())
    for i, ed in enumerate(cands.get("edges", [])):
        where = "edges[%d]" % i
        verify_edge(ed, where, paras, source_ids, errors, warnings)
        if not isinstance(ed, dict):
            continue
        for ep in ("from", "to"):
            ref = ed.get(ep)
            lab = ref.get("label") if isinstance(ref, dict) else ref
            if isinstance(lab, str) and K.norm_label(lab) not in cand_labels:
                errors.append("%s.%s: 端点标签 %r 不在候选节点中" % (where, ep, lab))
    return errors, warnings


def _check_generic_merge(cand_label, into_label, op, where, errors):
    """通用别名防护：通用术语标签不能仅凭同名强制合并。"""
    nl = K.norm_label(cand_label)
    if nl in GENERIC_NORMS and not op.get("allow_generic"):
        errors.append(
            "%s: 标签 %r 命中通用术语表，禁止默认 MERGE；若确有跨篇同一实体的显式证据，"
            "须设 allow_generic=true 并在 justification 中引用证据" % (where, cand_label))
    if (K.norm_label(cand_label) == K.norm_label(into_label)
            and not op.get("justification")):
        errors.append("%s: 同名合并也必须给出 justification（合并依据）" % where)


def verify_changeset(cs, graph, paras, source_ids):
    errors, warnings = [], []
    if case_mismatch(cs, graph):
        errors.append(case_mismatch(cs, graph))
    for i, op in enumerate(cs.get("operations", [])):
        where = "operations[%d]" % i
        if not isinstance(op, dict):
            errors.append("%s: 操作必须是对象" % where)
            continue
        kind = op.get("op")
        if kind not in OPS:
            errors.append("%s: 未知操作 %r，允许: %s" % (where, kind, sorted(OPS)))
            continue
        if kind == "ADD":
            if op.get("kind") == "node" or "node" in op:
                verify_node(op.get("node", op.get("candidate")), where + ".node",
                            paras, source_ids, errors, warnings)
            elif op.get("kind") == "edge" or "edge" in op:
                verify_edge(op.get("edge", op.get("candidate")), where + ".edge",
                            paras, source_ids, errors, warnings)
            else:
                errors.append("%s: ADD 需要 kind=node|edge" % where)
        elif kind == "MERGE":
            cand = op.get("candidate") or {}
            verify_node(cand, where + ".candidate", paras, source_ids, errors, warnings)
            into_id, err = K.resolve_ref(op.get("into"), graph)
            if err:
                errors.append("%s.into: %s" % (where, err))
            else:
                surv = K.find_node(graph, into_id)
                if surv is None:
                    errors.append("%s.into: 目标 %s 不是节点" % (where, into_id))
                else:
                    _check_generic_merge(cand.get("label", ""), surv.get("label", ""),
                                         op, where, errors)
            just = op.get("justification") or ""
            if len(just) < 20:
                errors.append("%s: MERGE 必须给出 >=20 字符的合并依据 justification" % where)
        elif kind == "KEEP_DISTINCT":
            cand = op.get("candidate") or {}
            verify_node(cand, where + ".candidate", paras, source_ids, errors, warnings)
            _, err = K.resolve_ref(op.get("distinct_from"), graph)
            if err:
                errors.append("%s.distinct_from: %s" % (where, err))
            if len(op.get("reason") or "") < 20:
                errors.append("%s: KEEP_DISTINCT 必须给出 >=20 字符的区分理由 reason" % where)
        elif kind == "UPDATE_EVIDENCE":
            tid, err = K.resolve_ref(op.get("target"), graph)
            if err:
                errors.append("%s.target: %s" % (where, err))
            evs = op.get("add_evidence") or []
            if not evs:
                errors.append("%s: UPDATE_EVIDENCE 需要非空 add_evidence" % where)
            for j, ev in enumerate(evs):
                check_evidence(ev, paras, source_ids,
                               "%s.add_evidence[%d]" % (where, j), errors)
        elif kind == "CONFLICT":
            verify_edge(op.get("candidate") or {}, where + ".candidate",
                        paras, source_ids, errors, warnings)
            eid, err = K.resolve_ref(op.get("conflicts_with"), graph)
            if err:
                errors.append("%s.conflicts_with: %s" % (where, err))
            elif K.find_edge(graph, eid) is None:
                errors.append("%s.conflicts_with: 目标 %s 不是边" % (where, eid))
            if len(op.get("reason") or "") < 20:
                errors.append("%s: CONFLICT 必须给出 >=20 字符的冲突说明 reason" % where)
    return errors, warnings


def case_mismatch(cs, graph):
    cid_c, cid_g = cs.get("case_id"), graph.get("case_id")
    if cid_c and cid_g and cid_c != cid_g:
        return "case_id 不一致: changeset=%r graph=%r" % (cid_c, cid_g)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="确定性校验 baseline 候选或变更集")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--candidates", help="baseline 候选 JSON")
    ap.add_argument("--changeset", help="变更集 JSON")
    ap.add_argument("--graph", help="校验 changeset 时的基线图（graph-v1.json）")
    ap.add_argument("--report", help="校验报告输出路径（JSON）")
    args = ap.parse_args(argv)

    case = K.read_case(args.input_dir)
    sources = K.load_sources(args.input_dir, case)
    paras = K.load_paragraphs(args.input_dir, sources)
    source_ids = {s["source_id"] for s in sources}
    if not paras:
        print("ERROR: 未加载到任何段落（检查 primary/secondary-material.json）",
              file=sys.stderr)
        return 1

    errors, warnings = [], []
    if args.candidates:
        cands = K.load_json(args.candidates)
        e, w = verify_candidates(cands, case, paras, source_ids)
        errors += e
        warnings += w
    if args.changeset:
        if not args.graph:
            print("ERROR: 校验 changeset 需要 --graph 基线图", file=sys.stderr)
            return 2
        cs = K.load_json(args.changeset)
        graph = K.load_json(args.graph)
        e, w = verify_changeset(cs, graph, paras, source_ids)
        errors += e
        warnings += w

    report = {"case_id": case.get("case_id"), "sources": sorted(source_ids),
              "paragraph_count": len(paras), "errors": errors, "warnings": warnings,
              "ok": not errors}
    if args.report:
        K.dump_json(report, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
