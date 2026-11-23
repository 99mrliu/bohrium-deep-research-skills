# -*- coding: utf-8 -*-
"""运行时编排器：/input → /app/work → /app/output（容错，仅标准库）。

用法：python3 run_case.py [--input /input] [--work /app/work] [--output /app/output]

流程（每步先保存诚实部分结果，再逐步改进）：
0. 读取 case.json（case_id、output_contract、根 DOI/title/authors——只属于第一篇）；
1. 读取 corpus-manifest.json / material.json / primary-material.json /
   secondary-material.json（可能还有 XML），容错抽取 JATS 段落库；
2. 读取 Agent 在 /app/work 写好的 mentions.json（语义候选由 Agent 产生）；
   缺失时立即产出 status=partial 的诚实结果并说明人工接管位置；
3. 确定性身份裁决门（MERGE / KEEP_DISTINCT / UNDECIDED）；
4. 引文核验 + 图谱构建（稳定 ID 在裁决后分配）；
5. 执行查询：/app/work/queries.json 若存在则使用，否则自动生成 3 条并实际执行；
6. result.json 动态镜像 output_contract 全部键，附诚实状态/不确定性/变更记录。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import load_json, dump_json, write_text
from identity_gate import adjudicate
from build_graph import build_graph, to_dot, to_jsonl, to_svg, to_text_preview
from query_graph import run_queries

_ID_KEYS = ("paragraph_id", "pid", "jats_id", "para_id", "id")
_TEXT_KEYS = ("text", "content", "paragraph", "sentence", "value")


def log_change(records, step, action):
    records.append({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "step": step, "action": action})


def extract_paragraphs(obj, hint, acc):
    """容错递归抽取段落：凡同时具有 ID 键与文本键的字典视为一个 JATS 段落。

    hint 沿祖先键传播（如 "papers" 下的来源名）；抽取不到时 acc 为空，
    上层如实报告 partial，绝不臆造段落。
    """
    if isinstance(obj, dict):
        idk = next((k for k in _ID_KEYS if k in obj), None)
        txk = next((k for k in _TEXT_KEYS if k in obj), None)
        if idk and txk and isinstance(obj[txk], str):
            src = obj.get("source_id") or obj.get("source") or hint or "unknown"
            acc.setdefault(str(src), {})[str(obj[idk])] = obj[txk]
            return
        for k, v in obj.items():
            # 段落映射形态：{"paragraphs": {"p-0001": "...", ...}}
            if k in ("paragraphs", "body") and isinstance(v, dict) \
                    and all(isinstance(x, str) for x in v.values()):
                src = obj.get("source_id") or hint or obj.get("doi") or "unknown"
                for pid, text in v.items():
                    acc.setdefault(str(src), {})[str(pid)] = text
                continue
            new_hint = hint
            if k in ("source_id", "source", "doi") and isinstance(v, str):
                new_hint = v
            elif isinstance(v, (dict, list)) and k not in (
                    "meta", "output_contract", "attributes", "evidence"):
                new_hint = k if hint in (None, "unknown") else hint
            extract_paragraphs(v, new_hint, acc)
    elif isinstance(obj, list):
        for it in obj:
            extract_paragraphs(it, hint, acc)


def mirror_contract(contract):
    """动态镜像 output_contract 的键（键集合随输入变化，不硬编码）。"""
    if isinstance(contract, dict):
        return {k: (mirror_contract(v) if isinstance(v, dict) else None)
                for k, v in contract.items()}
    if isinstance(contract, list):
        return {str(k): None for k in contract}
    return {}


def auto_queries(graph):
    """无外部查询规格时自动生成 3 条可实际执行的查询。"""
    specs = []
    if not graph["nodes"]:
        return specs
    degree = {}
    for e in graph["edges"]:
        degree[e["subject"]] = degree.get(e["subject"], 0) + 1
        degree[e["object"]] = degree.get(e["object"], 0) + 1
    hub = max(degree, key=degree.get) if degree else graph["nodes"][0]["id"]
    specs.append({"query_id": "Q1", "type": "neighbors", "node_id": hub,
                  "description": "自动生成：度数最高节点的一跳邻居"})
    etypes = {}
    for n in graph["nodes"]:
        et = n.get("entity_type")
        if isinstance(et, str):
            etypes[et] = etypes.get(et, 0) + 1
    if etypes:
        top = max(etypes, key=etypes.get)
        specs.append({"query_id": "Q2", "type": "filter", "entity_type": top,
                      "description": "自动生成：最常见实体类型过滤"})
    cross = _find_cross_source_pair(graph)
    if cross:
        specs.append({"query_id": "Q3", "type": "path",
                      "start_id": cross[0], "end_id": cross[1],
                      "description": "自动生成：跨来源节点最短路径"})
    else:
        preds = sorted({e["predicate"] for e in graph["edges"]})
        if preds:
            specs.append({"query_id": "Q3", "type": "filter",
                          "predicate": preds[0],
                          "description": "自动生成：谓词过滤（无跨来源对时替代）"})
    return specs


def _find_cross_source_pair(graph):
    merged = [n for n in graph["nodes"] if n.get("identity_status") == "MERGED"]
    singles = [n for n in graph["nodes"]
               if n["kind"] == "entity" and n.get("identity_status") != "MERGED"]
    for m in merged:
        for s in singles:
            ssrc = {x.get("source_id") for x in s.get("sources", [])}
            msrc = {x.get("source_id") for x in m.get("sources", [])}
            if ssrc - msrc:
                return (s["id"], m["id"])
    return None


def write_outputs(outdir, result, graph=None, decisions=None, conflicts=None,
                  queries=None, verification=None):
    dump_json(result, os.path.join(outdir, "result.json"))
    if graph is not None:
        dump_json(graph, os.path.join(outdir, "graph.json"))
        write_text(to_jsonl(graph), os.path.join(outdir, "graph.jsonl"))
        write_text(to_dot(graph), os.path.join(outdir, "graph.dot"))
        write_text(to_svg(graph), os.path.join(outdir, "graph.svg"))
        write_text(to_text_preview(graph), os.path.join(outdir, "preview.txt"))
    if decisions is not None:
        dump_json(decisions, os.path.join(outdir, "identity-decisions.json"))
    if conflicts is not None:
        dump_json(conflicts, os.path.join(outdir, "conflicts.json"))
    if queries is not None:
        dump_json(queries, os.path.join(outdir, "queries.json"))
    if verification is not None:
        dump_json(verification, os.path.join(outdir, "verification-report.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    for d in (args.work, args.output):
        os.makedirs(d, exist_ok=True)

    changes, uncertainties = [], []
    case = load_json(os.path.join(args.input, "case.json"), {}) or {}
    case_id = case.get("case_id", "unknown")
    contract = case.get("output_contract")
    result = mirror_contract(contract)
    result.update({
        "case_id": case_id,
        "skill": "crossdoc-identity-kg",
        "status": "partial",
        "uncertainties": uncertainties,
        "change_records": changes,
    })
    log_change(changes, "0", "读取 case.json，动态镜像 output_contract 键")
    # 根 DOI/title/authors 只属于第一篇（primary），绝不套用到第二篇
    root_meta = {"doi": case.get("doi"), "title": case.get("title"),
                 "authors": case.get("authors")}
    dump_json({"root_metadata_primary_only": root_meta},
              os.path.join(args.work, "root-metadata.json"))
    write_outputs(args.output, result)  # 早期部分结果

    # ---- 1. 段落库 ----
    store, sources = {}, []
    manifest = load_json(os.path.join(args.input, "corpus-manifest.json"))
    if isinstance(manifest, dict):
        entries = manifest.get("papers") or manifest.get("corpus") or []
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict):
                sources.append({"source_id": e.get("source_id") or e.get("doi"),
                                "doi": e.get("doi"), "authors": e.get("authors"),
                                "license": e.get("license"),
                                "sha256": e.get("sha256") or e.get("hash")})
    # primary/secondary 的来源解析到 corpus-manifest 的对应 source_id
    # （根 DOI/title/authors 只属于第一篇，不得套用到第二篇）。
    role_hint = {}
    if sources:
        role_hint["PRIMARY"] = sources[0].get("source_id")
        if len(sources) > 1:
            role_hint["SECONDARY"] = sources[1].get("source_id")
    for fname, role in (("material.json", None),
                        ("primary-material.json", "PRIMARY"),
                        ("secondary-material.json", "SECONDARY")):
        doc = load_json(os.path.join(args.input, fname))
        if doc is not None:
            extract_paragraphs(doc, role_hint.get(role) or role, store)
    log_change(changes, "1", "抽取 JATS 段落库：来源 %d 个，段落 %d 段"
               % (len(store), sum(len(v) for v in store.values())))
    dump_json({"sources": sources,
               "paragraph_counts": {k: len(v) for k, v in store.items()}},
              os.path.join(args.work, "paragraph-store-index.json"))
    if not store:
        uncertainties.append("未能从输入材料抽取任何 JATS 段落，图谱为空")
        result["status"] = "partial"
        write_outputs(args.output, result)
        return 0

    # ---- 2. Agent 语义提及 ----
    mdoc = load_json(os.path.join(args.work, "mentions.json"))
    if not mdoc or not mdoc.get("mentions"):
        uncertainties.append(
            "未找到 /app/work/mentions.json：语义候选须由 Agent 按 "
            "references/schema.md 抽取后写入，本脚本不臆造实体。"
            "人工接管位置：按段落库索引完成提及抽取后重跑本脚本。")
        result["status"] = "partial"
        log_change(changes, "2", "mentions.json 缺失，产出诚实部分结果")
        write_outputs(args.output, result)
        return 0
    mentions = mdoc["mentions"]
    generic = set(mdoc.get("meta", {}).get("generic_terms") or [])
    log_change(changes, "2", "读取 Agent 提及 %d 条" % len(mentions))

    # ---- 3-4. 裁决 + 构图 ----
    decisions, clusters = adjudicate(mentions, generic_terms=generic)
    rdoc = load_json(os.path.join(args.work, "relations.json"), {}) or {}
    graph, verification, conflicts = build_graph(
        mentions, rdoc.get("relations") or [], decisions, clusters, store)
    log_change(changes, "3", "身份裁决 %d 对；核验剔除提及 %d、边 %d"
               % (len(decisions), len(verification["rejected"]),
                  len(verification["rejected_edges"])))
    for r in verification["rejected"]:
        uncertainties.append("提及 %s 证据核验失败（%s），已剔除"
                             % (r["mention_id"], r["reason"]))
    for d in decisions:
        if d["decision"] == "UNDECIDED":
            uncertainties.append("候选对 %s 证据不足，保持 UNDECIDED"
                                 % "/".join(d["pair"]))

    # ---- 5. 查询 ----
    qdoc = load_json(os.path.join(args.work, "queries.json"), {}) or {}
    specs = qdoc.get("queries") or auto_queries(graph)
    queries = run_queries(graph, specs)
    log_change(changes, "5", "实际执行查询 %d 条" % len(queries))

    # ---- 6. 最终 result.json（动态镜像键 + 填充）----
    filled = {
        "status": "success" if graph["nodes"] else "partial",
        "graph": {"file": "graph.json", "node_count": len(graph["nodes"]),
                  "edge_count": len(graph["edges"])},
        "identity_decisions": decisions,
        "conflicts": conflicts,
        "queries": queries,
        "uncertainties": uncertainties,
        "sources": sources,
    }
    unfilled = []
    for k in result:
        if k in filled:
            result[k] = filled[k]
        elif k in ("case_id", "skill", "change_records"):
            pass
        elif result[k] is None:
            unfilled.append(k)
    if unfilled:
        uncertainties.append("output_contract 键 %s 无自然映射，保留 null"
                             % ", ".join(sorted(unfilled)))
    result["status"] = filled["status"]
    result.setdefault("graph", filled["graph"])
    result.setdefault("identity_decisions", decisions)
    result.setdefault("conflicts", conflicts)
    result.setdefault("queries", queries)
    result.setdefault("sources", sources)
    log_change(changes, "6", "写入最终结果")
    write_outputs(args.output, result, graph, decisions, conflicts,
                  queries, verification)
    print("run_case 完成: status=%s nodes=%d edges=%d decisions=%d queries=%d"
          % (result["status"], len(graph["nodes"]), len(graph["edges"]),
             len(decisions), len(queries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
