#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 结果装配器（含 DOT / 纯 SVG 预览生成）。

职责：
1. 读取 case.json，动态镜像 output_contract 的精确键集合：
   - 能由本流程产物填充的键：从图谱/查询/验证报告如实填充；
   - 流程不产生的键：置 null 并在台账中说明“诚实缺失”，绝不省略键；
   - case_id 强制取自 case.json。
2. 装配 /app/output（或指定目录）全部产物：
   result.json, graph.json, graph.jsonl, queries.json,
   verify_report.json, ledger.json, preview.dot, preview.svg。
3. 生成预览：
   - preview.dot：Graphviz DOT 纯文本（不依赖 Graphviz 安装）；
   - preview.svg：纯代码生成的分层 SVG（无第三方依赖，布局确定性）。
4. 台账 ledger.json：记录各步骤、输入 SHA-256、警告、合同键处理说明、
   输出文件清单。诚实部分结果（honest partial）：验证未通过时 result.json
   仍生成，但以 contract 字段 "status"（若存在）或 notes 注明 partial。

CLI:
  python3 assemble_result.py --case case.json --corpus normalized_corpus.json \
      --extraction candidate_extraction.json --graph graph.json \
      --verify verify_report.json --queries queries.json --out-dir /app/output
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import kgcommon as k
from build_graph import graph_to_jsonl

# 预览分层：kind -> 列
TIER_ORDER = ["paper", "sample", "method", "condition", "metric", "claim"]
TIER_COLORS = {
    "paper": "#4a6fa5", "sample": "#2e8b57", "method": "#b8860b",
    "condition": "#9467bd", "metric": "#c0392b", "claim": "#d2691e",
    "other": "#666666",
}


def _tier(kind):
    try:
        return TIER_ORDER.index(kind)
    except ValueError:
        return len(TIER_ORDER)


def render_dot(graph):
    lines = ["digraph provenance_kg {", "  rankdir=LR;",
             '  node [shape=box, style="rounded,filled", fillcolor="#f5f5f5"];']
    for n in graph.get("nodes", []):
        label = f"{n['node_id']}\\n{n.get('label','')}".replace('"', "'")
        extra = f" ({','.join(n.get('source_ids', []))})"
        lines.append(f'  "{n["node_id"]}" [label="{label}{extra}"];')
    for e in graph.get("edges", []):
        etype = str(e.get("type", "")).replace('"', "'")
        lines.append(f'  "{e["subject"]}" -> "{e["object"]}" [label="{etype}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_svg(graph, title="provenance-kg preview"):
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    columns = {}
    for n in sorted(nodes, key=lambda x: (_tier(x.get("kind")), x["node_id"])):
        t = _tier(n.get("kind"))
        columns.setdefault(t, []).append(n)
    col_x = {t: 130 + i * 260 for i, t in enumerate(sorted(columns))}
    pos = {}
    for t, col in columns.items():
        for i, n in enumerate(col):
            pos[n["node_id"]] = (col_x[t], 80 + i * 84)
    width = (max(col_x.values()) + 220) if col_x else 400
    height = max((y for (_, y) in pos.values()), default=80) + 110

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="monospace">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="16" y="26" font-size="14" fill="#333">{html.escape(title)}'
        f'（SYNTHETIC 预览，布局仅用于阅读）</text>',
    ]
    for t, x in sorted(col_x.items()):
        name = TIER_ORDER[t] if t < len(TIER_ORDER) else "other"
        parts.append(f'<text x="{x - 40}" y="52" font-size="11" fill="#999">[{name}]</text>')
    for e in edges:
        s, o = e.get("subject"), e.get("object")
        if s in pos and o in pos:
            x1, y1 = pos[s]
            x2, y2 = pos[o]
            parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                         f'stroke="#bbbbbb" stroke-width="1.2"/>')
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            parts.append(f'<text x="{mx:.0f}" y="{my - 3:.0f}" font-size="8" '
                         f'fill="#888888">{html.escape(str(e.get("type", "")))}</text>')
    for n in nodes:
        x, y = pos[n["node_id"]]
        color = TIER_COLORS.get(n.get("kind"), TIER_COLORS["other"])
        sids = ",".join(n.get("source_ids", []))
        parts.append(f'<circle cx="{x}" cy="{y}" r="14" fill="{color}" '
                     f'stroke="#333333" stroke-width="1"/>')
        label = html.escape(str(n.get("label", n["node_id"])))
        parts.append(f'<text x="{x + 20}" y="{y - 2}" font-size="11" '
                     f'fill="#111111">{html.escape(n["node_id"])}</text>')
        parts.append(f'<text x="{x + 20}" y="{y + 12}" font-size="9" '
                     f'fill="#555555">{label} [{html.escape(sids)}]</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _paper_descriptor(node, corpus_sources):
    sids = node.get("source_ids") or []
    src = corpus_sources.get(sids[0]) if sids else None
    attrs = node.get("attributes") or {}
    return {
        "node_id": node.get("node_id"),
        "source_id": sids[0] if sids else None,
        "doi": attrs.get("doi", (src or {}).get("doi")),
        "title": attrs.get("title", (src or {}).get("title")),
        "authors": attrs.get("authors", (src or {}).get("authors")),
    }


def assemble(case, corpus, graph, verify_report, queries_payload, out_dir,
             input_files):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_sources = {s["source_id"]: s for s in corpus.get("sources", [])}

    contract = case.get("output_contract")
    if isinstance(contract, list):
        contract_keys = list(contract)
    elif isinstance(contract, dict):
        contract_keys = list(contract.keys())
    else:
        contract_keys = []

    nodes_by_id = {n["node_id"]: n for n in graph.get("nodes", [])}
    ledger_notes = []
    providers = {}

    providers["case_id"] = lambda: case.get("case_id")

    def _primary():
        pp = graph.get("primary_paper")
        node = nodes_by_id.get(pp)
        return _paper_descriptor(node, corpus_sources) if node else None

    def _secondaries():
        out = []
        for n in graph.get("nodes", []):
            if n.get("kind") == "paper" and n.get("node_id") != graph.get("primary_paper"):
                out.append(_paper_descriptor(n, corpus_sources))
        return sorted(out, key=lambda d: (d.get("source_id") or ""))

    providers.update({
        "primary_paper": _primary,
        "secondary_papers": _secondaries,
        "graph_stats": lambda: graph.get("stats"),
        "nodes": lambda: graph.get("nodes"),
        "edges": lambda: graph.get("edges"),
        "merges": lambda: graph.get("merges"),
        "nonmerges": lambda: graph.get("nonmerges"),
        "conflicts": lambda: graph.get("conflicts"),
        "unreported": lambda: graph.get("unreported"),
        "queries": lambda: (queries_payload or {}).get("queries"),
        "coverage": lambda: (verify_report or {}).get("coverage"),
        "graph_files": lambda: {
            "graph_json": "graph.json", "graph_jsonl": "graph.jsonl",
            "queries": "queries.json", "verify_report": "verify_report.json",
            "ledger": "ledger.json", "preview_dot": "preview.dot",
            "preview_svg": "preview.svg",
        },
        "status": lambda: "ok" if (verify_report or {}).get("ok") else "partial",
        "notes": lambda: ledger_notes,
        "provenance_ledger": lambda: "ledger.json",
    })

    result = {}
    for key in contract_keys:
        if key in providers:
            result[key] = providers[key]()
        else:
            result[key] = None
            ledger_notes.append(
                f"合同键 '{key}' 在本流程中无对应产物，按诚实缺失规则置 null（未省略）")
    result["case_id"] = case.get("case_id")
    if contract_keys and "status" not in contract_keys:
        # 合同未声明 status 时不额外注入，保持键集合与合同一致
        pass

    # ---- 台账 ----
    ledger = {
        "case_id": case.get("case_id"),
        "verify_ok": (verify_report or {}).get("ok"),
        "steps": [
            {"step": "normalize_input", "detail": "语料发现/归一化/缺陷登记"},
            {"step": "verify_evidence", "detail": "证据地址/引文/归属/合并纪律/覆盖度校验"},
            {"step": "build_graph", "detail": "确定性图谱构建"},
            {"step": "query_graph", "detail": "确定性查询批量执行"},
            {"step": "assemble_result", "detail": "合同键动态镜像与产物装配"},
        ],
        "input_hashes": {name: k.sha256_file(p) for name, p in input_files.items()},
        "normalize_warnings": corpus.get("warnings", []),
        "verify_warnings": (verify_report or {}).get("warnings", []),
        "verify_errors": (verify_report or {}).get("errors", []),
        "contract_notes": ledger_notes,
        "honest_partial": not (verify_report or {}).get("ok", False),
        "skipped_inputs": corpus.get("skipped", []),
    }

    # ---- 写产物 ----
    outputs = {}
    k.write_text(out_dir / "graph.jsonl", graph_to_jsonl(graph))
    outputs["graph_jsonl"] = out_dir / "graph.jsonl"
    for name, obj in (("graph.json", graph), ("queries.json", queries_payload),
                      ("verify_report.json", verify_report), ("ledger.json", ledger)):
        k.write_json(out_dir / name, obj)
        outputs[name.replace(".", "_")] = out_dir / name
    k.write_text(out_dir / "preview.dot", render_dot(graph))
    outputs["preview_dot"] = out_dir / "preview.dot"
    k.write_text(out_dir / "preview.svg",
                 render_svg(graph, title=f"case {case.get('case_id')}"))
    outputs["preview_svg"] = out_dir / "preview.svg"
    # result.json 最后写（ledger 已落盘，notes 完整）
    k.write_json(out_dir / "result.json", result)
    outputs["result_json"] = out_dir / "result.json"
    ledger["output_files"] = sorted(p.name for p in outputs.values())
    k.write_json(out_dir / "ledger.json", ledger)
    return result, ledger, outputs


def main(argv=None):
    ap = argparse.ArgumentParser(description="结果装配器（动态镜像 output_contract）")
    ap.add_argument("--case", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--verify", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)

    case = k.read_json(args.case)
    corpus = k.read_json(args.corpus)
    graph = k.read_json(args.graph)
    verify_report = k.read_json(args.verify)
    queries_payload = k.read_json(args.queries)
    input_files = {"case": args.case, "corpus": args.corpus, "graph": args.graph,
                   "verify": args.verify, "queries": args.queries}

    result, ledger, outputs = assemble(case, corpus, graph, verify_report,
                                       queries_payload, args.out_dir, input_files)
    n_keys = len(result)
    print(f"[assemble_result] contract_keys={n_keys} "
          f"status={'ok' if not ledger['honest_partial'] else 'partial(honest)'} "
          f"outputs={len(outputs)} dir={args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
