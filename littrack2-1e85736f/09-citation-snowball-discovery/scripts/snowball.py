#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""snowball.py — 一轮 backward/forward 引文滚雪球扩展。

输入：graph_load.load_graph() 得到的 Graph、种子 id 列表、时间窗口。
- backward 扩展：种子是边的 source，候选是边的 target（种子的参考文献）。
- forward 扩展：种子是边的 target，候选是边的 source（引用了种子的文献）。
- 每个候选记录：方向集合、来源种子集合、每条边的 locator、距离（一轮恒为 1）、
  种子共被引次数（backward 方向来源种子数）、窗口角色（new / context）。
- 边指向图谱未收录节点 → dangling reference，单独列出。
- 种子在图谱中既无节点也无边 → seeds_missing，单独列出。
绝不外查网络；元数据只取自图谱节点记录。
"""
import json
import sys

from graph_load import load_graph, GraphError


def year_of(record):
    """从节点记录尽力解析年份；解析不到返回 None（调用方必须按 date_unknown 处理）。"""
    if not isinstance(record, dict):
        return None
    for key in ("year", "published_year"):
        v = record.get(key)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    issued = record.get("issued")
    if isinstance(issued, dict):
        dp = issued.get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            if isinstance(dp[0][0], int):
                return dp[0][0]
    for key in ("published", "date", "created", "issued"):
        v = record.get(key)
        if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
            return int(v[:4])
    return None


def in_window(year, window):
    """year 为 None 时返回 None（未知）；否则按 [start, end] 闭区间（精度到年）判定。"""
    if year is None:
        return None
    start = (window or {}).get("start")
    end = (window or {}).get("end")
    if start and "%d-12-31" % year < start:
        return False
    if end and "%d-01-01" % year > end:
        return False
    return True


def expand(graph, seeds, window):
    agg = {}          # candidate_id -> 聚合记录
    dangling = []     # 边指向未收录节点
    seeds_missing = []
    seeds_used = []

    for sid in seeds:
        sid = str(sid)
        bwd = graph.backward_edges(sid)
        fwd = graph.forward_edges(sid)
        if sid not in graph.nodes and not bwd and not fwd:
            seeds_missing.append(sid)
            continue
        seeds_used.append(sid)
        for e in bwd:
            _touch(graph, agg, dangling, e, cand=e["target"], seed=sid, direction="backward")
        for e in fwd:
            _touch(graph, agg, dangling, e, cand=e["source"], seed=sid, direction="forward")

    records = []
    for cid, rec in sorted(agg.items()):
        node = graph.nodes.get(cid, {"record": {}, "locator": None})
        year = year_of(node["record"])
        iw = in_window(year, window)
        role = "context" if iw is False else "new"
        entry = {
            "node_id": cid,
            "doi": node["record"].get("doi") or node["record"].get("DOI"),
            "title": _first(node["record"].get("title")),
            "abstract": node["record"].get("abstract"),
            "year": year,
            "directions": sorted(rec["directions"]),
            "seeds_via": sorted(rec["seeds_via"]),
            "distance": 1,
            "co_citation": len(rec["seeds_backward"]),
            "edges": rec["edges"],
            "node_locator": node["locator"],
            "in_window": iw,
            "role": role,
        }
        if iw is None:
            entry["date_unknown"] = True
        records.append(entry)

    return {
        "seeds_used": seeds_used,
        "seeds_missing": seeds_missing,
        "records": records,
        "dangling_references": dangling,
    }


def _touch(graph, agg, dangling, edge, cand, seed, direction):
    cand = str(cand)
    if cand not in graph.nodes:
        dangling.append({
            "missing_id": cand,
            "from_seed": seed,
            "direction": direction,
            "edge_id": edge["id"],
            "edge_locator": edge["locator"],
        })
        return
    rec = agg.setdefault(cand, {
        "directions": set(), "seeds_via": set(),
        "seeds_backward": set(), "edges": [],
    })
    rec["directions"].add(direction)
    rec["seeds_via"].add(seed)
    if direction == "backward":
        rec["seeds_backward"].add(seed)
    rec["edges"].append({"id": edge["id"], "locator": edge["locator"], "direction": direction})


def _first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def main(argv):
    if len(argv) != 4:
        print("用法: snowball.py <reference_graph.json> <seed_id,逗号分隔> <window.json>",
              file=sys.stderr)
        return 2
    try:
        g = load_graph(argv[1])
    except GraphError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 1
    seeds = [s for s in argv[2].split(",") if s]
    with open(argv[3], encoding="utf-8") as f:
        window = json.load(f)
    json.dump(expand(g, seeds, window), sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
