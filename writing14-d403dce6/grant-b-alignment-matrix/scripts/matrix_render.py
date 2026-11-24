#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix_render.py — 把 consistency_matrix.json 渲染为可嵌入章节稿附录的
markdown 要素对照说明表（Q|G|C|R|K 逐行对齐 + 覆盖统计）。

退出码：0 成功；1 矩阵结构非法；2 参数或输入文件错误。
确定性：同一输入产生字节一致的输出（节点按编号数值排序，无时间戳）。
"""
import argparse
import json
import os
import re
import sys

VERSION = "1.0"
ID_FULL_RE = re.compile(r"[QGCRK][0-9]+\Z")
CLASS_LABEL = {"q": "科学问题", "g": "研究目标", "c": "研究内容",
               "r": "技术路线步骤", "k": "考核指标"}


def num_key(node_id):
    return int(node_id[1:])


def load_matrix(path):
    if not os.path.isfile(path):
        sys.stderr.write("错误：矩阵文件不存在：%s\n" % path)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        sys.stderr.write("错误：矩阵无法解析：%s\n" % exc)
        sys.exit(2)
    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), dict) \
            or not isinstance(doc.get("edges"), list):
        sys.stderr.write("错误：矩阵结构非法（需要 nodes 对象与 edges 数组）。\n")
        sys.exit(1)
    nodes = {}
    for class_key in ("q", "g", "c", "r", "k"):
        for entry in doc["nodes"].get(class_key, []):
            if not isinstance(entry, dict) or "id" not in entry \
                    or not ID_FULL_RE.match(str(entry["id"])):
                sys.stderr.write("错误：矩阵含非法节点：%r\n" % (entry,))
                sys.exit(1)
            nodes[entry["id"]] = entry
    edges = []
    for edge in doc["edges"]:
        if not isinstance(edge, dict) or "from" not in edge or "to" not in edge:
            sys.stderr.write("错误：矩阵含非法边：%r\n" % (edge,))
            sys.exit(1)
        edges.append((edge["from"], edge["to"]))
    return doc, nodes, edges


def cell(ids, nodes, with_title=False):
    if not ids:
        return "—"
    parts = []
    for node_id in ids:
        title = nodes.get(node_id, {}).get("title", "")
        if with_title and title:
            parts.append("%s %s" % (node_id, title))
        else:
            parts.append(node_id)
    return "<br>".join(parts)


def render(doc, nodes, edges):
    lines = []
    lines.append("## 附：要素对照说明（由 matrix_render.py %s 生成）" % VERSION)
    lines.append("")
    lines.append("编号约定：Q=科学问题，G=研究目标，C=研究内容，R=技术路线步骤，K=考核指标；"
                 "对齐关系：G 回应 Q、C 支撑 G、R 落实 C、K 锚定 G。")
    lines.append("")
    lines.append("| Q 科学问题 | G 研究目标 | C 研究内容 | R 技术路线步骤 | K 考核指标 |")
    lines.append("| --- | --- | --- | --- | --- |")

    children = {}   # parent -> [child]
    parents = {}    # child -> [parent]
    for src, dst in edges:
        children.setdefault(dst, []).append(src)
        parents.setdefault(src, []).append(dst)

    g_ids = sorted((i for i in nodes if i.startswith("G")), key=num_key)
    covered_q, covered_g, covered_c = set(), set(), set()
    rows = 0
    for gid in g_ids:
        qs = sorted((q for q in parents.get(gid, []) if q.startswith("Q")), key=num_key)
        cs = sorted((c for c in children.get(gid, []) if c.startswith("C")), key=num_key)
        ks = sorted((k for k in children.get(gid, []) if k.startswith("K")), key=num_key)
        covered_q.update(qs)
        if cs:
            covered_g.add(gid)
        if not cs:
            cs = []
        first = True
        for cid in cs or [None]:
            rs = []
            if cid:
                rs = sorted((r for r in children.get(cid, []) if r.startswith("R")),
                            key=num_key)
                if rs:
                    covered_c.add(cid)
            lines.append("| %s | %s | %s | %s | %s |" % (
                cell(qs, nodes) if first else "（同上）",
                cell([gid], nodes, with_title=True) if first else "（同上）",
                cell([cid], nodes, with_title=True) if cid else "—（缺研究内容）",
                cell(rs, nodes) if rs else "—（缺路线步骤）",
                cell(ks, nodes) if first else "（同上）",
            ))
            rows += 1
            first = False

    # 未挂接到任何 G 的游离节点
    orphan_c = sorted((c for c in nodes if c.startswith("C")
                       and not [p for p in parents.get(c, []) if p.startswith("G")]),
                      key=num_key)
    orphan_r = sorted((r for r in nodes if r.startswith("R")
                       and not [p for p in parents.get(r, []) if p.startswith("C")]),
                      key=num_key)
    orphan_k = sorted((k for k in nodes if k.startswith("K")
                       and not [p for p in parents.get(k, []) if p.startswith("G")]),
                      key=num_key)
    orphan_g = sorted((g for g in g_ids
                       if not [p for p in parents.get(g, []) if p.startswith("Q")]),
                      key=num_key)
    for cid in orphan_c:
        rs = sorted((r for r in children.get(cid, []) if r.startswith("R")), key=num_key)
        lines.append("| ⚠ 未挂接 | — | %s | %s | — |"
                     % (cell([cid], nodes, with_title=True), cell(rs, nodes)))
    for rid in orphan_r:
        lines.append("| ⚠ 未挂接 | — | — | %s | — |" % cell([rid], nodes, with_title=True))
    for kid in orphan_k:
        lines.append("| ⚠ 未挂接 | — | — | — | %s |" % cell([kid], nodes, with_title=True))
    for gid in orphan_g:
        lines.append("| ⚠ 未挂接 | %s | — | — | — |" % cell([gid], nodes, with_title=True))

    counts = {k: sum(1 for i in nodes if i.startswith(k.upper())) for k in CLASS_LABEL}
    total_q = counts["q"] or 1
    total_g = counts["g"] or 1
    total_c = counts["c"] or 1
    lines.append("")
    lines.append("### 覆盖统计")
    lines.append("")
    lines.append("- 节点计数：Q=%d，G=%d，C=%d，R=%d，K=%d；边数=%d"
                 % (counts["q"], counts["g"], counts["c"], counts["r"], counts["k"],
                    len(edges)))
    lines.append("- 被目标回应的科学问题：%d/%d" % (len(covered_q), counts["q"]))
    lines.append("- 被内容支撑的研究目标：%d/%d" % (len(covered_g), counts["g"]))
    lines.append("- 被路线步骤覆盖的研究内容：%d/%d" % (len(covered_c), counts["c"]))
    lines.append("- 对照表行数：%d" % rows)
    if orphan_g or orphan_c or orphan_r or orphan_k:
        lines.append("- ⚠ 存在未挂接节点：G=%s C=%s R=%s K=%s" % (
            ",".join(orphan_g) or "无", ",".join(orphan_c) or "无",
            ",".join(orphan_r) or "无", ",".join(orphan_k) or "无"))
    else:
        lines.append("- 未挂接节点：无")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="把 consistency_matrix.json 渲染为可嵌入章节稿附录的要素对照说明表（markdown）。")
    parser.add_argument("--matrix", required=True, help="consistency_matrix.json 路径")
    parser.add_argument("--out", help="输出 markdown 路径（缺省打印到标准输出）")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    args = parser.parse_args()

    doc, nodes, edges = load_matrix(args.matrix)
    text = render(doc, nodes, edges)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("已写出：%s" % args.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
