#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_all.py — 主编排：校验 → 导出 → 执行查询 → 汇总 result.json（仅标准库）。

设计原则：
  * 语义候选图谱（实体/关系/证据、合并与不合并决策）由 Agent 依据原文撰写，
    本脚本只确定性执行【校验、导出、查询、汇总】，不替 Agent 生成答案；
  * 早存部分结果：每个阶段完成后立即刷新 result.json（status=partial），
    中途失败也保留可人工接管的产物与原因；
  * 全部产物确定性（无时间戳），哈希可复算。

用法：
  python3 run_all.py --case /input/case.json --input-dir /input \
      --work /app/work --out /app/output \
      [--graph /app/work/graph.candidate.json] [--queries /app/work/queries.json]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finalize  # noqa: E402
import kg_validate  # noqa: E402
from kg_export import export_all  # noqa: E402
from kg_loader import GraphLoadError, load_graph  # noqa: E402
import run_queries  # noqa: E402

MATERIAL_NAMES = ("material.json", "primary-material.json", "secondary-material.json")


def find_materials(input_dir):
    found = []
    for name in MATERIAL_NAMES:
        p = os.path.join(input_dir, name)
        if os.path.isfile(p):
            found.append(p)
    # 兜底：input 目录下其它 *.json（除 case.json）也尝试作为材料
    if os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, name)
            if (name.endswith(".json") and name != "case.json"
                    and os.path.isfile(p) and p not in found):
                found.append(p)
    return found


def stage_result(case, out, status, uncertainty, changes, extra=None):
    result = finalize.build_result(case, out, status, uncertainty, changes, extra)
    finalize.write_result(result, out)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="图谱工作流主编排")
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--graph", default=None,
                    help="候选图谱；默认 <work>/graph.candidate.json")
    ap.add_argument("--queries", default=None,
                    help="查询集；默认 <work>/queries.json")
    ap.add_argument("--label", default=None, help="产物标签（如 SYNTHETIC 示例）")
    ap.add_argument("--force-queries", action="store_true",
                    help="查询快照失配时允许重跑（快照如实记录）")
    args = ap.parse_args(argv)

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    case = {}
    if os.path.isfile(args.case):
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    changes = []
    uncertainty = []

    # ---- 阶段 0：输入确认 + 最早的 partial result ----
    if not case:
        uncertainty.append("case.json 缺失或无法解析，case_id 与 output_contract 未知")
    stage_result(case, args.out, "partial",
                 uncertainty + ["工作流刚开始：尚未完成校验/导出/查询"],
                 changes + ["阶段0：写入最早部分结果"])

    graph_path = args.graph or os.path.join(args.work, "graph.candidate.json")
    queries_path = args.queries or os.path.join(args.work, "queries.json")
    if not os.path.isfile(graph_path):
        stage_result(case, args.out, "blocked",
                     uncertainty + ["候选图谱不存在：%s。请由 Agent 依据原文按 "
                                    "references/candidate-graph-spec.md 撰写后重跑。" % graph_path],
                     changes + ["阶段1：阻塞（缺候选图谱）"])
        print("阻塞：候选图谱不存在 %s" % graph_path, file=sys.stderr)
        return 2
    if not os.path.isfile(queries_path):
        uncertainty.append("查询集不存在：%s；仅完成校验与导出，查询阶段标记未完成"
                           % queries_path)

    # ---- 阶段 1：结构 + 证据校验 ----
    materials = find_materials(args.input_dir)
    report_path = os.path.join(args.out, "validation_report.json")
    ok, report = kg_validate.validate(
        graph_path, materials, report_path,
        require_materials=bool(materials))
    changes.append("阶段1：校验完成（structural_ok=%s, evidence_ok=%s, 证据 %d 条）"
                   % (report.get("structural_ok"), report.get("evidence_ok"),
                      report.get("checked_evidence", 0)))
    if not materials:
        uncertainty.append("输入目录无任何可解析材料 JSON，证据核验被跳过（evidence_ok=null）")
    if not ok:
        stage_result(case, args.out, "blocked",
                     uncertainty + ["校验未通过，详见 validation_report.json；"
                                    "修正 graph.candidate.json 后重跑。"],
                     changes, extra={"validation_ok": False})
        print("校验未通过，详见 %s" % report_path, file=sys.stderr)
        return 2
    stage_result(case, args.out, "partial",
                 uncertainty + ["已完成校验，尚未导出/查询"],
                 changes, extra={"validation_ok": True})

    # ---- 阶段 2：导出 ----
    try:
        manifest = export_all(graph_path, args.out, label=args.label)
    except GraphLoadError as exc:
        stage_result(case, args.out, "blocked",
                     uncertainty + ["导出失败：%s" % exc], changes)
        print(str(exc), file=sys.stderr)
        return 2
    changes.append("阶段2：导出 graph.json/jsonl/csv/md/svg + manifest（graph_hash=%s）"
                   % manifest["graph_hash"][:16])
    g = load_graph(graph_path)
    extra = {"validation_ok": True, "graph_hash": manifest["graph_hash"],
             "counts": manifest["counts"],
             "sources": [dict(g.sources[k]) for k in sorted(g.sources)]}
    if args.label:
        extra["label"] = args.label
    stage_result(case, args.out, "partial",
                 uncertainty + ["已完成导出，尚未执行查询"], changes, extra=extra)

    # ---- 阶段 3：执行查询 ----
    query_summary = None
    if os.path.isfile(queries_path):
        qargv = ["--graph", graph_path, "--queries", queries_path,
                 "--out-dir", args.out]
        if args.force_queries:
            qargv.append("--force")
        code = run_queries.main(qargv)
        if code not in (0,):
            uncertainty.append("查询阶段退出码 %d（详见 stderr 与 query_results.json）" % code)
            changes.append("阶段3：查询执行异常（code=%d）" % code)
            stage_result(case, args.out, "partial", uncertainty, changes, extra=extra)
            return code
        with open(os.path.join(args.out, "query_results.json"),
                  "r", encoding="utf-8") as f:
            query_summary = json.load(f)["summary"]
        with open(os.path.join(args.out, "query_snapshot.json"),
                  "r", encoding="utf-8") as f:
            extra["snapshot_hash"] = json.load(f)["snapshot_hash"]
        changes.append("阶段3：执行查询 %d 条（ok=%d empty=%d error=%d）"
                       % (query_summary["total"], query_summary["ok"],
                          query_summary["empty"], query_summary["error"]))
        if query_summary["error"]:
            uncertainty.append("有 %d 条查询返回 error（如未知算子被诚实拒绝），"
                               "详见 query_results.json" % query_summary["error"])
        if query_summary["ok"] < 3:
            uncertainty.append("成功(ok)查询不足 3 条，不满足题目「至少 3 个实际执行查询」"
                               "的覆盖要求，需补充查询后重跑")
    extra["query_summary"] = query_summary

    # ---- 阶段 4：终态汇总 ----
    status = "success" if not uncertainty else "partial"
    final = stage_result(case, args.out, status, uncertainty, changes, extra=extra)
    print("完成：status=%s，产物 %d 个，result.json 已写出。"
          % (status, len(final["artifacts"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
