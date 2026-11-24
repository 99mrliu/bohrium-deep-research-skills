#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_check.py — 章节正文数值溯源校验（evidence-atlas）

输入：章节 Markdown 文件 + atlas_scan 生成的 atlas.json。
做法：抽取正文中的数值 token（含版本号 x.y.z、百分比、小数、科学计数法），
逐一在台账的 value 与 evidence 中定位：
  - BOUND     ：能在台账中定位（报告命中的台账 ID）；
  - UNSOURCED ：无法定位（给出"删除或标注[待确认]"建议）。
报告含行号、覆盖率；存在 UNSOURCED 时退出码为 1。

排除以下误报来源：
  - 台账 ID 引用本身，如 [[P003]]；
  - file:line 形式的来源定位，如 config.yaml:5、train.log:12、8:1:1 式比例；
  - URL 中的数字；
  - Markdown 标题行首的章节编号（## 3. 实验设置）。

仅使用 Python 标准库；无网络；确定性输出。

用法：
  python3 ledger_check.py chapter.md atlas.json [--out 报告目录]
"""

import argparse
import json
import os
import re
import sys

TOOL_NAME = "ledger_check"
TOOL_VERSION = "1.0.0"

# 数值 token：整数、小数、版本号式 x.y.z、科学计数法、可选百分号。
# 左边界排除 [\w.\-]，避免把 ResNet-18、word2vec、v1.2.3 的尾段拆成独立数字。
TOKEN_RE = re.compile(r'(?<![\w.\-/])\d+(?:\.\d+)*(?:[eE][-+]?\d+)?%?')

EXCLUDE_RES = [
    re.compile(r'\[\[[A-Za-z]{0,8}\d{1,6}\]\]'),          # 台账 ID 引用 [[P003]]
    re.compile(r'[\w.\-/]+(?::\d+)+(?:\s*行?)?'),          # file:line 与 8:1:1 式比例
    re.compile(r'https?://\S+'),                           # URL
    re.compile(r'^\s{0,3}#{1,6}\s+\d+(?:\.\d+)*[.、)．:]?\s*'),  # 标题章节编号
    re.compile(r'\b[Pp]\d{3,}\b'),                         # 裸台账 ID（不带方括号）
]


def masked_line(line):
    """把排除区域替换为空格，保留列位置。"""
    chars = list(line)
    for rx in EXCLUDE_RES:
        for m in rx.finditer(line):
            for i in range(m.start(), m.end()):
                chars[i] = " "
    return "".join(chars)


def norm_num(s):
    """数值归一化：去掉千分位与百分号；可转 float 则返回 float，否则 None。"""
    s = s.rstrip("%").replace(",", "").rstrip(".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def build_index(atlas):
    """从台账构建检索索引：精确串、浮点值、evidence 检索行。"""
    exact = {}    # 字符串 -> [id]
    floats = []   # (float, id)
    evid = []     # (id, evidence, 该参数的 float 值或 None)
    for p in atlas.get("parameters", []):
        pid = p.get("id", "?")
        val = str(p.get("value", "")).strip()
        fv = None
        if val:
            exact.setdefault(val, []).append(pid)
            fv = norm_num(val)
            if fv is not None:
                floats.append((fv, pid))
        ev = str(p.get("evidence", ""))
        if ev:
            evid.append((pid, ev, fv))
    return exact, floats, evid


def locate(token, exact, floats, evid):
    """返回命中的台账 ID 列表（可能为空）。"""
    hits = []
    core = token.rstrip("%")
    if core in exact:
        hits.extend(exact[core])
    if token in exact:  # 带百分号的原样匹配
        hits.extend(exact[token])
    tv = norm_num(token)
    if tv is not None:
        for fv, pid in floats:
            if tv == fv:
                hits.append(pid)
        if token.endswith("%"):
            for fv, pid in floats:
                if tv / 100.0 == fv:  # 80% 对 0.8
                    hits.append(pid)
    # evidence 词边界匹配（避免 "1" 命中 "0.0001" 这类子串误配）：
    # 仅当该参数自身数值与 token 一致时才算命中，
    # 防止"该行提到了别的数字"造成的噪声命中。
    if core and tv is not None:
        rx = re.compile(r'(?<![\w.])%s(?![\w])' % re.escape(core))
        for pid, ev, fv in evid:
            if fv is None:
                continue
            same = (tv == fv) or (token.endswith("%") and tv / 100.0 == fv)
            if same and rx.search(ev):
                hits.append(pid)
    # 去重保序
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def check(chapter_path, atlas):
    with open(chapter_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    exact, floats, evid = build_index(atlas)
    bound, unsourced = [], []
    for ln, line in enumerate(lines, 1):
        masked = masked_line(line)
        for m in TOKEN_RE.finditer(masked):
            token = m.group(0)
            hits = locate(token, exact, floats, evid)
            rec = {"line": ln, "token": token, "hits": hits,
                   "context": line.strip()[:160]}
            if hits:
                bound.append(rec)
            else:
                unsourced.append(rec)
    total = len(bound) + len(unsourced)
    return {
        "meta": {
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "chapter": os.path.abspath(chapter_path),
            "token_total": total,
            "bound_count": len(bound),
            "unsourced_count": len(unsourced),
            "coverage": (len(bound) / total) if total else 1.0,
        },
        "bound": bound,
        "unsourced": unsourced,
    }


def render_md(report):
    meta = report["meta"]
    out = []
    out.append("# 数值溯源校验报告（ledger_report.md）")
    out.append("")
    out.append("- 章节文件：`%s`" % meta["chapter"])
    out.append("- 数值 token 总数：%d；BOUND：%d；UNSOURCED：%d；覆盖率：%.1f%%" % (
        meta["token_total"], meta["bound_count"], meta["unsourced_count"],
        meta["coverage"] * 100.0))
    out.append("")
    out.append("## UNSOURCED（无法在台账定位；建议删除或标注 [待确认]）")
    out.append("")
    if not report["unsourced"]:
        out.append("（无）")
    for r in report["unsourced"]:
        out.append("- 行 %d：`%s` — %s" % (r["line"], r["token"], r["context"]))
        out.append("  - 处置建议：删除该数值，或在正文标注 `[待确认]` 并列入人工确认项。")
    out.append("")
    out.append("## BOUND（已在台账定位）")
    out.append("")
    if not report["bound"]:
        out.append("（无）")
    for r in report["bound"]:
        out.append("- 行 %d：`%s` ← %s" % (
            r["line"], r["token"], "、".join(r["hits"])))
    out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="章节正文数值溯源校验（evidence-atlas）")
    ap.add_argument("chapter", help="章节 Markdown 文件")
    ap.add_argument("atlas", help="atlas_scan 生成的 atlas.json")
    ap.add_argument("--out", default=None,
                    help="可选：报告输出目录（写 ledger_report.md/json）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.chapter):
        print("错误：章节文件不存在：%s" % args.chapter, file=sys.stderr)
        return 2
    if not os.path.isfile(args.atlas):
        print("错误：台账文件不存在：%s" % args.atlas, file=sys.stderr)
        return 2
    try:
        with open(args.atlas, "r", encoding="utf-8") as f:
            atlas = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("错误：台账读取/解析失败：%s" % e, file=sys.stderr)
        return 2

    report = check(args.chapter, atlas)
    meta = report["meta"]

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "ledger_report.json"), "w",
                  encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        with open(os.path.join(args.out, "ledger_report.md"), "w",
                  encoding="utf-8") as f:
            f.write(render_md(report))

    print("ledger_check：token %d，BOUND %d，UNSOURCED %d，覆盖率 %.1f%%" % (
        meta["token_total"], meta["bound_count"], meta["unsourced_count"],
        meta["coverage"] * 100.0))
    for r in report["unsourced"]:
        print("  UNSOURCED 行 %d：`%s` — 建议删除或标注[待确认]" % (
            r["line"], r["token"]))
    return 1 if report["unsourced"] else 0


if __name__ == "__main__":
    sys.exit(main())
