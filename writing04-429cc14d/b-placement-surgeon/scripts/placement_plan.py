#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""placement_plan.py — placement-surgeon 阶段 3：修复计划校验与原子施加。

仅使用 Python 标准库；确定性；无网络访问。

输入：
    --manuscript FILE   原始稿件（UTF-8 文本）
    --plan       FILE   plan.json（格式见 references/placement_plan_format.md）
    --out        DIR    输出目录，成功时写出 edited_manuscript.txt 与
                        change_map.json；任何校验失败都不写任何输出文件（原子）

plan 操作：
    move    {"op":"move","marker":"[6]","from_sentence":"S016",
             "to_sentence":"S013"}  把 from 句中的精确 marker 串移到 to 句末
    insert  {"op":"insert","sentence":"S005","marker_text":"[1]"}
                                   在指定句末（终结标点之前）插入标记文本
    remove  {"op":"remove","marker":"[6]","sentence":"S016"}
                                   移除指定句中精确匹配的 marker 串

校验（全部通过才施加；任一失败整体不写盘，退出码 2）：
    * 锚点句 id 存在（或 anchor_text 在全文唯一匹配）；
    * marker 原文在指定句内逐字存在且唯一；
    * insert 的 marker_text 必须是合法引用标记（[n]/[n-m]/(Author, year)）；
    * 各操作的删除区间互不重叠，插入点不落在删除区间内。

退出码：0 施加成功；2 校验失败/IO 错误。
"""

import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claim_scan  # noqa: E402

TRAIL = set("。！？；.!?”’\"')）】」』》\n")
BRACKET_FULL = re.compile(r"\[\s*\d+(?:\s*[-–—,，]\s*\d+)*\s*\]")
AUTHORYEAR_FULL = re.compile(
    r"[（(][^（）()\n]{0,80}?(?:19|20)\d{2}[a-z]?[^（）()\n]{0,30}?[)）]"
)


def line_col(text, pos):
    line = text.count("\n", 0, pos) + 1
    lstart = text.rfind("\n", 0, pos) + 1
    return line, pos - lstart + 1


def insertion_offset(sent):
    """句末插入点：句尾终结标点/闭引号之前。"""
    text = sent["text"]
    k = len(text.rstrip("\n"))
    while k > 0 and text[k - 1] in TRAIL:
        k -= 1
    return sent["char_start"] + k


def resolve_sentence(ref, sentences, errors):
    """按 id 或 anchor_text 解析锚点句，要求唯一。"""
    by_id = {s["id"]: s for s in sentences}
    if "sentence" in ref:
        sid = ref["sentence"]
        if sid not in by_id:
            errors.append("锚点句不存在：%s" % sid)
            return None
        return by_id[sid]
    if "anchor_text" in ref:
        hits = [s for s in sentences if ref["anchor_text"] in s["text"]]
        if len(hits) != 1:
            errors.append("anchor_text 匹配不唯一（%d 处）：%r"
                          % (len(hits), ref["anchor_text"]))
            return None
        return hits[0]
    errors.append("操作缺少 sentence/anchor_text 锚点：%r" % ref)
    return None


def find_marker_span(sent, raw, errors, ctx):
    """在句内找 marker 精确串，要求唯一，返回全局区间。"""
    seg = sent["text"]
    idxs = [m.start() for m in re.finditer(re.escape(raw), seg)]
    if len(idxs) != 1:
        errors.append("%s：标记 %r 在句 %s 内出现 %d 次（要求恰 1 次）"
                      % (ctx, raw, sent["id"], len(idxs)))
        return None
    return (sent["char_start"] + idxs[0],
            sent["char_start"] + idxs[0] + len(raw))


def build_edits(plan, sentences):
    """把 plan 操作编译为编辑列表；返回 (edits, op_records, errors)。

    edits: [(start, end, replacement, op_index, kind)]
    """
    edits = []
    op_records = []
    errors = []

    for i, op in enumerate(plan.get("operations", [])):
        kind = op.get("op")
        ctx = "操作#%d(%s)" % (i + 1, kind)
        if kind not in ("move", "insert", "remove"):
            errors.append("%s：未知 op（仅支持 move/insert/remove）" % ctx)
            continue

        if kind == "insert":
            stext = op.get("marker_text", "")
            if not (BRACKET_FULL.fullmatch(stext) or AUTHORYEAR_FULL.fullmatch(stext)):
                errors.append("%s：marker_text 不是合法引用标记：%r" % (ctx, stext))
                continue
            sent = resolve_sentence(op, sentences, errors)
            if sent is None:
                continue
            pos = insertion_offset(sent)
            edits.append((pos, pos, stext, i, "insert"))
            op_records.append({"index": i, "op": kind, "marker": stext,
                               "to_sentence": sent["id"], "pos": pos,
                               "reason": op.get("reason", "")})

        elif kind == "remove":
            raw = op.get("marker")
            if not raw:
                errors.append("%s：缺少 marker 字段" % ctx)
                continue
            sent = resolve_sentence(op, sentences, errors)
            if sent is None:
                continue
            span = find_marker_span(sent, raw, errors, ctx)
            if span is None:
                continue
            edits.append((span[0], span[1], "", i, "remove"))
            op_records.append({"index": i, "op": kind, "marker": raw,
                               "from_sentence": sent["id"], "span": span,
                               "reason": op.get("reason", "")})

        else:  # move
            raw = op.get("marker")
            if not raw:
                errors.append("%s：缺少 marker 字段" % ctx)
                continue
            src = resolve_sentence({"sentence": op.get("from_sentence")}
                                   if op.get("from_sentence") else op,
                                   sentences, errors)
            dst = resolve_sentence({"sentence": op.get("to_sentence")},
                                   sentences, errors)
            if src is None or dst is None:
                continue
            if src["id"] == dst["id"]:
                errors.append("%s：from/to 句相同（%s）" % (ctx, src["id"]))
                continue
            span = find_marker_span(src, raw, errors, ctx)
            if span is None:
                continue
            pos = insertion_offset(dst)
            edits.append((span[0], span[1], "", i, "remove"))
            edits.append((pos, pos, raw, i, "insert"))
            op_records.append({"index": i, "op": kind, "marker": raw,
                               "from_sentence": src["id"],
                               "to_sentence": dst["id"],
                               "span": span, "pos": pos,
                               "reason": op.get("reason", "")})

    # 互不重叠校验
    removes = sorted([(s, e, i) for (s, e, _r, i, k) in edits if k == "remove"])
    for (s1, e1, i1), (s2, e2, i2) in zip(removes, removes[1:]):
        if s2 < e1:
            errors.append("操作#%d 与操作#%d 的删除区间重叠" % (i1 + 1, i2 + 1))
    for (s, e, _r, i, k) in edits:
        if k == "insert":
            for (rs, re_, ri) in removes:
                if rs < s < re_:
                    errors.append("操作#%d 的插入点落在操作#%d 的删除区间内"
                                  % (i + 1, ri + 1))
    return edits, op_records, errors


def apply_edits(full_text, edits):
    """按位置降序施加编辑，返回 (edited_text, {op_index: edited_pos})。"""
    ordered = sorted(edits, key=lambda e: (e[0], e[1]), reverse=True)
    edited = full_text
    for (s, e, rep, _i, _k) in ordered:
        edited = edited[:s] + rep + edited[e:]
    # 计算每个操作在 edited 中的最终位置；move 含删除+插入两条编辑，
    # 新位置取插入点（insert 优先于 remove）
    pos_of = {}
    for (s, e, rep, i, k) in edits:
        delta = sum(len(r2) - (e2 - s2)
                    for (s2, e2, r2, _j, _k2) in edits if s2 < s)
        if k == "insert" or i not in pos_of:
            pos_of[i] = s + delta
    return edited, pos_of


def atomic_write(path, content):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description="修复计划校验与原子施加（placement-surgeon 阶段 3）")
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    for p in (args.manuscript, args.plan):
        if not os.path.isfile(p):
            print("错误：文件不存在：%s" % p, file=sys.stderr)
            return 2
    try:
        with open(args.plan, "r", encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("错误：plan.json 解析失败：%s" % exc, file=sys.stderr)
        return 2

    sentences, _markers, full_text, _stats = claim_scan.scan_manuscript(
        args.manuscript)
    edits, op_records, errors = build_edits(plan, sentences)

    if errors:
        print(json.dumps({"status": "rejected", "errors": errors},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2  # 原子性：不写任何输出文件

    edited, pos_of = apply_edits(full_text, edits)

    diff = list(difflib.unified_diff(
        full_text.splitlines(), edited.splitlines(),
        fromfile="original", tofile="edited", lineterm=""))

    changes = []
    for rec in op_records:
        i = rec["index"]
        ep = pos_of[i]
        line, col = line_col(edited, ep)
        entry = {"op": rec["op"], "marker": rec["marker"],
                 "reason": rec.get("reason", ""),
                 "new_position": {"line": line, "col": col,
                                  "char_offset": ep}}
        if rec["op"] == "insert":
            entry["to_sentence"] = rec["to_sentence"]
        elif rec["op"] == "remove":
            old_line, old_col = line_col(full_text, rec["span"][0])
            entry["from_sentence"] = rec["from_sentence"]
            entry["old_position"] = {"line": old_line, "col": old_col,
                                     "char_offset": rec["span"][0]}
        else:
            old_line, old_col = line_col(full_text, rec["span"][0])
            entry["from_sentence"] = rec["from_sentence"]
            entry["to_sentence"] = rec["to_sentence"]
            entry["old_position"] = {"line": old_line, "col": old_col,
                                     "char_offset": rec["span"][0]}
        changes.append(entry)

    change_map = {
        "plan_note": plan.get("note", ""),
        "operations_applied": len(changes),
        "changes": changes,
        "diff": diff,
    }

    os.makedirs(args.out, exist_ok=True)
    ep = os.path.join(args.out, "edited_manuscript.txt")
    cp = os.path.join(args.out, "change_map.json")
    atomic_write(ep, edited)
    atomic_write(cp, json.dumps(change_map, ensure_ascii=False, indent=2))
    print(json.dumps({"status": "applied", "operations": len(changes),
                      "edited_manuscript": ep, "change_map": cp},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
