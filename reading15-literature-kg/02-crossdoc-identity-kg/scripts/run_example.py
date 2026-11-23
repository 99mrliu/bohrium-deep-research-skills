# -*- coding: utf-8 -*-
"""最小合成示例流水线：input/ → output/（确定性，仅标准库）。

用法：python3 scripts/run_example.py
读取 examples/minimal/input/ 下的 papers/mentions/relations/queries/case，
运行 证据核验 → 身份裁决门 → 图谱构建 → 查询执行，
全部产物写入 examples/minimal/output/ 并在 stdout 打印摘要。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import load_json, dump_json, write_text
from identity_gate import adjudicate
from build_graph import build_graph, to_dot, to_jsonl, to_svg, to_text_preview
from query_graph import run_queries

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "examples", "minimal")
IN = os.path.join(BASE, "input")
OUT = os.path.join(BASE, "output")


def _store_from_papers(papers_doc):
    store = {}
    for sid, paper in (papers_doc.get("papers") or {}).items():
        store[sid] = {str(k): v for k, v in (paper.get("paragraphs") or {}).items()}
    return store


def main():
    papers = load_json(os.path.join(IN, "papers.json"), {})
    mentions_doc = load_json(os.path.join(IN, "mentions.json"), {})
    relations_doc = load_json(os.path.join(IN, "relations.json"), {})
    queries_doc = load_json(os.path.join(IN, "queries.json"), {})
    case = load_json(os.path.join(IN, "case.json"), {})

    store = _store_from_papers(papers)
    mentions = mentions_doc.get("mentions") or []
    relations = relations_doc.get("relations") or []
    generic = set(mentions_doc.get("meta", {}).get("generic_terms") or [])

    decisions, clusters = adjudicate(mentions, generic_terms=generic)
    graph, verification, conflicts = build_graph(
        mentions, relations, decisions, clusters, store)
    query_results = run_queries(graph, queries_doc.get("queries") or [])

    n_merge = sum(1 for d in decisions if d["decision"] == "MERGE")
    n_keep = sum(1 for d in decisions if d["decision"] == "KEEP_DISTINCT")
    n_und = sum(1 for d in decisions if d["decision"] == "UNDECIDED")

    contract = case.get("output_contract") or {}
    result = {k: None for k in contract} if isinstance(contract, dict) else {}
    result.update({
        "case_id": case.get("case_id", "EXAMPLE-SYNTH-001"),
        "label": "SYNTHETIC EXAMPLE OUTPUT（合成示例输出，非正式案例结果）",
        "status": "success",
        "graph": {"file": "graph.json",
                  "node_count": len(graph["nodes"]),
                  "edge_count": len(graph["edges"])},
        "identity_decisions": decisions,
        "conflicts": conflicts,
        "queries": query_results,
        "uncertainties": [
            "XRD 在两篇论文中仅为通用术语提及，证据不足，裁决为 UNDECIDED",
            "LLZO 电导率两来源数值不同（3.2e-4 与 1.1e-3 S/cm），分别保留，不合成结论",
        ],
    })

    dump_json(result, os.path.join(OUT, "result.json"))
    dump_json(graph, os.path.join(OUT, "graph.json"))
    write_text(to_jsonl(graph), os.path.join(OUT, "graph.jsonl"))
    dump_json(decisions, os.path.join(OUT, "identity-decisions.json"))
    dump_json(conflicts, os.path.join(OUT, "conflicts.json"))
    dump_json(query_results, os.path.join(OUT, "queries.json"))
    dump_json(verification, os.path.join(OUT, "verification-report.json"))
    write_text(to_dot(graph, label="synthetic example (not real papers)"),
               os.path.join(OUT, "graph.dot"))
    write_text(to_svg(graph, title="Synthetic example graph (fabricated demo data)"),
               os.path.join(OUT, "graph.svg"))
    write_text(to_text_preview(graph), os.path.join(OUT, "preview.txt"))

    print("示例流水线完成（合成数据）:")
    print("  提及 %d 条 -> 节点 %d，边 %d" % (
        len(mentions), len(graph["nodes"]), len(graph["edges"])))
    print("  裁决: MERGE=%d KEEP_DISTINCT=%d UNDECIDED=%d" % (n_merge, n_keep, n_und))
    print("  冲突记录 %d 条；查询 %d 条（ok=%d）" % (
        len(conflicts), len(query_results),
        sum(1 for q in query_results if q.get("status") == "ok")))
    print("  核验拒绝: 提及 %d 条，边 %d 条" % (
        len(verification["rejected"]), len(verification["rejected_edges"])))
    print("  输出目录: %s" % os.path.abspath(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
