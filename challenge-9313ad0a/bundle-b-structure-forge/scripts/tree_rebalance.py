#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tree_rebalance.py — 思维导图层级结构确定性自动再平衡工具。

仅依赖 Python 3.10+ 标准库，不进行任何网络访问。

用法:
    python3 scripts/tree_rebalance.py --map mindmap.json --out rebalanced.json --changes changes.jsonl

按固定顺序执行以下结构性修复（全程确定：同输入必得同输出）:

    (1) merge_duplicate   合并规范化后完全相同的兄弟标签：
                          保留 id 字典序最小者，其余节点的子节点改挂到保留节点下；
                          绝不跨父节点合并。
    (2) collapse_chain    折叠单子链：某节点恰有一个子节点且无兄弟节点时，
                          将该节点并入其子节点（保留子节点及其标签），迭代至不动点。
    (3) split_overloaded  拆分子节点数超过 7 的兄弟组：按 kind 分组，
                          插入中间分组节点，标签为 "<kind>类"，
                          id 为 "<parentid>-grp-<kind>"（按 kind 字典序排列）。
                          单一 kind 组内仍超过 7 个时按每 7 个一段分块（id 追加 -1、-2…）；
                          若分组数本身超过 7，保留最大的 6 组、其余并入 "other类"。
                          子节点全部为分组节点（id 以 "<parentid>-grp-" 开头）时跳过，
                          以保证幂等。
    (4) truncate_label    标签显示长度超过 40 时，在字符边界截断至总长 40
                          （前 39 字符 + "…"）。

不修复、仅应由 tree_lint.py 报告的结构错误：多根、环、孤儿节点、parent 引用缺失。
本工具只做结构性调整，不改写语义；被移除节点的原始 label/kind 记录在变更行中。

输出:
    rebalanced.json  与输入同 schema（meta/root/nodes），节点按 id 排序、键序规范化，
                     因此幂等：对已干净的树再运行将得到逐字节相同的输出与空变更文件。
    changes.jsonl    每行一个 JSON 对象 {"op": ...}，按修复阶段顺序排列；
                     无任何修复时为空文件。
"""

import argparse
import json
import sys

MAX_LABEL_LEN = 40
MAX_CHILDREN = 7


def display_len(s):
    return len(s)


def normalize_label(s):
    import unicodedata
    out = []
    for ch in s.lower():
        if ch.isspace():
            continue
        if unicodedata.category(ch).startswith("P"):
            continue
        out.append(ch)
    return "".join(out)


def build_children(by_id):
    children = {nid: [] for nid in by_id}
    for nid, n in by_id.items():
        p = n.get("parent")
        if p in by_id and p != nid:
            children[p].append(nid)
    for nid in children:
        children[nid].sort()
    return children


def main():
    ap = argparse.ArgumentParser(description="思维导图层级结构确定性自动再平衡工具")
    ap.add_argument("--map", dest="map_path", required=True, help="思维导图 JSON 路径")
    ap.add_argument("--out", dest="out_path", required=True, help="再平衡结果输出路径")
    ap.add_argument("--changes", dest="changes_path", required=True, help="变更记录（JSONL）输出路径")
    args = ap.parse_args()

    try:
        with open(args.map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"无法读取输入: {e}", file=sys.stderr)
        return 2

    root_id = data.get("root")
    by_id = {}
    for n in data.get("nodes", []) or []:
        nid = n.get("id")
        if nid is not None and nid not in by_id:
            by_id[nid] = dict(n)

    changes = []

    # ---- (1) merge_duplicate（迭代至不动点） --------------------------------
    while True:
        children = build_children(by_id)
        merged = False
        for pid in sorted(children):
            groups = {}
            for cid in children[pid]:  # 已按 id 字典序
                key = normalize_label(str(by_id[cid].get("label", "")))
                if key:
                    groups.setdefault(key, []).append(cid)
            for key in sorted(groups):
                g = groups[key]
                if len(g) <= 1:
                    continue
                keep = g[0]  # 字典序最小
                for other in g[1:]:
                    moved = sorted(children.get(other, []))
                    for gc in moved:
                        by_id[gc]["parent"] = keep
                    changes.append({
                        "op": "merge_duplicate",
                        "kept": keep,
                        "removed": other,
                        "removed_label": by_id[other].get("label", ""),
                        "removed_kind": by_id[other].get("kind", ""),
                        "reparented_children": moved,
                    })
                    del by_id[other]
                    merged = True
        if not merged:
            break

    # ---- (2) collapse_chain（迭代至不动点） ---------------------------------
    while True:
        children = build_children(by_id)
        target = None
        for nid in sorted(by_id):
            if nid == root_id:
                continue
            p = by_id[nid].get("parent")
            if p not in by_id:
                continue
            if len(children.get(nid, [])) == 1 and len(children.get(p, [])) == 1:
                target = nid  # 恰有一个子节点且无兄弟
                break
        if target is None:
            break
        child = children[target][0]
        new_parent = by_id[target]["parent"]
        by_id[child]["parent"] = new_parent
        changes.append({
            "op": "collapse_chain",
            "removed": target,
            "kept": child,
            "removed_label": by_id[target].get("label", ""),
            "removed_kind": by_id[target].get("kind", ""),
            "new_parent": new_parent,
        })
        del by_id[target]

    # ---- (3) split_overloaded（单次确定性扫描，含幂等防护） ------------------
    children = build_children(by_id)
    for pid in sorted(children):
        kids = children[pid]
        if len(kids) <= MAX_CHILDREN:
            continue
        if all(k.startswith(pid + "-grp-") for k in kids):
            continue  # 已拆分过，保证幂等
        by_kind = {}
        for k in kids:
            by_kind.setdefault(str(by_id[k].get("kind", "other")), []).append(k)
        groups = []  # (kind, suffix, members)
        for kind in sorted(by_kind):
            members = by_kind[kind]
            if len(members) > MAX_CHILDREN:
                for i in range(0, len(members), MAX_CHILDREN):
                    groups.append((kind, f"-{i // MAX_CHILDREN + 1}",
                                   members[i:i + MAX_CHILDREN]))
            else:
                groups.append((kind, "", members))
        if len(groups) > MAX_CHILDREN:
            groups.sort(key=lambda g: (-len(g[2]), g[0], g[1]))
            kept = groups[:MAX_CHILDREN - 1]
            rest = groups[MAX_CHILDREN - 1:]
            merged_members = sorted(m for _, _, ms in rest for m in ms)
            kept.append(("other", "", merged_members))
            groups = sorted(kept, key=lambda g: (g[0], g[1]))
        created = []
        used_ids = set(by_id)
        for kind, suffix, members in groups:
            gid = f"{pid}-grp-{kind}{suffix}"
            n_extra = 2
            while gid in used_ids:
                gid = f"{pid}-grp-{kind}{suffix}-{n_extra}"
                n_extra += 1
            used_ids.add(gid)
            by_id[gid] = {"id": gid, "parent": pid,
                          "label": f"{kind}类", "kind": kind}
            for m in members:
                by_id[m]["parent"] = gid
            created.append({"id": gid, "label": f"{kind}类",
                            "kind": kind, "children": members})
        changes.append({
            "op": "split_overloaded",
            "parent": pid,
            "created": created,
        })

    # ---- (4) truncate_label ---------------------------------------------------
    for nid in sorted(by_id):
        label = str(by_id[nid].get("label", ""))
        if display_len(label) > MAX_LABEL_LEN:
            new_label = label[:MAX_LABEL_LEN - 1] + "…"
            changes.append({
                "op": "truncate_label",
                "node": nid,
                "original_label": label,
                "new_label": new_label,
            })
            by_id[nid]["label"] = new_label

    # ---- 输出 ------------------------------------------------------------------
    out = {
        "meta": data.get("meta", {}),
        "root": root_id,
        "nodes": [by_id[k] for k in sorted(by_id)],
    }
    try:
        with open(args.out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        with open(args.changes_path, "w", encoding="utf-8") as f:
            for c in changes:
                f.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as e:
        print(f"无法写入输出: {e}", file=sys.stderr)
        return 2

    print(f"tree_rebalance: nodes={len(by_id)} ops={len(changes)} "
          f"({', '.join(c['op'] for c in changes) if changes else '无变更'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
