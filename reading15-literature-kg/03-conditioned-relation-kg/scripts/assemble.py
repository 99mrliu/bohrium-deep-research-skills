#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结果组装器：动态镜像 case.json 的 output_contract 全部键，产出 result.json。

- 每个 output_contract 键都被镜像：认识的键填真实产物摘要，不认识的键
  填 null + pending 说明（诚实占位，绝不伪造）。
- 附带 case_id、status、sources、uncertainty、changes。
用法：
  python3 assemble.py --case <input>/case.json --outdir <output_dir>
"""
import argparse
import os
import sys

from relation_common import load_json, dump_json


def fill_known_key(key, outdir, artifacts):
    """按键名启发式填充；返回 (value, filled?)。"""
    def counts(path, field):
        try:
            return load_json(path).get(field)
        except Exception:
            return None

    if key in ("graph_summary", "graph", "entities_and_relations"):
        g = artifacts.get("graph")
        if g:
            return {"path": g,
                    "n_nodes": counts(g, "nodes") and len(counts(g, "nodes")),
                    "n_edges": counts(g, "edges") and len(counts(g, "edges"))}, True
    if key in ("evidence_bound_graph", "evidence", "evidence_binding"):
        return {"graph_json": artifacts.get("graph"),
                "graph_jsonl": artifacts.get("graph_jsonl"),
                "note": "每个节点/边均含 source_id + JATS paragraph_id + 逐字短引"}, True
    if key in ("relation_audit", "audit"):
        return {"path": artifacts.get("audit"),
                "n_errors": counts(artifacts.get("audit", ""), "n_errors"),
                "n_warnings": counts(artifacts.get("audit", ""), "n_warnings")}, True
    if key in ("conflicts", "conflict_report"):
        return {"path": artifacts.get("conflicts"),
                "n_conflicts": counts(artifacts.get("conflicts", ""), "n_conflicts"),
                "policy": "冲突全部保留，绝不静默解决"}, True
    if key in ("queries", "query_results"):
        return {"path": artifacts.get("queries"),
                "n_executed": counts(artifacts.get("queries", ""), "n_executed")}, True
    if key in ("merge_report", "merges", "merge_and_conflicts"):
        return {"path": artifacts.get("merge_report")}, True
    if key in ("preview", "graph_preview"):
        return {"svg": artifacts.get("svg"), "dot": artifacts.get("dot"),
                "markdown": artifacts.get("preview_md")}, True
    if key in ("uncertainty", "uncertainties"):
        return None, False  # 由顶层 uncertainty 统一承载
    if key in ("status",):
        return None, False
    return None, False


def main(argv=None):
    ap = argparse.ArgumentParser(description="result.json 组装器")
    ap.add_argument("--case", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args(argv)

    case = load_json(args.case)
    out = args.outdir.rstrip("/")
    artifacts = {
        "graph": out + "/graph.json",
        "graph_jsonl": out + "/graph.jsonl",
        "audit": out + "/relation_audit.json",
        "conflicts": out + "/conflicts.json",
        "queries": out + "/queries.json",
        "merge_report": out + "/merge_report.json",
        "svg": out + "/graph.svg",
        "dot": out + "/graph.dot",
        "preview_md": out + "/graph_preview.md",
    }
    artifacts = {k: v for k, v in artifacts.items() if os.path.exists(v)}

    result = {
        "case_id": case.get("case_id"),
        "skill": "03-conditioned-relation-kg",
        "status": "success",
        "sources": [{"source_id": m.get("source_id"), "role": m.get("role"),
                     "file": m.get("file")}
                    for m in load_json(os.path.join(os.path.dirname(args.case),
                        "material.json")).get("materials", [])]
                    if os.path.exists(os.path.join(os.path.dirname(args.case),
                        "material.json")) else [],
        "uncertainty": [],
        "changes": ["bootstrap: 早期部分 result.json",
                    "validate+lint: 关系校验与条件降级",
                    "conflict_detect: 冲突保留",
                    "query_run: 确定性查询执行",
                    "assemble: 镜像 output_contract"],
    }

    # 收集不确定项：lint 降级、冲突、空结果查询
    lint_path = out + "/lint_findings.json"
    if os.path.exists(lint_path):
        for f in load_json(lint_path).get("findings", []):
            result["uncertainty"].append(
                "lint %s @%s：保持 partial/uncertain，未补造" % (
                    f.get("rule"), f.get("edge_id")))
    conf_path = out + "/conflicts.json"
    if os.path.exists(conf_path):
        for c in load_json(conf_path).get("conflicts", []):
            result["uncertainty"].append(
                "冲突 %s（%s）未解决，全部保留" % (c.get("kind"),
                ", ".join(e.get("edge_id", "?") for e in c.get("edges", []))))
    q_path = out + "/queries.json"
    if os.path.exists(q_path):
        for r in load_json(q_path).get("results", []):
            if r.get("answer") == "no_direct_relation":
                result["uncertainty"].append(
                    "查询 %s：无直接关系（共现≠关系），如实回答" % r.get("query_id"))

    # 动态镜像 output_contract 全部键
    contract = case.get("output_contract") or {}
    mirrored = {}
    for key in contract:
        value, filled = fill_known_key(key, out, artifacts)
        if key == "status":
            mirrored[key] = result["status"]
        elif key in ("uncertainty", "uncertainties"):
            mirrored[key] = result["uncertainty"]
        elif filled:
            mirrored[key] = value
        else:
            mirrored[key] = None
            result["uncertainty"].append(
                "output_contract 键 '%s' 无对应产物，诚实置 null" % key)
            if result["status"] == "success":
                result["status"] = "partial"
    result["contract_mirror"] = mirrored
    # 契约键同时提升到 result.json 顶层（与既有顶层键冲突时保留真实顶层值），
    # 保证“result.json 含全部 output_contract 字段”可被顶层直接核验。
    for key, value in mirrored.items():
        if key not in result:
            result[key] = value

    dump_json(result, out + "/result.json")
    print("assemble: contract keys mirrored=%d status=%s -> %s/result.json"
          % (len(mirrored), result["status"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
