#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_assemble.py — 装配器：把 /app/work 的产物汇总为 /app/output 交付件。

产物：graph-baseline.json/jsonl、graph-current.json/jsonl、queries.json、
changes.json/jsonl、change-ledger.md、graph-preview.md、graph.dot、graph.svg、
result.json。result.json 回显 case_id，并动态镜像 case.json 中
output_contract 的全部键：能填的填真实产物，填不了的填 null 并记入
uncertainty（诚实部分结果，绝不编造）。本脚本可随时运行：产物缺失时
status=partial 并说明缺口，支持"先存部分结果、逐步补齐"。
"""
import argparse
import math
import os
import shutil
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_common as K

TYPE_COLORS = {
    "material": "#cde4ff", "method": "#d8f5d0", "task": "#fff2c8",
    "metric": "#ffd9d9", "researcher": "#e8ddff", "conclusion": "#ffe3c2",
    "sample": "#d0f0ee", "dataset": "#f5d5ec", "condition": "#eeeeee",
    "device": "#e2e8c0",
}


# ---------------------------------------------------------------- 预览渲染

def render_dot(graph):
    L = ['digraph kg {', '  rankdir=LR; node [shape=box, style=filled];']
    for n in sorted(graph.get("nodes", []), key=lambda x: x["id"]):
        color = TYPE_COLORS.get(n["type"], "#ffffff")
        label = "%s: %s" % (n["type"], n["label"])
        L.append('  "%s" [label="%s", fillcolor="%s"];'
                 % (n["id"], label.replace('"', "'"), color))
    for e in sorted(graph.get("edges", []), key=lambda x: x["id"]):
        attrs = e.get("attributes", {})
        extra = " ".join(str(attrs.get(k, "")) for k in ("value", "condition")).strip()
        label = e["relation"] + ("\\n" + extra if extra else "")
        style = ' color="#cc0000", fontcolor="#cc0000"' if e.get("conflict_group") else ""
        L.append('  "%s" -> "%s" [label="%s"%s];'
                 % (e["from"], e["to"], label.replace('"', "'"), style))
    L.append("}")
    return "\n".join(L) + "\n"


def render_svg(graph):
    nodes = sorted(graph.get("nodes", []), key=lambda x: x["id"])
    edges = sorted(graph.get("edges", []), key=lambda x: x["id"])
    n = max(len(nodes), 1)
    W = H = max(720, 120 + n * 46)
    cx, cy, R = W / 2, H / 2, min(W, H) / 2 - 90
    pos = {}
    for i, nd in enumerate(nodes):
        ang = 2 * math.pi * i / n - math.pi / 2
        pos[nd["id"]] = (cx + R * math.cos(ang), cy + R * math.sin(ang))
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'font-family="sans-serif">' % (W, H),
             '<rect width="100%" height="100%" fill="#ffffff"/>']
    for e in edges:
        if e["from"] not in pos or e["to"] not in pos:
            continue
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        color = "#cc0000" if e.get("conflict_group") else "#666666"
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="1.2"/>' % (x1, y1, x2, y2, color))
        attrs = e.get("attributes", {})
        extra = " ".join(str(attrs.get(k, "")) for k in ("value", "condition")).strip()
        label = e["relation"] + (" " + extra if extra else "")
        parts.append('<text x="%.1f" y="%.1f" font-size="9" fill="%s" '
                     'text-anchor="middle">%s</text>'
                     % ((x1 + x2) / 2, (y1 + y2) / 2 - 3, color, escape(label)))
    for nd in nodes:
        x, y = pos[nd["id"]]
        color = TYPE_COLORS.get(nd["type"], "#ffffff")
        parts.append('<circle cx="%.1f" cy="%.1f" r="26" fill="%s" stroke="#333"/>'
                     % (x, y, color))
        parts.append('<text x="%.1f" y="%.1f" font-size="8" text-anchor="middle">%s</text>'
                     % (x, y - 2, escape(nd["type"])))
        short = nd["label"] if len(nd["label"]) <= 18 else nd["label"][:17] + "…"
        parts.append('<text x="%.1f" y="%.1f" font-size="8" text-anchor="middle">%s</text>'
                     % (x, y + 8, escape(short)))
        parts.append('<text x="%.1f" y="%.1f" font-size="7" fill="#555" '
                     'text-anchor="middle">%s</text>' % (x, y + 36, escape(nd["id"])))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_preview_md(graph, synthetic):
    L = ["# 图谱预览（当前版本 %s）%s" % (graph.get("version"),
                                        "【SYNTHETIC 合成示例】" if synthetic else ""), ""]
    L.append("节点 %d，边 %d。每条记录的完整证据见 graph-current.json。"
             % (len(graph.get("nodes", [])), len(graph.get("edges", []))))
    L.append("")
    L.append("## 节点")
    L.append("| id | type | label | aliases | 证据数 |")
    L.append("|-|-|-|-|-|")
    for nd in sorted(graph.get("nodes", []), key=lambda x: x["id"]):
        al = "; ".join(a.get("label", "") if isinstance(a, dict) else str(a)
                       for a in nd.get("aliases", []))
        L.append("| %s | %s | %s | %s | %d |"
                 % (nd["id"], nd["type"], nd["label"], al, len(nd.get("evidence", []))))
    L.append("")
    L.append("## 边")
    L.append("| id | relation | from | to | value | condition | status |")
    L.append("|-|-|-|-|-|-|-|")
    for e in sorted(graph.get("edges", []), key=lambda x: x["id"]):
        a = e.get("attributes", {})
        L.append("| %s | %s | %s | %s | %s | %s | %s |"
                 % (e["id"], e["relation"], e["from"], e["to"],
                    a.get("value", ""), a.get("condition", ""),
                    e.get("status", "active")))
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- 契约镜像

def _contract_keys(contract):
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        keys = []
        for it in contract:
            if isinstance(it, str):
                keys.append(it)
            elif isinstance(it, dict):
                k = it.get("name") or it.get("key") or it.get("field")
                if k:
                    keys.append(k)
        return keys
    return []


def _map_contract_key(key, ctx):
    kl = key.lower()
    if "graph" in kl:
        return {"baseline": "graph-baseline.json", "current": "graph-current.json",
                "jsonl": ["graph-baseline.jsonl", "graph-current.jsonl"],
                "preview": ["graph.dot", "graph.svg", "graph-preview.md"]}
    if "quer" in kl:
        return {"file": "queries.json",
                "executed": ctx["n_queries"], "note": "全部为真实执行，含证据"}
    if "change" in kl or "ledger" in kl or "audit" in kl:
        return {"file": "changes.json", "jsonl": "changes.jsonl",
                "ledger": "change-ledger.md", "summary": ctx["change_summary"]}
    if "evidence" in kl or "source" in kl or "provenance" in kl:
        return {"sources": ctx["sources"],
                "note": "每个实质节点/边均含 source_id + JATS paragraph_id + 原文短引；"
                        "本包无 PDF 页码，未使用页码定位"}
    if "status" in kl:
        return ctx["status"]
    if "uncertain" in kl:
        return ctx["uncertainty"]
    if "case" in kl:
        return ctx["case_id"]
    if "answer" in kl or "result" in kl or "summary" in kl or "output" in kl:
        return ctx["summary_text"]
    return None


# ---------------------------------------------------------------- 主流程

def _copy(work_dir, out_dir, src, dst):
    p = os.path.join(work_dir, src)
    if os.path.exists(p):
        shutil.copyfile(p, os.path.join(out_dir, dst))
        return True
    return False


def assemble(input_dir, work_dir, out_dir):
    case = K.read_case(input_dir)
    case_id = case.get("case_id")
    synthetic = bool(case.get("synthetic"))
    os.makedirs(out_dir, exist_ok=True)
    missing, uncertainty = [], []

    g1p, g2p = (os.path.join(work_dir, f) for f in ("graph-v1.json", "graph-v2.json"))
    g1 = K.load_json(g1p) if os.path.exists(g1p) else None
    g2 = K.load_json(g2p) if os.path.exists(g2p) else None
    if g1 is None:
        missing.append("baseline 图（先运行 kg_apply.py init）")
    if g2 is None:
        missing.append("当前图（运行 kg_apply.py apply，或仅有 baseline 时以 v1 交付）")
    for src, dst in [("graph-v1.json", "graph-baseline.json"),
                     ("graph-v1.jsonl", "graph-baseline.jsonl"),
                     ("graph-v2.json", "graph-current.json"),
                     ("graph-v2.jsonl", "graph-current.jsonl"),
                     ("queries.json", "queries.json"),
                     ("changes.json", "changes.json"),
                     ("changes.jsonl", "changes.jsonl"),
                     ("change-ledger.md", "change-ledger.md"),
                     ("diff.json", "diff.json")]:
        if not _copy(work_dir, out_dir, src, dst) and src not in (
                "graph-v2.json", "graph-v2.jsonl", "changes.json", "changes.jsonl",
                "change-ledger.md", "diff.json", "queries.json"):
            missing.append(src)
    if not os.path.exists(os.path.join(out_dir, "queries.json")):
        missing.append("queries.json（运行 kg_query.py --spec ...）")

    gcur = g2 or g1
    sources = (gcur or {}).get("sources") or K.load_sources(input_dir, case)
    for s in sources[1:]:
        for k in ("doi", "title"):
            if not s.get(k):
                uncertainty.append("来源 %s 缺少 %s（根 case.json 元数据只属于第一篇，"
                                   "未套用到该来源）" % (s["source_id"], k))
    if gcur:
        with open(os.path.join(out_dir, "graph.dot"), "w", encoding="utf-8") as f:
            f.write(render_dot(gcur))
        with open(os.path.join(out_dir, "graph.svg"), "w", encoding="utf-8") as f:
            f.write(render_svg(gcur))
        with open(os.path.join(out_dir, "graph-preview.md"), "w",
                  encoding="utf-8") as f:
            f.write(render_preview_md(gcur, synthetic))
        n_conf = len({e.get("conflict_group") for e in gcur.get("edges", [])
                      if e.get("conflict_group")})
        if n_conf:
            uncertainty.append("存在 %d 组未裁决冲突边（conflict_group 见 "
                               "graph-current.json），双方证据并列保留，未合并为单一结论"
                               % n_conf)

    changes_doc = None
    cpath = os.path.join(out_dir, "changes.json")
    if os.path.exists(cpath):
        changes_doc = K.load_json(cpath)
    qdoc = None
    qpath = os.path.join(out_dir, "queries.json")
    if os.path.exists(qpath):
        qdoc = K.load_json(qpath)

    status = "success" if (g1 is not None and gcur is not None and qdoc
                           and not missing) else "partial"
    summary_text = (
        "增量文献知识图谱：baseline v1（primary 封存）%s；当前版本 %s。"
        "节点 %d、边 %d；变更操作 %s；真实执行查询 %d 个；未裁决冲突 %d 组。"
        % ("已建" if g1 else "缺失", (gcur or {}).get("version", "缺失"),
           len((gcur or {}).get("nodes", [])), len((gcur or {}).get("edges", [])),
           (changes_doc or {}).get("summary", "无（未应用变更集）"),
           len((qdoc or {}).get("queries", [])),
           len({e.get("conflict_group") for e in (gcur or {}).get("edges", [])
                if e.get("conflict_group")})))

    ctx = {"case_id": case_id, "status": status, "sources": sources,
           "uncertainty": uncertainty, "summary_text": summary_text,
           "n_queries": len((qdoc or {}).get("queries", [])),
           "change_summary": (changes_doc or {}).get("summary")}
    result = {
        "schema": K.SCHEMA_RESULT,
        "case_id": case_id,
        "synthetic": synthetic,
        "status": status,
        "status_reason": ("全部产物齐备" if status == "success"
                          else "缺口: " + "; ".join(missing or ["当前图/查询"])),
        "skill": "05-incremental-change-kg",
        "versions": {"baseline": "graph-baseline.json",
                     "current": "graph-current.json" if g2 else None},
        "sources": sources,
        "summary": summary_text,
        "uncertainty": uncertainty,
        "changes": {"file": "changes.json", "ledger": "change-ledger.md",
                    "summary": (changes_doc or {}).get("summary")},
    }
    for key in _contract_keys(case.get("output_contract")):
        val = _map_contract_key(key, ctx)
        if val is None:
            uncertainty.append("output_contract 键 %r 非本 Skill 产物，"
                               "按诚实原则填 null" % key)
        result[key] = val
    result["uncertainty"] = uncertainty  # 契约镜像后再刷新一次
    K.dump_json(result, os.path.join(out_dir, "result.json"))
    print("装配完成: status=%s -> %s" % (status, os.path.join(out_dir, "result.json")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="汇总 work 产物到 output 并生成 result.json")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args(argv)
    return assemble(args.input_dir, args.work_dir, args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
