#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tree_lint.py — 思维导图层级结构体检（lint）工具。

仅依赖 Python 3.10+ 标准库，不进行任何网络访问。

用法:
    python3 scripts/tree_lint.py --map mindmap.json --report lint_report.json [--budget N]

输入（思维导图中间表示）:
    {"meta": {"purpose": "paper|experiment|project|meeting|knowledge",
              "budget": int, "audience": str},
     "root": "<node id>",
     "nodes": [{"id": str, "parent": str|null, "label": str, "kind": str}, ...]}

ERROR 级（存在任一则退出码为 1）:
    duplicate_id        节点 id 重复
    parent_missing      parent 引用了不存在的节点 id
    multiple_roots      多根（parent==null 的节点多于一个，或 meta.root 与之不符）
    cycle               沿 parent 链存在环
    orphan              存在自 meta.root 不可达的节点（孤儿节点）
    empty_label         标签为空或仅含空白

WARN 级（不影响退出码，退出码为 0）:
    long_label              标签显示长度超过 40（中日韩全角字符按 1 计）
    overloaded              同一父节点下子节点数超过 7（分支过载）
    depth                   自根起算的深度超过 5（根深度为 1）
    single_child_chain      单子链：逐节点仅有一个子节点、长度不少于 3 的链
    sibling_near_duplicate  兄弟节点标签近似重复（规范化后相等，或相互包含且长度比 > 0.8）
    kind_mixing             同一兄弟组内 distinct kind 超过 2（分类轴不一致）
    over_budget             节点总数超过预算（--budget 或 meta.budget）
    missing_core_kind       按 meta.purpose 缺失核心 kind（见下）

各 purpose 的核心 kind:
    paper      -> question, method, result, conclusion
    experiment -> method, risk
    project    -> milestone, task, risk
    meeting    -> decision, task
    knowledge  -> （无强制核心 kind）

输出 lint_report.json:
    {"summary": {"errors": n, "warnings": n, "nodes": N,
                 "max_depth": d, "max_children": c},
     "findings": [{"severity": "ERROR"|"WARN", "check": str,
                   "node_ids": [...], "detail": str}, ...]}
findings 按 (check, node_ids) 字典序排序，结果完全确定（同输入必得同输出）。
"""

import argparse
import json
import sys
import unicodedata

MAX_LABEL_LEN = 40
MAX_CHILDREN = 7
MAX_DEPTH = 5

KIND_VOCAB = [
    "question", "method", "evidence", "result", "conclusion", "limitation",
    "task", "risk", "decision", "milestone", "concept", "other",
]

PURPOSE_CORE_KINDS = {
    "paper": ["question", "method", "result", "conclusion"],
    "experiment": ["method", "risk"],
    "project": ["milestone", "task", "risk"],
    "meeting": ["decision", "task"],
    "knowledge": [],
}


def display_len(s):
    """显示长度：每个字符（含 CJK）按 1 计。"""
    return len(s)


def normalize_label(s):
    """规范化标签：转小写，删除全部空白与标点（Unicode P 类）。"""
    out = []
    for ch in s.lower():
        if ch.isspace():
            continue
        if unicodedata.category(ch).startswith("P"):
            continue
        out.append(ch)
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description="思维导图层级结构体检工具")
    ap.add_argument("--map", dest="map_path", required=True, help="思维导图 JSON 路径")
    ap.add_argument("--report", dest="report_path", required=True, help="体检报告输出路径")
    ap.add_argument("--budget", type=int, default=None, help="节点数预算（覆盖 meta.budget）")
    args = ap.parse_args()

    try:
        with open(args.map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"无法读取输入: {e}", file=sys.stderr)
        return 2

    meta = data.get("meta", {}) or {}
    root_id = data.get("root")
    nodes = data.get("nodes", []) or []
    budget = args.budget if args.budget is not None else meta.get("budget")

    findings = []

    def add(severity, check, node_ids, detail):
        findings.append({
            "severity": severity,
            "check": check,
            "node_ids": sorted({str(i) for i in node_ids}),
            "detail": detail,
        })

    # ---- 建立索引（重复 id 取首次出现） -------------------------------------
    by_id = {}
    dup_ids = []
    for n in nodes:
        nid = n.get("id")
        if nid is None:
            continue
        if nid in by_id:
            dup_ids.append(nid)
        else:
            by_id[nid] = n
    if dup_ids:
        add("ERROR", "duplicate_id", dup_ids,
            "节点 id 重复（取首次出现参与后续检查）: " + ", ".join(sorted(dup_ids)))

    # ---- ERROR: parent_missing ---------------------------------------------
    pm = {}
    for n in nodes:
        nid = n.get("id")
        p = n.get("parent")
        if nid in by_id and p is not None and p not in by_id:
            pm.setdefault(nid, p)
    if pm:
        add("ERROR", "parent_missing", pm.keys(),
            "以下节点的 parent 引用不存在的 id: "
            + "; ".join(f"{k} -> {pm[k]}" for k in sorted(pm)))

    # ---- ERROR: multiple_roots ---------------------------------------------
    nulls = [n["id"] for n in nodes if n.get("id") in by_id and n.get("parent") is None]
    root_problems = []
    if len(nulls) != 1:
        root_problems.append(f"parent==null 的节点数为 {len(nulls)}（应为 1）: "
                             + (", ".join(sorted(nulls)) if nulls else "无"))
    if root_id is None:
        root_problems.append("缺少顶层 root 字段")
    elif root_id not in by_id:
        root_problems.append(f"root 指向不存在的节点 id: {root_id}")
    elif by_id[root_id].get("parent") is not None:
        root_problems.append(f"root 节点 {root_id} 的 parent 非 null")
    if root_problems:
        add("ERROR", "multiple_roots",
            nulls + ([root_id] if root_id is not None else []),
            "；".join(root_problems))

    # ---- 邻接表（仅保留两端均存在的边） --------------------------------------
    children = {nid: [] for nid in by_id}
    for n in nodes:
        nid = n.get("id")
        p = n.get("parent")
        if nid in by_id and p in by_id and nid != p:
            children[p].append(nid)
    for nid in children:
        children[nid].sort()

    # ---- ERROR: cycle -------------------------------------------------------
    cycle_nodes = set()
    state = {}
    for start in sorted(by_id):
        path, idx = [], {}
        cur = start
        while cur is not None and cur in by_id:
            if cur in idx:
                cycle_nodes.update(path[idx[cur]:])
                break
            if state.get(cur):
                break
            idx[cur] = len(path)
            path.append(cur)
            cur = by_id[cur].get("parent")
        for x in path:
            state[x] = True
    if cycle_nodes:
        add("ERROR", "cycle", cycle_nodes,
            "沿 parent 链检测到环，涉及节点: " + ", ".join(sorted(cycle_nodes)))

    # ---- ERROR: orphan（自 root 不可达） ------------------------------------
    depth = {}
    if root_id in by_id:
        depth[root_id] = 1
        queue = [root_id]
        while queue:
            cur = queue.pop(0)
            for ch in children[cur]:
                if ch not in depth:
                    depth[ch] = depth[cur] + 1
                    queue.append(ch)
        orphans = [nid for nid in by_id if nid not in depth]
        if orphans:
            add("ERROR", "orphan", orphans,
                "以下节点自 root 不可达（孤儿节点），需人工决策归属或删除: "
                + ", ".join(sorted(orphans)))
    max_depth = max(depth.values()) if depth else 0

    # ---- ERROR: empty_label -------------------------------------------------
    el = [nid for nid in by_id if not str(by_id[nid].get("label", "")).strip()]
    if el:
        add("ERROR", "empty_label", el,
            "以下节点标签为空或仅含空白: " + ", ".join(sorted(el)))

    # ---- WARN: long_label ----------------------------------------------------
    ll = {nid: display_len(str(by_id[nid].get("label", "")))
          for nid in by_id}
    ll = {nid: d for nid, d in ll.items() if d > MAX_LABEL_LEN}
    if ll:
        add("WARN", "long_label", ll.keys(),
            f"标签显示长度超过 {MAX_LABEL_LEN}: "
            + "; ".join(f"{k}（{ll[k]} 字符）" for k in sorted(ll)))

    # ---- WARN: overloaded ----------------------------------------------------
    for pid in sorted(children):
        c = len(children[pid])
        if c > MAX_CHILDREN:
            add("WARN", "overloaded", [pid],
                f"节点 {pid} 有 {c} 个子节点（>{MAX_CHILDREN}），分支过载: "
                + ", ".join(children[pid]))

    # ---- WARN: depth ---------------------------------------------------------
    deep = {nid: d for nid, d in depth.items() if d > MAX_DEPTH}
    if deep:
        add("WARN", "depth", deep.keys(),
            f"以下节点深度超过 {MAX_DEPTH}: "
            + "; ".join(f"{k}（深度 {deep[k]}）" for k in sorted(deep)))

    # ---- WARN: single_child_chain -------------------------------------------
    child_count = {nid: len(children[nid]) for nid in by_id}
    starts = []
    for nid in sorted(by_id):
        if child_count[nid] != 1:
            continue
        p = by_id[nid].get("parent")
        if p is None or p not in by_id or child_count.get(p, 0) != 1:
            starts.append(nid)
    for s in starts:
        run = [s]
        seen = {s}
        cur = s
        while child_count.get(cur) == 1:
            nxt = children[cur][0]
            if nxt in seen:
                break
            run.append(nxt)
            seen.add(nxt)
            cur = nxt
        if len(run) >= 3:
            add("WARN", "single_child_chain", run,
                f"长度为 {len(run)} 的单子链（逐级仅一个子节点）: " + " -> ".join(run))

    # ---- WARN: sibling_near_duplicate ---------------------------------------
    for pid in sorted(children):
        kids = children[pid]
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                a, b = kids[i], kids[j]
                la = str(by_id[a].get("label", ""))
                lb = str(by_id[b].get("label", ""))
                na, nb = normalize_label(la), normalize_label(lb)
                if not na or not nb:
                    continue
                if na == nb:
                    add("WARN", "sibling_near_duplicate", [a, b],
                        f"兄弟节点标签规范化后完全相同: {a}（{la!r}）≡ {b}（{lb!r}）")
                else:
                    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
                    if short in long_ and len(short) / len(long_) > 0.8:
                        add("WARN", "sibling_near_duplicate", [a, b],
                            f"兄弟节点标签相互包含且长度比 {len(short)/len(long_):.2f} > 0.8: "
                            f"{a}（{la!r}）~ {b}（{lb!r}）")

    # ---- WARN: kind_mixing ---------------------------------------------------
    for pid in sorted(children):
        kids = children[pid]
        kinds = [str(by_id[k].get("kind", "other")) for k in kids]
        distinct = sorted(set(kinds))
        if len(distinct) > 2:
            add("WARN", "kind_mixing", [pid],
                f"节点 {pid} 的兄弟组混用 {len(distinct)} 种 kind（>2），分类轴不一致: "
                + ", ".join(distinct))

    # ---- WARN: over_budget ---------------------------------------------------
    if isinstance(budget, int) and len(nodes) > budget:
        add("WARN", "over_budget", [],
            f"节点总数 {len(nodes)} 超过预算 {budget}")

    # ---- WARN: missing_core_kind ---------------------------------------------
    purpose = meta.get("purpose")
    if purpose in PURPOSE_CORE_KINDS and PURPOSE_CORE_KINDS[purpose]:
        present = {str(n.get("kind", "")) for n in nodes}
        missing = [k for k in PURPOSE_CORE_KINDS[purpose] if k not in present]
        if missing:
            add("WARN", "missing_core_kind", [],
                f"purpose={purpose} 要求核心 kind "
                f"{PURPOSE_CORE_KINDS[purpose]}，缺失: " + ", ".join(missing))

    # ---- 汇总与输出 -----------------------------------------------------------
    findings.sort(key=lambda f: (f["check"], f["node_ids"]))
    n_err = sum(1 for f in findings if f["severity"] == "ERROR")
    n_warn = sum(1 for f in findings if f["severity"] == "WARN")
    max_children = max((len(c) for c in children.values()), default=0)
    report = {
        "summary": {
            "errors": n_err,
            "warnings": n_warn,
            "nodes": len(nodes),
            "max_depth": max_depth,
            "max_children": max_children,
        },
        "findings": findings,
    }
    try:
        with open(args.report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as e:
        print(f"无法写入报告: {e}", file=sys.stderr)
        return 2

    print(f"tree_lint: errors={n_err} warnings={n_warn} "
          f"nodes={len(nodes)} max_depth={max_depth} max_children={max_children}")
    return 1 if n_err > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
