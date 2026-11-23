#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_query.py — 预置查询：把图谱指标机器化地算出来。

预置查询（定义详见 references/query_cookbook.md）：
  q_orphan_claims    无证据论断（孤儿）
  q_coverage_matrix  证据覆盖矩阵（Task × Anchor，pass 证据计数）
  q_reused_evidence  被多任务复用的锚点
  q_conflict_list    冲突清单
  q_evidence_chain   每个 Task 的完整证据链
  q_uncited_anchors  未引用锚点（源文覆盖盲区）
  q_score_derivation 逐题 0/1/2 分数推导（图指标的确定函数）
  q_honest_flags     诚实标记清单
  q_metrics          图谱汇总指标

输出 query_report.json 与 query_report.md。确定性、原子写。
用法：python3 graph_query.py --graph G --out-json J --out-md M [--only 名称]
"""
import argparse
import json
import os
import sys
import tempfile  # 原子写临时文件


def atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False,
                                  sort_keys=True, indent=2) + "\n")


class GraphView(object):
    def __init__(self, graph):
        self.graph = graph
        self.nodes = {n["id"]: n for n in graph.get("nodes", [])}
        self.edges = graph.get("edges", [])
        self.by_type = {}
        for n in graph.get("nodes", []):
            self.by_type.setdefault(n["type"], []).append(n)
        self.supports = [e for e in self.edges
                         if e["type"] == "supports"]
        self.derived = [e for e in self.edges
                        if e["type"] == "derived_from"]
        self.answers = [e for e in self.edges if e["type"] == "answers"]

    def claims_of(self, task_id):
        return [e["src"] for e in self.answers if e["dst"] == task_id]

    def evidences_of(self, claim_id):
        return [e["src"] for e in self.supports if e["dst"] == claim_id]

    def anchor_of(self, ev_id):
        for e in self.derived:
            if e["src"] == ev_id:
                return e["dst"]
        return None

    def verdict(self, ev_id):
        for e in self.supports:
            if e["src"] == ev_id:
                return e["attrs"].get("verdict")
        return None


def q_orphan_claims(gv):
    supported = {e["dst"] for e in gv.supports}
    return [{"claim": n["id"], "task": n["attrs"].get("task"),
             "text": n["attrs"].get("text", "")}
            for n in gv.by_type.get("Claim", [])
            if not n["attrs"].get("honest") and n["id"] not in supported]


def q_coverage_matrix(gv):
    tasks = [n["id"] for n in gv.by_type.get("Task", [])]
    anchors = [n["id"] for n in gv.by_type.get("Anchor", [])]
    matrix = {t: {a: 0 for a in anchors} for t in tasks}
    for t in tasks:
        for c in gv.claims_of(t):
            for ev in gv.evidences_of(c):
                if gv.verdict(ev) == "pass":
                    a = gv.anchor_of(ev)
                    if a in matrix[t]:
                        matrix[t][a] += 1
    return matrix


def q_reused_evidence(gv):
    anchor2tasks = {}
    for t in [n["id"] for n in gv.by_type.get("Task", [])]:
        for c in gv.claims_of(t):
            for ev in gv.evidences_of(c):
                if gv.verdict(ev) == "pass":
                    a = gv.anchor_of(ev)
                    if a:
                        anchor2tasks.setdefault(a, set()).add(t)
    return [{"anchor": a, "tasks": sorted(ts)}
            for a, ts in anchor2tasks.items() if len(ts) >= 2]


def q_conflict_list(gv):
    return gv.graph.get("conflicts", [])


def q_evidence_chain(gv):
    chains = {}
    for t in gv.by_type.get("Task", []):
        tid = t["id"]
        claims = []
        for c in gv.claims_of(tid):
            cn = gv.nodes.get(c, {})
            evs = []
            for ev in gv.evidences_of(c):
                en = gv.nodes.get(ev, {})
                evs.append({
                    "id": ev, "anchor": gv.anchor_of(ev),
                    "verdict": gv.verdict(ev),
                    "reason": en.get("attrs", {}).get("reason", ""),
                    "quote": en.get("attrs", {}).get("quote", "")})
            claims.append({
                "id": c, "text": cn.get("attrs", {}).get("text", ""),
                "honest": bool(cn.get("attrs", {}).get("honest")),
                "honest_reason": cn.get("attrs", {}).get(
                    "honest_reason", ""),
                "evidence": evs})
        chains[tid] = {"label": t["attrs"].get("label", ""),
                       "claims": claims}
    return chains


def q_uncited_anchors(gv):
    cited = set()
    for t in [n["id"] for n in gv.by_type.get("Task", [])]:
        for c in gv.claims_of(t):
            for ev in gv.evidences_of(c):
                if gv.verdict(ev) == "pass":
                    a = gv.anchor_of(ev)
                    if a:
                        cited.add(a)
    return [{"anchor": n["id"], "kind": n["attrs"].get("kind"),
             "preview": n["attrs"].get("text", "")[:80]}
            for n in gv.by_type.get("Anchor", [])
            if n["id"] not in cited]


def q_score_derivation(gv):
    """分数 = 图指标的确定函数：
    2 = 全部非诚实 claim 均有 pass 支持且无 fail 边；
    1 = 至少一条 pass 但有 fail 边或存在未支持 claim；
    0 = 无任何 pass 证据；
    null = 该题仅含诚实标记 claim（不可评分）。
    """
    scores = {}
    for t in gv.by_type.get("Task", []):
        tid = t["id"]
        claims = gv.claims_of(tid)
        graded = [c for c in claims
                  if not gv.nodes.get(c, {}).get("attrs", {})
                  .get("honest")]
        honest_only = len(claims) > 0 and not graded
        n_pass_claims, n_fail_edges, n_pass_edges = 0, 0, 0
        for c in graded:
            verdicts = [gv.verdict(ev) for ev in gv.evidences_of(c)]
            if "pass" in verdicts:
                n_pass_claims += 1
            n_fail_edges += verdicts.count("fail")
            n_pass_edges += verdicts.count("pass")
        if honest_only or not graded:
            score, rationale = None, "仅含诚实标记论断或无论断，不可评分"
        elif n_pass_edges == 0:
            score, rationale = 0, "无任何 pass 证据"
        elif n_pass_claims == len(graded) and n_fail_edges == 0:
            score, rationale = 2, "全部论断有 pass 支持且无 fail 边"
        else:
            score, rationale = 1, (
                "部分论断获支持或存在 fail 边（pass_claims=%d/%d, "
                "fail_edges=%d）" % (n_pass_claims, len(graded),
                                     n_fail_edges))
        scores[tid] = {"score": score, "rationale": rationale,
                       "claims_graded": len(graded),
                       "pass_claims": n_pass_claims,
                       "fail_edges": n_fail_edges}
    return scores


def q_honest_flags(gv):
    return [{"claim": n["id"], "task": n["attrs"].get("task"),
             "text": n["attrs"].get("text", ""),
             "reason": n["attrs"].get("honest_reason", "")}
            for n in gv.by_type.get("Claim", [])
            if n["attrs"].get("honest")]


def q_metrics(gv, orphans, uncited):
    node_counts = {t: len(ns) for t, ns in gv.by_type.items()}
    edge_counts = {}
    for e in gv.edges:
        edge_counts[e["type"]] = edge_counts.get(e["type"], 0) + 1
    anchors = len(gv.by_type.get("Anchor", []))
    cited = anchors - len(uncited)
    verdicts = {"pass": 0, "fail": 0, "degraded": 0}
    for e in gv.supports:
        v = e["attrs"].get("verdict")
        if v in verdicts:
            verdicts[v] += 1
    return {
        "nodes_total": len(gv.nodes), "nodes_by_type": node_counts,
        "edges_total": len(gv.edges), "edges_by_type": edge_counts,
        "anchors": anchors, "anchors_cited": cited,
        "anchor_coverage": (round(cited / anchors, 4)
                            if anchors else None),
        "orphans": len(orphans), "fails": verdicts["fail"],
        "degraded": verdicts["degraded"],
        "conflicts": len(gv.graph.get("conflicts", [])),
    }


QUERIES = {
    "q_orphan_claims": q_orphan_claims,
    "q_coverage_matrix": q_coverage_matrix,
    "q_reused_evidence": q_reused_evidence,
    "q_conflict_list": q_conflict_list,
    "q_evidence_chain": q_evidence_chain,
    "q_uncited_anchors": q_uncited_anchors,
    "q_score_derivation": q_score_derivation,
    "q_honest_flags": q_honest_flags,
}


def render_md(report):
    lines = ["# query_report", "",
             "task_type: %s  " % report.get("task_type"),
             "case_id: %s" % report.get("case_id"), ""]
    lines.append("## q_metrics 图谱汇总指标")
    lines.append("```json")
    lines.append(json.dumps(report["metrics"], ensure_ascii=False,
                            sort_keys=True, indent=2))
    lines.append("```")
    lines.append("")
    q = report["queries"]
    lines.append("## q_coverage_matrix 证据覆盖矩阵（Task × Anchor）")
    matrix = q["q_coverage_matrix"]
    anchors = sorted({a for row in matrix.values() for a in row})
    if anchors:
        lines.append("| Task | " + " | ".join(anchors) + " |")
        lines.append("|" + "---|" * (len(anchors) + 1))
        for t, row in matrix.items():
            lines.append("| %s | %s |" % (
                t, " | ".join(str(row[a]) for a in anchors)))
    else:
        lines.append("（无锚点）")
    lines.append("")
    lines.append("## q_score_derivation 逐题分数推导")
    lines.append("| Task | score | rationale |")
    lines.append("|---|---|---|")
    for t, s in q["q_score_derivation"].items():
        lines.append("| %s | %s | %s |" % (t, s["score"],
                                            s["rationale"]))
    lines.append("")
    lines.append("## q_conflict_list 冲突清单")
    if q["q_conflict_list"]:
        for c in q["q_conflict_list"]:
            lines.append("- `%s` **%s** %s <-> %s：%s" % (
                c["id"], c["kind"], c["node_a"], c["node_b"],
                c["detail"]))
    else:
        lines.append("（无冲突）")
    lines.append("")
    lines.append("## q_orphan_claims 无证据论断")
    if q["q_orphan_claims"]:
        for o in q["q_orphan_claims"]:
            lines.append("- `%s` (task=%s)：%s"
                         % (o["claim"], o["task"], o["text"]))
    else:
        lines.append("（无孤儿）")
    lines.append("")
    lines.append("## q_reused_evidence 多任务复用锚点")
    if q["q_reused_evidence"]:
        for r in q["q_reused_evidence"]:
            lines.append("- `%s` 被 %s 复用"
                         % (r["anchor"], ", ".join(r["tasks"])))
    else:
        lines.append("（无复用）")
    lines.append("")
    lines.append("## q_uncited_anchors 未引用锚点（覆盖盲区）")
    if q["q_uncited_anchors"]:
        for u in q["q_uncited_anchors"]:
            lines.append("- `%s` (%s)：%s"
                         % (u["anchor"], u["kind"], u["preview"]))
    else:
        lines.append("（全部锚点均被引用）")
    lines.append("")
    lines.append("## q_honest_flags 诚实标记清单")
    if q["q_honest_flags"]:
        for h in q["q_honest_flags"]:
            lines.append("- `%s` (task=%s)：%s —— 理由：%s"
                         % (h["claim"], h["task"], h["text"],
                            h["reason"]))
    else:
        lines.append("（无诚实标记）")
    lines.append("")
    lines.append("## q_evidence_chain 逐 Task 证据链")
    for tid, chain in q["q_evidence_chain"].items():
        lines.append("### %s — %s" % (tid, chain["label"][:80]))
        for c in chain["claims"]:
            tag = "（诚实标记）" if c["honest"] else ""
            lines.append("- 论断 `%s`%s：%s" % (c["id"], tag,
                                                 c["text"]))
            for ev in c["evidence"]:
                lines.append("  - 证据 `%s` → 锚点 `%s` [%s]：%s"
                             % (ev["id"], ev["anchor"],
                                ev["verdict"], ev["quote"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="证据图谱预置查询")
    ap.add_argument("--graph", default="/app/work/graph.json")
    ap.add_argument("--out-json", default="/app/work/query_report.json")
    ap.add_argument("--out-md", default="/app/work/query_report.md")
    ap.add_argument("--only", default=None,
                    help="只运行某一个查询（名称见 query_cookbook.md）")
    args = ap.parse_args(argv)

    try:
        with open(args.graph, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except Exception as exc:
        print("[graph_query] ERROR: 无法读取 graph: %s" % exc,
              file=sys.stderr)
        return 1

    try:
        gv = GraphView(graph)
        orphans = q_orphan_claims(gv)
        uncited = q_uncited_anchors(gv)
        results = {}
        for name, fn in QUERIES.items():
            if args.only and name != args.only:
                continue
            results[name] = fn(gv)
        metrics = q_metrics(gv, orphans, uncited)
        report = {"case_id": graph.get("case_id"),
                  "task_type": graph.get("task_type"),
                  "queries": results, "metrics": metrics}
        atomic_write_json(args.out_json, report)
        atomic_write(args.out_md, render_md(report))
        print("[graph_query] queries=%d orphans=%d fails=%d "
              "conflicts=%d coverage=%s -> %s / %s"
              % (len(results), metrics["orphans"], metrics["fails"],
                 metrics["conflicts"],
                 str(metrics["anchor_coverage"]),
                 args.out_json, args.out_md))
        return 0
    except Exception as exc:
        print("[graph_query] ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
