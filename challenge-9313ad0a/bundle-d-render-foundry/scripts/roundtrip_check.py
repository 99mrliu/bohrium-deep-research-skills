#!/usr/bin/env python3
"""roundtrip_check.py — FreeMind .mm 导出结果的往返一致性校验。

用法:
    python3 scripts/roundtrip_check.py --map mindmap.json --mm mindmap.mm \
        --report roundtrip_report.json

将 .mm 解析回 (id, label, parent) 三元组集合与 arrowlink (from, to) 集合，
与源 mindmap.json 严格比对（标签需经 XML 转义往返后逐字符一致；
父结构一致；关系端点一致）。

输出报告:
    {"match": bool,
     "missing_in_mm": [...], "extra_in_mm": [...],
     "label_mismatches": [...], "relation_mismatches": [...]}

退出码: 完全一致为 0，存在差异为 1，输入不可解析为 2。
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET


def load_source(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    triples = set()
    for n in data["nodes"]:
        triples.add((n["id"], str(n["label"]), n.get("parent")))
    rels = set()
    for r in data.get("relations", []):
        rels.add((r["from"], r["to"]))
    return triples, rels


def load_mm(path):
    tree = ET.parse(path)
    root_el = tree.getroot()
    if root_el.tag != "map":
        sys.stderr.write("错误：.mm 根元素不是 <map>。\n")
        sys.exit(2)
    triples = set()
    rels = set()

    def rec(el, parent_id):
        nid = el.get("ID")
        label = el.get("TEXT", "")
        triples.add((nid, label, parent_id))
        for child in el:
            if child.tag == "arrowlink":
                dest = child.get("DESTINATION")
                if dest is not None:
                    rels.add((nid, dest))
            elif child.tag == "node":
                rec(child, nid)

    node_els = [c for c in root_el if c.tag == "node"]
    if not node_els:
        sys.stderr.write("错误：.mm 中不存在根 <node>。\n")
        sys.exit(2)
    rec(node_els[0], None)
    return triples, rels


def fmt_triple(t):
    nid, label, parent = t
    return "%s | label=%r | parent=%s" % (nid, label, parent)


def main():
    ap = argparse.ArgumentParser(description=".mm 往返一致性校验器")
    ap.add_argument("--map", required=True, help="源 mindmap.json 路径")
    ap.add_argument("--mm", required=True, help="待校验 mindmap.mm 路径")
    ap.add_argument("--report", required=True, help="报告 JSON 输出路径")
    args = ap.parse_args()

    src_triples, src_rels = load_source(args.map)
    mm_triples, mm_rels = load_mm(args.mm)

    missing = sorted(fmt_triple(t) for t in src_triples - mm_triples)
    extra = sorted(fmt_triple(t) for t in mm_triples - src_triples)

    src_by_id = {t[0]: t for t in src_triples}
    mm_by_id = {t[0]: t for t in mm_triples}
    label_mismatches = []
    for nid in sorted(set(src_by_id) & set(mm_by_id)):
        if src_by_id[nid][1] != mm_by_id[nid][1]:
            label_mismatches.append({
                "id": nid,
                "expected": src_by_id[nid][1],
                "actual": mm_by_id[nid][1],
            })

    relation_mismatches = (
        ["missing:%s->%s" % (a, b) for a, b in sorted(src_rels - mm_rels)]
        + ["extra:%s->%s" % (a, b) for a, b in sorted(mm_rels - src_rels)]
    )

    match = not (missing or extra or label_mismatches or relation_mismatches)
    report = {
        "match": match,
        "missing_in_mm": missing,
        "extra_in_mm": extra,
        "label_mismatches": label_mismatches,
        "relation_mismatches": relation_mismatches,
    }
    with open(args.report, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    sys.stdout.write("往返校验：%s\n" % ("一致" if match else "存在差异"))
    return 0 if match else 1


if __name__ == "__main__":
    sys.exit(main())
