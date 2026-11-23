#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_queries.py — 批量执行查询并维护「查询快照」以便复核与重跑检测（仅标准库）。

产物（--out-dir）：
  query_results.json   每条查询的 status / 结果 / explain / query_hash / result_hash
  query_snapshot.json  graph_hash + 每条 query_hash + results_hash + snapshot_hash
                       （无时间戳，纯内容哈希，第三方可复算）

重跑失配检测（防止悄悄改查询后冒充旧结果）：
  * 已存在快照且当前 queries/graph 哈希与快照不一致：
      - 默认：拒绝覆盖，退出码 4，stderr 说明失配项；
      - --force：如实重跑，新快照记录 previous_snapshot_hash 与 rerun_after_mismatch=true；
  * --check：只核对不执行；一致退出 0，失配退出 3（用于复核者验证产物未被改动）。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kg_engine import result_hash, run_query  # noqa: E402
from kg_loader import GraphLoadError, load_graph  # noqa: E402

SNAPSHOT = "query_snapshot.json"
RESULTS = "query_results.json"


def _load_json(path, what):
    if not os.path.isfile(path):
        raise SystemExit("%s 不存在: %s" % (what, path))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit("%s 不是合法 UTF-8 JSON: %s（%s）" % (what, path, exc))


def compute_hashes(graph, queries):
    return {
        "graph_hash": graph.graph_hash(),
        "queries": [{"id": q.get("id", "?"), "query_hash": result_hash(q)} for q in queries],
    }


def diff_snapshot(snap, cur):
    """返回失配说明列表（空=一致）。"""
    problems = []
    if snap.get("graph_hash") != cur["graph_hash"]:
        problems.append("graph_hash 失配: 快照 %s ≠ 当前 %s"
                        % (str(snap.get("graph_hash"))[:16], cur["graph_hash"][:16]))
    old = {q["id"]: q["query_hash"] for q in snap.get("queries", [])}
    new = {q["id"]: q["query_hash"] for q in cur["queries"]}
    for qid in sorted(set(old) | set(new)):
        if qid not in old:
            problems.append("查询 %s 为新增（快照中不存在）" % qid)
        elif qid not in new:
            problems.append("查询 %s 已被删除（当前不存在）" % qid)
        elif old[qid] != new[qid]:
            problems.append("查询 %s 内容已改变（query_hash 失配）" % qid)
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="批量执行图谱查询 + 快照管理")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--check", action="store_true",
                    help="只核对快照与当前 graph/queries 是否一致，不执行查询")
    ap.add_argument("--force", action="store_true",
                    help="快照失配时仍重跑（快照中如实记录 rerun_after_mismatch）")
    args = ap.parse_args(argv)

    try:
        g = load_graph(args.graph)
    except GraphLoadError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    qdoc = _load_json(args.queries, "查询文件")
    queries = qdoc.get("queries")
    if not isinstance(queries, list) or not queries:
        print("查询文件缺少非空 queries 列表: %s" % args.queries, file=sys.stderr)
        return 2
    cur = compute_hashes(g, queries)
    snap_path = os.path.join(args.out_dir, SNAPSHOT)

    if args.check:
        if not os.path.isfile(snap_path):
            print("快照不存在，无法核对: %s" % snap_path, file=sys.stderr)
            return 3
        snap = _load_json(snap_path, "快照")
        problems = diff_snapshot(snap, cur)
        if problems:
            print("快照核对失配（%d 项）：" % len(problems), file=sys.stderr)
            for p in problems:
                print(" - " + p, file=sys.stderr)
            return 3
        print("快照核对一致：graph_hash 与全部 %d 条 query_hash 均匹配。" % len(cur["queries"]))
        return 0

    prev_snap = None
    mismatch = []
    if os.path.isfile(snap_path):
        prev_snap = _load_json(snap_path, "快照")
        mismatch = diff_snapshot(prev_snap, cur)
        if mismatch and not args.force:
            print("检测到查询/图谱与既有快照失配，拒绝悄悄重跑（退出码 4）。"
                  "确认是有意修改后请加 --force：", file=sys.stderr)
            for p in mismatch:
                print(" - " + p, file=sys.stderr)
            return 4

    # 实际执行（确定性引擎；结果只依赖图谱与查询内容）
    results = [run_query(g, q) for q in queries]
    os.makedirs(args.out_dir, exist_ok=True)
    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_empty = sum(1 for r in results if r["status"] == "empty")
    n_err = sum(1 for r in results if r["status"] == "error")
    results_doc = {
        "graph_hash": cur["graph_hash"],
        "summary": {"total": len(results), "ok": n_ok, "empty": n_empty, "error": n_err},
        "results": results,
    }
    results_doc["results_hash"] = result_hash(results_doc["results"])
    with open(os.path.join(args.out_dir, RESULTS), "w", encoding="utf-8") as f:
        json.dump(results_doc, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    snap = {"graph_hash": cur["graph_hash"], "queries": cur["queries"],
            "results_hash": results_doc["results_hash"]}
    if prev_snap is not None and mismatch:
        snap["rerun_after_mismatch"] = True
        snap["previous_snapshot_hash"] = prev_snap.get("snapshot_hash")
        snap["mismatch_items"] = mismatch
    snap["snapshot_hash"] = result_hash({k: v for k, v in snap.items() if k != "snapshot_hash"})
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print("已执行 %d 条查询：ok=%d empty=%d error=%d（快照 %s）"
          % (len(results), n_ok, n_empty, n_err, snap["snapshot_hash"][:16]))
    for r in results:
        print("  %-4s %-15s %s" % (r["id"], r["op"], r["status"]))
    if snap.get("rerun_after_mismatch"):
        print("注意：本次为失配后 --force 重跑，快照已记录 previous_snapshot_hash。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
