#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关系记录校验器：受控词表（允许案例扩展）+ 证据绑定 + 引文逐字核验。

规则（错误级 E / 警告级 W）：
  R1  必填字段齐全（edge_id/relation/subject/object/voice/evidence）      E
  R2  relation ∈ 受控词表 ∪ 案例扩展                                       E
  R3  voice 必填且 ∈ {primary-results, cited-background,
                       interpretation, hypothesis}                          E
  R4  evidence 非空，且含 source_id/paragraph_id/quote                      E
  R5  quote 在对应 JATS 段落原文中逐字命中（归一化后子串）                  E
  R6  比较型关系必须有 conditions.metric（或 basis）与 comparator          E
  R7  measurement 有 value 则必须有 unit 且至少一个条件作用域键            E
      （否则视为“全局数值”，拒绝绑定）
  R8  voice=cited-background 且 used_as_primary_evidence=true → 拒绝        E
      （背景转述永远不得当作一手证据）
  R9  polarity ∈ {positive, negative, neutral}                             E
  R10 conditions 取值引用已知节点（提供 --nodes 时检查）                    W

用法：
  python3 relation_validate.py --relations relations.json --input <input_dir> \
      [--nodes nodes.json] --out relation_audit.json [--no-fail]
退出码：存在错误级问题且未给 --no-fail 时为 1。
"""
import argparse
import sys

from relation_common import (COMPARATIVE, EDGE_REQUIRED, EVIDENCE_REQUIRED,
                             POLARITY, SCOPE_KEYS, VOICES, load_corpus,
                             load_json, dump_json, vocab_with_extensions)
from quote_check import check_quote


def validate_edge(edge, vocab, corpus, node_ids=None):
    problems = []  # (level, rule, message)
    for field in EDGE_REQUIRED:
        if field not in edge or edge[field] in (None, ""):
            problems.append(("E", "R1", "缺少必填字段 %s" % field))
    rel = edge.get("relation")
    if rel and rel not in vocab:
        problems.append(("E", "R2", "relation '%s' 不在受控词表/案例扩展中" % rel))
    voice = edge.get("voice")
    if not voice or voice not in VOICES:
        problems.append(("E", "R3", "author voice 缺失或非法: %r（强制必填）" % voice))
    evs = edge.get("evidence") or []
    if not evs:
        problems.append(("E", "R4", "evidence 为空：每条边必须绑定证据"))
    for i, ev in enumerate(evs):
        for field in EVIDENCE_REQUIRED:
            if not ev.get(field):
                problems.append(("E", "R4", "evidence[%d] 缺少 %s" % (i, field)))
        if all(ev.get(f) for f in EVIDENCE_REQUIRED):
            chk = check_quote(corpus, ev["source_id"], ev["paragraph_id"], ev["quote"])
            if not chk["match"]:
                problems.append(("E", "R5", "引文未逐字命中: %s (%s)"
                                 % (ev["quote"][:60], chk.get("reason", "?"))))
    cond = edge.get("conditions") or {}
    if rel in COMPARATIVE:
        if not (cond.get("metric") or edge.get("basis")):
            problems.append(("E", "R6", "比较型关系缺少 metric/basis（不得做全局比较）"))
        if not edge.get("comparator"):
            problems.append(("E", "R6", "比较型关系缺少 comparator（比较对象）"))
    meas = edge.get("measurement")
    if meas and meas.get("value") is not None:
        if not meas.get("unit"):
            problems.append(("E", "R7", "数值 %r 缺少单位" % meas.get("value")))
        if not any(cond.get(k) for k in SCOPE_KEYS):
            problems.append(("E", "R7", "数值未绑定任何条件作用域（禁止全局数值）"))
    if voice == "cited-background" and edge.get("used_as_primary_evidence"):
        problems.append(("E", "R8", "cited-background 被用作一手证据，拒绝"))
    pol = edge.get("polarity")
    if pol is not None and pol not in POLARITY:
        problems.append(("E", "R9", "polarity 非法: %r" % pol))
    if node_ids is not None:
        for k, v in cond.items():
            if isinstance(v, str) and v.startswith("n_") and v not in node_ids:
                problems.append(("W", "R10", "conditions.%s 引用未知节点 %s" % (k, v)))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="条件化关系校验器")
    ap.add_argument("--relations", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--nodes", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-fail", action="store_true")
    args = ap.parse_args(argv)

    doc = load_json(args.relations)
    vocab = vocab_with_extensions(doc)
    corpus, _ = load_corpus(args.input)
    node_ids = None
    if args.nodes:
        node_ids = {n.get("node_id") for n in load_json(args.nodes).get("nodes", [])}

    per_edge, n_err, n_warn = [], 0, 0
    for edge in doc.get("edges", []):
        probs = validate_edge(edge, vocab, corpus, node_ids)
        n_err += sum(1 for p in probs if p[0] == "E")
        n_warn += sum(1 for p in probs if p[0] == "W")
        per_edge.append({
            "edge_id": edge.get("edge_id"),
            "status": "error" if any(p[0] == "E" for p in probs)
                      else ("warning" if probs else "ok"),
            "problems": [{"level": l, "rule": r, "message": m} for l, r, m in probs],
        })
    audit = {
        "relations_file": args.relations,
        "vocab": sorted(vocab),
        "extensions": doc.get("extensions", []),
        "n_edges": len(doc.get("edges", [])),
        "n_errors": n_err,
        "n_warnings": n_warn,
        "edges": per_edge,
    }
    dump_json(audit, args.out)
    print("validate: edges=%d errors=%d warnings=%d -> %s"
          % (audit["n_edges"], n_err, n_warn, args.out))
    if n_err and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
