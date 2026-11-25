#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_minimal_example.py — 端到端运行 examples/minimal 合成示例并自检。

步骤：读 case.json → 加载图谱 → 一轮滚雪球 → 读关键词快照 → 渠道合并 →
互补增益与诊断 → 排序 → 组装 result.json → 自检（渠道三分、context/dangling 隔离、
增益数字、output_contract 覆盖）→ bundle 体积/文件数约束自查。

完全离线，仅用标准库。用法：python3 run_minimal_example.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.dirname(HERE)
EXAMPLE = os.path.join(BUNDLE, "examples", "minimal")
sys.path.insert(0, HERE)

from graph_load import load_graph, GraphError          # noqa: E402
from snowball import expand                            # noqa: E402
from channel_merge import load_keyword_candidates, merge  # noqa: E402
from complementarity import metrics, diagnose          # noqa: E402
from assemble_result import assemble, write_result     # noqa: E402

# 示例材料的期望埋点（见 examples/minimal/materials 与 README 说明）
EXPECT = {
    "both": 1, "graph_only": 2, "keyword_only": 1,
    "context": 1, "dangling": 1, "graph_unique_gain": 0.5,
}


def rel(p):
    return os.path.relpath(p, BUNDLE)


def rank_new(merged):
    """排序依据透明化：距离升序 → 共被引降序 → both 优先 → id 升序。"""
    criteria = [
        "1) 图谱距离升序（一轮扩展恒为 1；关键词独有候选记 null 排后）",
        "2) 种子共被引次数降序（backward 方向来源种子数）",
        "3) 渠道优先级 both > graph_only > keyword_only",
        "4) id 字典序（稳定次序）",
    ]
    chan_rank = {"both": 0, "graph_only": 1, "keyword_only": 2}
    pool = merged["both"] + merged["graph_only"] + merged["keyword_only"]

    def key(it):
        d = it.get("distance")
        return (d if isinstance(d, int) else 99, -(it.get("co_citation") or 0),
                chan_rank.get(it.get("channel"), 9), it.get("id", ""))

    ranked = []
    for i, it in enumerate(sorted(pool, key=key), 1):
        ranked.append({
            "rank": i, "id": it.get("id"), "channel": it.get("channel"),
            "distance": it.get("distance"), "co_citation": it.get("co_citation"),
            "reason": "distance=%s, co_citation=%s, channel=%s" % (
                it.get("distance"), it.get("co_citation"), it.get("channel")),
        })
    return {"criteria": criteria, "ranked": ranked}


def check_bundle_constraints():
    """硬性约束自查：≤50 文件、单文件 ≤500KB、总计 ≤2MB、无符号链接、每个文件带扩展名。"""
    files, total = [], 0
    problems = []
    for root, dirs, names in os.walk(BUNDLE):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            p = os.path.join(root, name)
            if os.path.islink(p):
                problems.append("符号链接: %s" % rel(p))
                continue
            size = os.path.getsize(p)
            files.append((rel(p), size))
            total += size
            if size > 500 * 1024:
                problems.append("单文件超 500KB: %s (%dB)" % (rel(p), size))
            if "." not in name:
                problems.append("文件无扩展名: %s" % rel(p))
    if len(files) > 50:
        problems.append("文件数超 50: %d" % len(files))
    if total > 2 * 1024 * 1024:
        problems.append("总体积超 2MB: %dB" % total)
    return {"file_count": len(files), "total_bytes": total, "problems": problems}


def main():
    gaps, partial = [], []

    # 1) 读案例
    with open(os.path.join(EXAMPLE, "case.json"), encoding="utf-8") as f:
        case = json.load(f)
    task = case.get("task", {})
    seeds, terms = task.get("seeds", []), task.get("query_terms", [])
    window = case.get("window") or {}
    materials_dir = os.path.join(BUNDLE, case.get("materials_dir", ""))
    output_dir = os.path.join(BUNDLE, case.get("output_dir", ""))

    # 2) 定位材料（案例显式给出；此处附兜底逻辑演示）
    graph_path = os.path.join(materials_dir, "reference_graph.json")
    snapshot_path = os.path.join(materials_dir, "crossref_response.json")
    for p, label in ((graph_path, "reference_graph.json"), (snapshot_path, "crossref_response.json")):
        if not os.path.isfile(p):
            gaps.append("材料缺失: %s" % label)
            partial.append("material missing: %s" % label)

    # 3) 加载图谱 + 4) 一轮滚雪球
    try:
        graph = load_graph(graph_path)
        expansion = expand(graph, seeds, window)
    except GraphError as e:
        graph, expansion = None, None
        gaps.append("图谱加载失败: %s" % e)
        partial.append("graph load failed")

    # 5) 关键词候选
    try:
        kw_candidates, kw_base = load_keyword_candidates(snapshot_path)
    except Exception as e:  # noqa: BLE001 — 诚实降级
        kw_candidates, kw_base = [], None
        gaps.append("关键词快照解析失败: %s" % e)
        partial.append("snapshot parse failed")

    # 6) 合并（context / dangling 单独成列，不参与合并）
    if expansion is not None:
        new_records = [r for r in expansion["records"] if r["role"] == "new"]
        context_records = [r for r in expansion["records"] if r["role"] == "context"]
        merged = merge(new_records, kw_candidates)
    else:
        context_records = []
        merged = {"both": [], "graph_only": [], "keyword_only": []}

    # 7) 互补增益与诊断
    comp = metrics(merged)
    comp["diagnosis"] = diagnose(merged["graph_only"], terms)

    # 8) 排序
    ranking = rank_new(merged)

    # 9) 组装
    sections = {
        "task_echo": {"seeds": seeds, "query_terms": terms},
        "window": window,
        "channels": {
            "keyword": {
                "source": rel(snapshot_path),
                "candidate_count": len(kw_candidates),
                "locator_base": kw_base,
            },
            "graph": {
                "source": rel(graph_path),
                "summary": graph.summary() if graph else None,
                "seed_count": len(seeds),
                "seeds_used": expansion["seeds_used"] if expansion else [],
                "seeds_missing": expansion["seeds_missing"] if expansion else seeds,
            },
        },
        "expansion": {
            "records": expansion["records"] if expansion else None,
            "dangling_references": expansion["dangling_references"] if expansion else None,
            "seeds_used": expansion["seeds_used"] if expansion else None,
            "seeds_missing": expansion["seeds_missing"] if expansion else None,
        },
        "merged": {
            "both": merged["both"],
            "graph_only": [{k: v for k, v in it.items() if k != "abstract"}
                           for it in merged["graph_only"]],
            "keyword_only": [{k: v for k, v in it.items() if k != "abstract"}
                             for it in merged["keyword_only"]],
            "context": context_records,
        },
        "complementarity": comp,
        "ranking": ranking,
        "gaps": gaps,
        "notes": [
            "本示例为显式标注的合成数据（synthetic），不对应任何真实文献；DOI 均为保留测试段 10.5555/*。",
            "所有引文边仅取自 materials/reference_graph.json；关键词候选仅取自 materials/crossref_response.json；全程离线。",
        ],
    }
    result = assemble(case, sections, gaps=gaps, partial_reasons=partial,
                      generated_by="citation-snowball-discovery run_minimal_example.py (synthetic example)")
    out_path = os.path.join(output_dir, "result.json")
    write_result(result, out_path)

    # 10) 自检
    checks = []
    counts = comp["counts"]
    checks.append(("both == %d" % EXPECT["both"], counts["both"] == EXPECT["both"]))
    checks.append(("graph_only == %d" % EXPECT["graph_only"], counts["graph_only"] == EXPECT["graph_only"]))
    checks.append(("keyword_only == %d" % EXPECT["keyword_only"], counts["keyword_only"] == EXPECT["keyword_only"]))
    checks.append(("context 条数 == %d 且与合并隔离" % EXPECT["context"],
                   len(context_records) == EXPECT["context"]
                   and all(c["node_id"] not in {b["id"] for b in merged["both"] + merged["graph_only"]}
                           for c in context_records)))
    dang = expansion["dangling_references"] if expansion else []
    checks.append(("dangling == %d 且未混入候选" % EXPECT["dangling"],
                   len(dang) == EXPECT["dangling"]
                   and all(d["missing_id"] not in {r["node_id"] for r in expansion["records"]}
                           for d in dang)))
    gain = comp["graph_unique_gain"]
    checks.append(("graph_unique_gain == %.3f" % EXPECT["graph_unique_gain"],
                   gain is not None and abs(gain - EXPECT["graph_unique_gain"]) < 1e-9))
    # graph_only 埋点：标题与摘要均不含任何查询词
    diag_ok = all(
        any("标题不含任何查询词" in r for r in d["reasons"])
        and any("摘要不含任何查询词" in r for r in d["reasons"])
        for d in comp["diagnosis"]) and len(comp["diagnosis"]) == EXPECT["graph_only"]
    checks.append(("graph_only 诊断：标题/摘要均不含查询词（共 %d 条）" % EXPECT["graph_only"], diag_ok))
    # 共被引埋点：ref-1 被两颗种子共同引用
    ref1 = [r for r in expansion["records"] if r["node_id"] == "ref-1"]
    checks.append(("ref-1 共被引 == 2", bool(ref1) and ref1[0]["co_citation"] == 2))
    # output_contract 覆盖
    contract = case.get("output_contract", [])
    checks.append(("output_contract 全部字段存在", all(f in result for f in contract)))
    # 边 locator 回指抽查：每条引用过的边都能在图谱文件里找到
    with open(graph_path, encoding="utf-8") as f:
        raw_graph = json.load(f)
    n_edges = len(raw_graph.get("edges", []))
    loc_ok = True
    for r in expansion["records"]:
        for e in r["edges"]:
            idx = int(e["locator"].split("/")[-1])
            if not (0 <= idx < n_edges):
                loc_ok = False
    checks.append(("边 locator 均可回指图谱文件", loc_ok))

    bundle_check = check_bundle_constraints()
    checks.append(("bundle 约束自查（≤50 文件 / ≤500KB / ≤2MB / 无符号链接 / 带扩展名）",
                   not bundle_check["problems"]))

    print("== result.json: %s (status=%s)" % (rel(out_path), result["status"]))
    print("== 渠道计数: %s" % json.dumps(counts, ensure_ascii=False))
    print("== graph_unique_gain = %s" % gain)
    print("== context: %s" % [c["node_id"] for c in context_records])
    print("== dangling: %s" % [d["missing_id"] for d in dang])
    print("== bundle: %d 个文件, %d 字节" % (bundle_check["file_count"], bundle_check["total_bytes"]))
    failed = False
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), "-", name)
        failed = failed or not ok
    if failed:
        print("自检未全部通过", file=sys.stderr)
        return 1
    print("全部自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
