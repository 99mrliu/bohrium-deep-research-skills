#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scope_note.py — 由要素级对应表渲染中文比对说明（markdown），并提供措辞闸门。

两种用法：
  渲染：python3 scope_note.py --table correspondence.json [--case-id ID] [--output note.md]
  闸门：python3 scope_note.py --gate note.md
        扫描任意 markdown 说明，发现违禁结论性措辞时按行号报告并以退出码 1 结束；
        未发现时退出码 0。违禁短语清单与 references/wording_gate.md 保持一致。

诚实性约束：
  渲染出的说明只报告文本层面的差异；固定页脚声明：不假定两版本权利要求
  保护范围是否一致，一切法律等价性判断（包括但不限于 doctrine of
  equivalents）均超出说明范围。页脚文本刻意避开全部违禁短语，因此本工具
  生成的说明应当能够通过 --gate 检查。

退出码：0 = 正常（渲染成功 / 闸门未检出）；1 = 闸门检出违禁措辞；2 = 用法/输入错误。
"""
from __future__ import annotations

import argparse
import json
import sys

TOOL = "scope_note.py"
VERSION = "1.0.0"

# 违禁结论性措辞（与 references/wording_gate.md 保持一致；修改时必须同步）。
FORBIDDEN_PHRASES = [
    "保护范围相同",
    "保护范围一致",
    "保护范围等同",
    "范围完全相同",
    "未实质改变",
    "未发生实质改变",
    "实质性变化不存在",
    "实质相同",
    "实质上相同",
    "等同",
    "等效替换成立",
    "构成侵权",
    "不构成侵权",
    "侵权成立",
    "侵权不成立",
    "法律效力相同",
]

# 固定诚实性页脚（不得删改；措辞刻意避开全部违禁短语）。
HONESTY_FOOTER = (
    "> **诚实性声明（固定文本，不得删改）**：本说明仅逐字报告两版本权利要求"
    "文本层面的差异；文本差异的存在或不存在均不构成任何法律结论。本说明"
    "不对两版本权利要求保护范围是否一致作出任何假定或断言；一切法律等价性"
    "判断（包括但不限于 doctrine of equivalents）均超出本说明范围。如需"
    "法律意见，请咨询具备资质的专利代理师或律师。"
)

CLS_LABEL = {
    "unchanged": "未变更",
    "modified": "已修改",
    "added": "新增",
    "removed": "删除",
    "reordered": "顺序调整",
}


def gate_scan(text: str):
    """逐行扫描违禁短语；返回 [(行号, 短语, 行文本)]。"""
    hits = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for ph in FORBIDDEN_PHRASES:
            if ph in line:
                hits.append((lineno, ph, line.rstrip()))
    return hits


def _quote_block(quote: str) -> str:
    return "\n".join("> " + ln for ln in quote.split("\n"))


def _side_md(label: str, side) -> str:
    if side is None:
        return "  - %s：（无对应文本）" % label
    return "  - %s（%s #%s，span %s–%s）：\n%s" % (
        label,
        side["kind"],
        side["index"],
        side["span"][0],
        side["span"][1],
        _quote_block(side["quote"]),
    )


def render(table: dict, case_id=None) -> str:
    L = []
    title = "# 权利要求版本文本比对说明"
    if case_id:
        title += "（案件标识：%s）" % case_id
    L.append(title)
    L.append("")
    L.append("本说明由 %s v%s 依据要素级对应表自动渲染，仅报告文本层面的差异。" % (TOOL, VERSION))
    L.append("")

    L.append("## 状态与限制")
    L.append("")
    L.append("- status：`%s`；mode：`%s`" % (table.get("status"), table.get("mode")))
    limits = table.get("limits") or []
    if limits:
        for lim in limits:
            L.append("- 限制：%s" % lim)
    else:
        L.append("- 限制：无已声明限制。")
    a = table.get("a") or {}
    b = table.get("b") or {}
    L.append("- 版本 A：%s（sha256：%s）" % (a.get("source_path"), a.get("text_sha256")))
    if b:
        L.append("- 版本 B：%s（sha256：%s）" % (b.get("source_path"), b.get("text_sha256")))
    else:
        L.append("- 版本 B：缺失（单侧清单）。")
    L.append("")

    st = table.get("statistics") or {}
    ep = st.get("element_pairs") or {}
    L.append("## 统计（由对齐脚本按对应表重新计算）")
    L.append("")
    L.append("- 权利要求数：版本 A %s 项，版本 B %s 项；成功配对 %s 对。"
             % (st.get("claims_a"), st.get("claims_b"), st.get("claim_pairs")))
    L.append("- 整项新增 %s 项，整项删除 %s 项。"
             % (st.get("claims_added", 0), st.get("claims_removed", 0)))
    L.append("- 要素对：未变更 %s，已修改 %s，新增 %s，删除 %s，顺序调整 %s。" % (
        ep.get("unchanged", 0), ep.get("modified", 0), ep.get("added", 0),
        ep.get("removed", 0), ep.get("reordered", 0)))
    L.append("")

    if table.get("mode") == "one_sided_inventory":
        L.append("## 单侧清单（未执行比对）")
        L.append("")
        for c in table.get("one_sided_claims", []):
            L.append("### 权利要求 %s（%s）" % (c["number"], c["type"]))
            L.append("")
            L.append("span %s–%s：" % (c["span"][0], c["span"][1]))
            L.append("")
            L.append(_quote_block(c["quote"]))
            L.append("")
    else:
        L.append("## 逐项比对")
        L.append("")
        for cp in table.get("claim_pairs", []):
            L.append("### 权利要求：版本 A 第 %s 项 ↔ 版本 B 第 %s 项" % (cp["number_a"], cp["number_b"]))
            L.append("")
            for k, epair in enumerate(cp.get("element_pairs", []), 1):
                cls = epair["classification"]
                sim_v = epair.get("similarity")
                sim_s = "—" if sim_v is None else "%.4f" % sim_v
                extra = "；次序发生变化" if epair.get("reordered") else ""
                L.append("%d. 文本分类：**%s**（相似度 %s%s）" % (k, CLS_LABEL.get(cls, cls), sim_s, extra))
                L.append(_side_md("版本 A", epair.get("a")))
                L.append(_side_md("版本 B", epair.get("b")))
                L.append("")
            cands = cp.get("candidates") or []
            if cands:
                L.append("低于阈值的最佳候选（仅列出，未强制配对）：")
                L.append("")
                for c in cands:
                    L.append("- 相似度 %.4f：" % c["similarity"])
                    L.append(_side_md("版本 A", c.get("a")))
                    L.append(_side_md("版本 B", c.get("b")))
                L.append("")
        for cr in table.get("claims_removed", []):
            L.append("### 整项删除：版本 A 第 %s 项（版本 B 无对应编号）" % cr["number"])
            L.append("")
            L.append(_quote_block(cr["quote"]))
            L.append("")
        for ca in table.get("claims_added", []):
            L.append("### 整项新增：版本 B 第 %s 项（版本 A 无对应编号）" % ca["number"])
            L.append("")
            L.append(_quote_block(ca["quote"]))
            L.append("")

    L.append("---")
    L.append("")
    L.append(HONESTY_FOOTER)
    L.append("")
    return "\n".join(L)


def _load_table(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ValueError("无法读取文件 %s：%s" % (path, exc))
    except json.JSONDecodeError as exc:
        raise ValueError("文件 %s 不是合法 JSON：%s" % (path, exc))
    if not isinstance(data, dict) or "claim_pairs" not in data:
        raise ValueError("文件 %s 不是 claim_align.py 生成的对应表 JSON（缺少 claim_pairs 键）。" % path)
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="渲染中文比对说明，或对任意 markdown 说明执行措辞闸门。")
    ap.add_argument("--table", default=None, help="claim_align.py 生成的对应表 JSON。")
    ap.add_argument("--case-id", default=None, help="写入说明标题的案件标识。")
    ap.add_argument("--output", default=None, help="渲染输出路径；缺省写到标准输出。")
    ap.add_argument("--gate", default=None, help="闸门模式：扫描该 markdown 文件中的违禁结论性措辞。")
    args = ap.parse_args(argv)

    if args.gate:
        if args.table:
            print("用法错误：--gate 与 --table 互斥。", file=sys.stderr)
            return 2
        try:
            with open(args.gate, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            print("用法/输入错误：无法读取文件 %s：%s" % (args.gate, exc), file=sys.stderr)
            return 2
        hits = gate_scan(text)
        if hits:
            print("措辞闸门检出违禁结论性措辞（%d 处）：" % len(hits), file=sys.stderr)
            for lineno, ph, line in hits:
                print("  第 %d 行：含违禁短语「%s」：%s" % (lineno, ph, line.strip()), file=sys.stderr)
            return 1
        print("措辞闸门通过：未检出违禁结论性措辞。")
        return 0

    if not args.table:
        print("用法错误：渲染模式必须提供 --table；闸门模式请使用 --gate。", file=sys.stderr)
        return 2
    try:
        table = _load_table(args.table)
    except ValueError as exc:
        print("用法/输入错误：%s" % exc, file=sys.stderr)
        return 2

    md = render(table, args.case_id)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(md)
        except OSError as exc:
            print("用法/输入错误：无法写入输出文件 %s：%s" % (args.output, exc), file=sys.stderr)
            return 2
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
