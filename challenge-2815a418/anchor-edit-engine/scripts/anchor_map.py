#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anchor_map.py — 将基线稿件编译为锚点图 anchors.json。

每段一个锚点：
  anchor_id        A001、A002 ……（按文档顺序）
  heading          章节路径（如 "标题 > 2 数据与方法"，文首段落为 "(文首)"）
  paragraph_index  当前章节路径内的段序（从 1 开始）
  quote            该段逐字原文（段内换行以 \\n 连接）
  char_offset      段落首字符在原文中的偏移

用法：
  python3 anchor_map.py 基线.md --out anchors.json [--stats]
  python3 anchor_map.py 基线.md --find "逐字片段"     # 反查锚点号
  python3 anchor_map.py 基线.md --stats               # 段落统计

仅使用 Python 3 标准库。
"""
import argparse
import json
import re
import sys

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def compile_anchors(text):
    """把 Markdown 文本编译为锚点列表。段落 = 空行分隔的连续非空行块；
    标题行自身不可锚定，只用于维护章节路径。"""
    lines = text.split("\n")
    offsets = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1

    anchors = []
    stack = []          # [(level, title), ...]
    para_counter = {}   # heading_path -> 已计数段落数
    buf = []            # 当前段落的行号

    def flush():
        if not buf:
            return
        start, end = buf[0], buf[-1]
        ptext = "\n".join(lines[start:end + 1])
        path = " > ".join(t for _, t in stack) or "(文首)"
        para_counter[path] = para_counter.get(path, 0) + 1
        anchors.append({
            "anchor_id": "A%03d" % (len(anchors) + 1),
            "heading": path,
            "paragraph_index": para_counter[path],
            "quote": ptext,
            "char_offset": offsets[start],
        })
        buf.clear()

    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            stack[:] = [(l, t) for l, t in stack if l < level]
            stack.append((level, title))
        elif ln.strip() == "":
            flush()
        else:
            buf.append(i)
    flush()
    return anchors


def print_stats(anchors):
    paths = {}
    for a in anchors:
        paths.setdefault(a["heading"], 0)
        paths[a["heading"]] += 1
    print("段落总数: %d" % len(anchors))
    for p in paths:
        print("  %-50s %d 段" % (p, paths[p]))
    total_chars = sum(len(a["quote"]) for a in anchors)
    print("锚点 quote 总字符: %d" % total_chars)


def main():
    ap = argparse.ArgumentParser(description="基线 -> 锚点图 anchors.json")
    ap.add_argument("baseline", help="基线稿件路径（Markdown）")
    ap.add_argument("--out", help="anchors.json 输出路径")
    ap.add_argument("--find", help="按逐字片段反查锚点号")
    ap.add_argument("--stats", action="store_true", help="输出段落统计")
    args = ap.parse_args()

    with open(args.baseline, "r", encoding="utf-8") as f:
        text = f.read()

    anchors = compile_anchors(text)

    if args.find is not None:
        frag = args.find
        if not frag:
            print("错误：--find 片段为空", file=sys.stderr)
            return 2
        hits = [a for a in anchors if frag in a["quote"]]
        result = {
            "fragment": frag,
            "global_occurrences": text.count(frag),
            "anchor_hits": [
                {"anchor_id": a["anchor_id"], "heading": a["heading"],
                 "paragraph_index": a["paragraph_index"], "quote": a["quote"]}
                for a in hits
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["global_occurrences"] != 1:
            print("警告：片段在全文中出现 %d 次（落稿要求恰好 1 次）"
                  % result["global_occurrences"], file=sys.stderr)
        if not hits:
            print("警告：片段未落在任何段落锚点内", file=sys.stderr)
        return 0

    if args.stats:
        print_stats(anchors)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(anchors, f, ensure_ascii=False, indent=2)
        print("已写出 %s（%d 个锚点）" % (args.out, len(anchors)))
    elif not args.stats:
        # 无 --out/--stats/--find 时打印全部锚点便于查看
        print(json.dumps(anchors, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
