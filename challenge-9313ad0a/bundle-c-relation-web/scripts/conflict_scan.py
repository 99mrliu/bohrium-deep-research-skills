#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conflict_scan.py — 数值冲突候选启发式扫描器（Python 3.10+ 标准库）。

用法：
    python3 conflict_scan.py --nodes nodes.json --material pages.jsonl \
        --out conflict_candidates.json

机制：
    在每个节点标签与每页材料文本上运行正则
        ([\\u4e00-\\u9fffA-Za-z]{2,12})[^\\d]{0,8}(\\d+(?:\\.\\d+)?)\\s*(单位)?
    提取 (规范化键, 数值, 单位, 出处)。键的规范化：折叠空白、剥离尾部动词
    （为/达到/降至/升高到 等）。按 (键, 单位) 分组；同组出现 ≥2 个不同数值
    且出处不同（不同节点或不同材料页）时，输出一条冲突候选，建议处置为
    conflicts_with 边或 uncertainty 条目。

输出 conflict_candidates.json：
    {"candidates":[{"key","unit","values":[{"value","where":{"kind":"node|material",
                    "ref":...}}],"suggestion":"conflicts_with|uncertainty"}]}
    candidates 按 key 排序，values 按 value 排序，输出确定。
"""

import argparse
import json
import re
import sys
import unicodedata

PATTERN = re.compile(
    r"([\u4e00-\u9fffA-Za-z]{2,12})[^\d]{0,8}(\d+(?:\.\d+)?)"
    r"\s*(%|℃|°C|K|MPa|nm|h|min|g|mL)?"
)

# 键尾部的动词/系词，规范化时剥离
TRAILING_VERBS = ["升高到", "降至", "达到", "上升为", "提高到", "为", "是", "约", "达", "有"]


def normalize_key(k):
    k = unicodedata.normalize("NFKC", k)
    k = re.sub(r"\s+", "", k).strip("，。；：:、的了")
    changed = True
    while changed and k:
        changed = False
        for v in TRAILING_VERBS:
            if k.endswith(v) and len(k) > len(v):
                k = k[: -len(v)]
                changed = True
    return k


def iter_sources(nodes_path, material_path):
    """产出 (kind, ref, text)：节点与材料页两类出处。"""
    with open(nodes_path, "r", encoding="utf-8") as f:
        nodes = json.load(f).get("nodes", [])
    for n in nodes:
        yield ("node", n.get("id"), n.get("label") or "")
    with open(material_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            yield ("material", "%s#p%s" % (rec.get("file"), rec.get("page")),
                   rec.get("text") or "")


def extract(text):
    """从文本提取 (normalized_key, value_str, unit) 列表。"""
    out = []
    for m in PATTERN.finditer(text):
        raw_key, num, unit = m.group(1), m.group(2), m.group(3) or ""
        key = normalize_key(raw_key)
        if len(key) < 2:
            continue
        out.append((key, num, unit))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="数值冲突候选启发式扫描")
    ap.add_argument("--nodes", required=True)
    ap.add_argument("--material", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    # groups[(key, unit)] = {(value): set of (kind, ref)}
    groups = {}
    for kind, ref, text in iter_sources(args.nodes, args.material):
        for key, num, unit in extract(text):
            g = groups.setdefault((key, unit), {})
            g.setdefault(num, set()).add((kind, ref))

    candidates = []
    for (key, unit), valmap in groups.items():
        distinct = sorted(valmap.keys(), key=lambda s: float(s))
        if len(distinct) < 2:
            continue
        # 出处须不同（不同节点或不同材料页）
        refs = set()
        for v in distinct:
            refs |= valmap[v]
        if len(refs) < 2:
            continue
        values = []
        for v in distinct:
            for kind, ref in sorted(valmap[v]):
                values.append({"value": v,
                               "where": {"kind": kind, "ref": ref}})
        candidates.append({
            "key": key,
            "unit": unit,
            "values": values,
            "suggestion": "conflicts_with|uncertainty",
        })

    candidates.sort(key=lambda c: (c["key"], c["unit"]))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"candidates": candidates}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
