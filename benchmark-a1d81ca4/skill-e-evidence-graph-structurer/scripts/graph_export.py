#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_export.py — 导出交付物到 /app/output。

产物：
  evidence_graph.json   完整图谱 + graph_metrics
  graph_map.md          人类可读图谱（逐 Task 证据链与冲突）
  result.json           契约驱动：动态读取 output_contract 字段名，
                        从工作文件（--work-file）同名键拷贝；
                        缺失字段填 null 并记入 uncertainty
  failure_analysis.md   孤儿与 fail 边的题目 ID、摘录、原因、修法

交付门禁：存在孤儿（无 supports 边的非诚实 claim）或未处理 fail 边时，
仍写出全部文件便于排查，但 result.json 记 status=部分完成 且以退出码
2 拦截交付（--force 可跳过拦截）。

用法：
  python3 graph_export.py --graph /app/work/graph.json \
      --case /input/case.json --work-file /app/work/result_fields.json \
      --outdir /app/output [--force]
"""
import argparse
import json
import os
import sys
import tempfile


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


def analyze(graph):
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    supports = [e for e in edges if e["type"] == "supports"]
    supported = {e["dst"] for e in supports}
    orphans = [n for n in graph.get("nodes", [])
               if n.get("type") == "Claim"
               and not n.get("attrs", {}).get("honest")
               and n["id"] not in supported]
    fails = []
    for e in supports:
        if e["attrs"].get("verdict") == "fail":
            ev = nodes.get(e["src"], {})
            claim = nodes.get(e["dst"], {})
            fails.append({
                "evidence": e["src"], "claim": e["dst"],
                "task": claim.get("attrs", {}).get("task"),
                "anchor": ev.get("attrs", {}).get("anchor"),
                "quote": ev.get("attrs", {}).get("quote", ""),
                "reason": e["attrs"].get("reason", "")})
    node_counts, edge_counts = {}, {}
    for n in graph.get("nodes", []):
        node_counts[n["type"]] = node_counts.get(n["type"], 0) + 1
    for e in edges:
        edge_counts[e["type"]] = edge_counts.get(e["type"], 0) + 1
    anchors = node_counts.get("Anchor", 0)
    cited = set()
    derived = [e for e in edges if e["type"] == "derived_from"]
    pass_evs = {e["src"] for e in supports
                if e["attrs"].get("verdict") == "pass"}
    for e in derived:
        if e["src"] in pass_evs:
            cited.add(e["dst"])
    metrics = {
        "nodes_total": len(graph.get("nodes", [])),
        "nodes_by_type": node_counts,
        "edges_total": len(edges),
        "edges_by_type": edge_counts,
        "anchors": anchors, "anchors_cited": len(cited),
        "anchor_coverage": (round(len(cited) / anchors, 4)
                            if anchors else None),
        "orphans": len(orphans), "fails": len(fails),
        "conflicts": len(graph.get("conflicts", [])),
    }
    return nodes, edges, orphans, fails, metrics


def render_graph_map(graph, nodes, edges, metrics):
    lines = ["# graph_map 证据图谱（人类可读）", "",
             "- case_id: %s" % graph.get("case_id"),
             "- task_type: %s" % graph.get("task_type"),
             "- 节点 %d / 边 %d / 锚点覆盖率 %s / 孤儿 %d / fail %d / 冲突 %d"
             % (metrics["nodes_total"], metrics["edges_total"],
                str(metrics["anchor_coverage"]), metrics["orphans"],
                metrics["fails"], metrics["conflicts"]), ""]
    answers = [e for e in edges if e["type"] == "answers"]
    supports = [e for e in edges if e["type"] == "supports"]
    derived = [e for e in edges if e["type"] == "derived_from"]
    governed = [e for e in edges if e["type"] == "governed_by"]
    anchor_of = {e["src"]: e["dst"] for e in derived}
    for n in graph.get("nodes", []):
        if n["type"] != "Task":
            continue
        tid = n["id"]
        lines.append("## Task %s — %s" % (tid,
                                          n["attrs"].get("label", "")))
        claims = [e["src"] for e in answers if e["dst"] == tid]
        if not claims:
            lines.append("（暂无论断挂接）")
        for cid in claims:
            cn = nodes.get(cid, {})
            ca = cn.get("attrs", {})
            tag = "（诚实标记：%s）" % ca.get("honest_reason", "") \
                if ca.get("honest") else ""
            lines.append("- 论断 `%s`%s" % (cid, tag))
            lines.append("  - 内容：%s" % ca.get("text", ""))
            if ca.get("kind") == "item":
                lines.append("  - 参考答案：%s"
                             % ca.get("reference_answer", ""))
                rules = [e["dst"] for e in governed if e["src"] == cid]
                for rid in rules:
                    rn = nodes.get(rid, {})
                    lines.append("  - 评分规则 `%s`：%s"
                                 % (rid, rn.get("attrs", {})
                                    .get("text", "")))
            for e in supports:
                if e["dst"] != cid:
                    continue
                ev = nodes.get(e["src"], {})
                lines.append("  - 证据 `%s` → 锚点 `%s` [%s/%s]"
                             % (e["src"], anchor_of.get(e["src"]),
                                e["attrs"].get("verdict"),
                                e["attrs"].get("reason")))
                lines.append("    引文：%s"
                             % ev.get("attrs", {}).get("quote", ""))
        lines.append("")
    lines.append("## 冲突清单")
    if graph.get("conflicts"):
        for c in graph["conflicts"]:
            lines.append("- `%s` **%s** %s <-> %s：%s"
                         % (c["id"], c["kind"], c["node_a"],
                            c["node_b"], c["detail"]))
    else:
        lines.append("（无冲突）")
    lines.append("")
    return "\n".join(lines)


def render_failure_analysis(orphans, fails, conflicts):
    lines = ["# failure_analysis 失败分析", ""]
    lines.append("## 孤儿论断（无 supports 边且未标诚实）")
    if orphans:
        for o in orphans:
            a = o.get("attrs", {})
            lines.append("- 题目 %s / 论断 `%s`" % (a.get("task"),
                                                    o["id"]))
            lines.append("  - 摘录：%s" % a.get("text", ""))
            lines.append("  - 原因：起草时未附任何证据")
            lines.append("  - 修法：补充逐字证据并重新 graph_link；"
                         "若源文确实无据，改为诚实标记"
                         "（honest=true + honest_reason）")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## fail 边（逐字核验未通过）")
    if fails:
        for f in fails:
            lines.append("- 题目 %s / 论断 `%s` / 证据 `%s`"
                         % (f["task"], f["claim"], f["evidence"]))
            lines.append("  - 锚点：%s" % f["anchor"])
            lines.append("  - 摘录：%s" % f["quote"])
            lines.append("  - 原因：%s" % f["reason"])
            lines.append("  - 修法：anchor_not_found → 核对锚点 ID；"
                         "verbatim_mismatch → 回到锚点原文逐字引用"
                         "（允许 NFKC/连字/断词/空白归一化），"
                         "随后重新 graph_link")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 未解决冲突（需在答案中显式说明）")
    if conflicts:
        for c in conflicts:
            lines.append("- `%s` %s：%s" % (c["id"], c["kind"],
                                            c["detail"]))
    else:
        lines.append("（无）")
    lines.append("")
    return "\n".join(lines)


def build_result(graph, metrics, orphans, fails, work):
    result = {"case_id": graph.get("case_id")}
    missing = []
    for field in graph.get("contract_fields", []):
        value = work.get(field)
        result[field] = value
        if value is None:
            missing.append(field)
    blocked = bool(orphans or fails)
    reasons = []
    if blocked:
        reasons.append("交付门禁未通过：孤儿 %d 个、fail 边 %d 条"
                       % (len(orphans), len(fails)))
    if missing:
        reasons.append("output_contract 字段缺失（置 null）：%s"
                       % ", ".join(missing))
    if graph.get("case_id") is None:
        status = "无法判断"
        reasons.insert(0, "case.json 缺失或不可解析，case_id 未知")
    elif blocked or missing:
        status = "部分完成"
    else:
        status = "成功"
        reasons.append("全部 output_contract 字段已填充，图谱门禁通过")
    result["status"] = status
    result["status_reason"] = "；".join(reasons)
    result["sources"] = [
        {"id": n["id"], "path": n["attrs"].get("path"),
         "sha256": n["attrs"].get("sha256")}
        for n in graph.get("nodes", []) if n["type"] == "Source"]
    uncertainty = list(work.get("uncertainty", []) or [])
    for f in missing:
        uncertainty.append("字段 %s 无法填充，已置 null" % f)
    for c in graph.get("conflicts", []):
        uncertainty.append("未解决冲突 %s（%s）：%s"
                           % (c["id"], c["kind"], c["detail"]))
    result["uncertainty"] = uncertainty
    records = list(work.get("change_records", []) or [])
    records.append({"seq": len(records) + 1, "action": "export",
                    "detail": "graph_export 生成 result.json（status=%s）"
                              % status})
    result["change_records"] = records
    result["graph_metrics"] = metrics
    return result, blocked


def main(argv=None):
    ap = argparse.ArgumentParser(description="导出图谱交付物")
    ap.add_argument("--graph", default="/app/work/graph.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work-file", default="/app/work/result_fields.json",
                    help="agent 起草的合同字段工作文件（JSON object）")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--force", action="store_true",
                    help="门禁未通过时仍以退出码 0 结束")
    args = ap.parse_args(argv)

    try:
        with open(args.graph, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except Exception as exc:
        print("[graph_export] ERROR: 无法读取 graph: %s" % exc,
              file=sys.stderr)
        return 1

    work = {}
    if os.path.isfile(args.work_file):
        try:
            with open(args.work_file, "r", encoding="utf-8") as fh:
                work = json.load(fh)
            if not isinstance(work, dict):
                work = {}
        except Exception:
            work = {}

    try:
        os.makedirs(args.outdir, exist_ok=True)
        nodes, edges, orphans, fails, metrics = analyze(graph)
        result, blocked = build_result(graph, metrics, orphans,
                                       fails, work)
        exported = dict(graph)
        exported["graph_metrics"] = metrics
        atomic_write_json(os.path.join(args.outdir,
                                       "evidence_graph.json"), exported)
        atomic_write(os.path.join(args.outdir, "graph_map.md"),
                     render_graph_map(graph, nodes, edges, metrics))
        atomic_write(os.path.join(args.outdir, "failure_analysis.md"),
                     render_failure_analysis(
                         orphans, fails, graph.get("conflicts", [])))
        atomic_write_json(os.path.join(args.outdir, "result.json"),
                          result)
        print("[graph_export] status=%s orphans=%d fails=%d "
              "conflicts=%d -> %s"
              % (result["status"], len(orphans), len(fails),
                 metrics["conflicts"], args.outdir))
        if blocked and not args.force:
            print("[graph_export] GATE BLOCKED：存在孤儿或 fail 边，"
                  "详见 failure_analysis.md（--force 可跳过）",
                  file=sys.stderr)
            return 2
        return 0
    except Exception as exc:
        print("[graph_export] ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
