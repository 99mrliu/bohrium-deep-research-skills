#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""section_split.py — 无分节草稿的段落归类与骨架重组助手（仅标准库）。

对缺少「结果/讨论」分节标题的草稿，按段落级启发式打分：
  结果分  = 数值词数 + 3 × 统计证据词数
  讨论分  = 2 × 解释标记词数
结果分 > 讨论分 → 归入「结果」；讨论分 > 结果分 → 归入「讨论」；
相等或均为 0 → 「待人工判断」。

输出重组骨架 Markdown 与 moves.json（段落号 → 目标节 → 理由），
供 change_log 引用。归类是保守启发式，骨架须人工复核后再定稿。
"""
import argparse
import json
import re
import sys

NUMBER = re.compile(r"\d+(?:\.\d+)?")
STAT = re.compile(
    r"[pP]\s*[<=>≤≥]\s*0?\.\d+|置信区间|\bCI\b|[tFz]\s*[(=]|χ²|标准差|标准误|±")
INTERP = re.compile(
    r"表明|说明|提示|意味着|可能|由于|原因|机制|一致|反映|阐释|解释|推断|"
    r"\bsuggest|\bindicate|\bimply|\bbecause|\bmechanism|\bconsistent|"
    r"\binterpretation|\blikely|\btherefore",
    re.IGNORECASE)


def split_paragraphs(text):
    """按空行分段；返回 [(para_id, text)]，忽略纯标题行单独成段。"""
    paras, buf = [], []
    pid = 0
    for line in text.splitlines():
        if line.strip():
            buf.append(line.rstrip())
        else:
            if buf:
                pid += 1
                paras.append((pid, "\n".join(buf)))
                buf = []
    if buf:
        pid += 1
        paras.append((pid, "\n".join(buf)))
    return paras


def classify(text):
    n_num = len(NUMBER.findall(text))
    n_stat = len(STAT.findall(text))
    n_interp = len(INTERP.findall(text))
    r_score = n_num + 3 * n_stat
    d_score = 2 * n_interp
    if r_score > d_score:
        target = "结果"
    elif d_score > r_score:
        target = "讨论"
    else:
        target = "待人工判断"
    reason = ("数值词 %d 个、统计证据词 %d 个、解释标记 %d 个（结果分 %d，讨论分 %d）"
              % (n_num, n_stat, n_interp, r_score, d_score))
    return target, reason


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="无分节草稿的段落归类与骨架重组助手（启发式，输出需人工复核）。")
    ap.add_argument("--draft", required=True, help="缺少分节标题的草稿 Markdown 路径")
    ap.add_argument("--out", required=True, help="重组骨架 Markdown 输出路径")
    ap.add_argument("--moves", required=True, help="段落归类记录 moves.json 输出路径")
    args = ap.parse_args(argv)

    try:
        with open(args.draft, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("错误：无法读取草稿 %s：%s" % (args.draft, e), file=sys.stderr)
        return 2

    paras = split_paragraphs(text)
    moves = []
    buckets = {"结果": [], "讨论": [], "待人工判断": []}
    for pid, ptext in paras:
        target, reason = classify(ptext)
        buckets[target].append((pid, ptext))
        moves.append({"paragraph": "P%d" % pid, "target": target, "reason": reason})

    L = ["# 重组骨架（section_split.py 生成，须人工复核后方可定稿）", ""]
    for section in ("结果", "讨论", "待人工判断"):
        L.append("## %s" % section)
        L.append("")
        if not buckets[section]:
            L.append("（无段落归入）")
            L.append("")
        for pid, ptext in buckets[section]:
            L.append("<!-- 原段落 P%d -->" % pid)
            L.append(ptext)
            L.append("")
    skeleton = "\n".join(L)

    record = {
        "tool": "section_split",
        "source": args.draft,
        "note": "启发式段落归类，供 change_log 引用；目标节须人工复核。",
        "paragraphs": moves,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(skeleton + "\n")
        with open(args.moves, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        print("错误：无法写出结果：%s" % e, file=sys.stderr)
        return 2

    for m in moves:
        print("%s → %s（%s）" % (m["paragraph"], m["target"], m["reason"]))
    print("骨架已写入 %s；归类记录已写入 %s" % (args.out, args.moves))
    return 0


if __name__ == "__main__":
    sys.exit(main())
