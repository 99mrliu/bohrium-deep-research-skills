#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cite_check.py — 引用存在性核验（仅标准库，Python >= 3.9）。

核验讨论正文中的文献锚点 [Lnn] 是否真实存在于材料提供的文献表，
并检查文献表条目是否被使用、元数据是否可疑。

输入：
  --discussion discussion.md   讨论正文
  --bib        references.txt  文献表。支持两种格式：
                 (1) 行式：每行一条，形如
                     L01 | 作者. 题名. 刊名, 年.
                 (2) BibTeX：@entry{Lnn, title={...}, year={...}, ...}
输出：
  --out        cite_report.md  核验报告

规则：
  ERROR  正文引用的 [Lnn] 在文献表中不存在（禁止编造/幻觉引用）；
  ERROR  锚点格式错误（如 [L 01]、[LO1]、[L01a]）；
  INFO   文献表条目未被正文引用（未使用）；
  WARN   年份缺失或超出 1900–2100、题名疑似缺失。

退出码：0 = 无 ERROR；1 = 存在 ERROR。
"""
import argparse
import re
import sys

CITE_RE = re.compile(r"\[L(\d{1,3})\]")
BRACKET_RE = re.compile(r"\[([^\[\]\s]{1,16})\]")
LINE_ENTRY_RE = re.compile(r"^\s*(L\d{1,3})\s*\|\s*(.+?)\s*$")
BIBTEX_ENTRY_RE = re.compile(r"@\w+\s*\{\s*(L\d{1,3})\s*,(.*?)\n\s*\}", re.S | re.M)
BIBTEX_TITLE_RE = re.compile(r"title\s*=\s*[\{\"](.+?)[\}\"]\s*,", re.S)
YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")

YEAR_MIN, YEAR_MAX = 1900, 2100


def parse_bib(text):
    """返回 {id: {"raw": 原文, "title_ok": bool, "years": [int, ...]}}。"""
    entries = {}
    for line in text.splitlines():
        m = LINE_ENTRY_RE.match(line)
        if m:
            lid, raw = m.group(1), m.group(2)
            segs = [s.strip() for s in raw.split(".") if s.strip()]
            entries[lid] = {
                "raw": raw,
                "title_ok": len(segs) >= 2,
                "years": [int(y) for y in YEAR_RE.findall(raw)],
            }
    for m in BIBTEX_ENTRY_RE.finditer(text):
        lid, body = m.group(1), m.group(2)
        if lid in entries:
            continue
        tm = BIBTEX_TITLE_RE.search(body)
        entries[lid] = {
            "raw": " ".join(body.split())[:200],
            "title_ok": bool(tm),
            "years": [int(y) for y in YEAR_RE.findall(body)],
        }
    return entries


def main(argv=None):
    p = argparse.ArgumentParser(
        description="核验讨论正文引用 [Lnn] 是否真实存在于文献表，并检查元数据可疑项。")
    p.add_argument("--discussion", required=True, help="讨论正文 markdown")
    p.add_argument("--bib", required=True, help="文献表（行式或 BibTeX）")
    p.add_argument("--out", required=True, help="输出核验报告 markdown 路径")
    args = p.parse_args(argv)

    with open(args.discussion, "r", encoding="utf-8") as f:
        discussion = f.read()
    with open(args.bib, "r", encoding="utf-8") as f:
        bib_text = f.read()

    errors, warns, infos = [], [], []

    bib = parse_bib(bib_text)
    if not bib:
        errors.append("文献表为空或无法解析：材料未提供可用参考文献，正文不得出现任何 [Lnn] 引用")

    cited = ["L%s" % d for d in CITE_RE.findall(discussion)]
    cited_set = set(cited)

    # 锚点格式错误：以 L/l 开头但不符合 [Lnn]
    for m in BRACKET_RE.finditer(discussion):
        tok = m.group(1)
        if tok[:1].upper() == "L" and not re.fullmatch(r"L\d{1,3}", tok):
            errors.append("锚点格式错误: [%s]（应为 [Lnn]，n 为数字）" % tok)

    # 引用存在性
    for lid in sorted(cited_set):
        if lid not in bib:
            errors.append("幻觉引用: 正文引用 [%s]，但文献表中不存在该条目" % lid)

    # 未使用条目
    for lid in sorted(bib):
        if lid not in cited_set:
            infos.append("文献 %s 未被正文引用（未使用）" % lid)

    # 元数据可疑项
    meta_rows = []
    for lid in sorted(bib):
        e = bib[lid]
        row_warns = []
        in_range = [y for y in e["years"] if YEAR_MIN <= y <= YEAR_MAX]
        out_range = [y for y in e["years"] if not (YEAR_MIN <= y <= YEAR_MAX)]
        if not e["years"]:
            row_warns.append("缺少年份")
        elif out_range and not in_range:
            row_warns.append("年份超出 %d–%d: %s" % (YEAR_MIN, YEAR_MAX, out_range))
        if not e["title_ok"]:
            row_warns.append("题名疑似缺失")
        for w in row_warns:
            warns.append("%s: %s" % (lid, w))
        meta_rows.append((lid, "是" if lid in cited_set else "否",
                          "; ".join(row_warns) if row_warns else "—"))

    # ---------- 报告 ----------
    md = []
    md.append("# 引用核验报告\n")
    md.append("## 正文引用存在性\n")
    md.append("| 引用锚点 | 文献表存在 |")
    md.append("|---|---|")
    if cited_set:
        for lid in sorted(cited_set):
            md.append("| [%s] | %s |" % (lid, "是" if lid in bib else "**否（ERROR）**"))
    else:
        md.append("| — | 正文无 [Lnn] 引用 |")
    md.append("")
    md.append("## 文献表条目（%d 条）\n" % len(bib))
    md.append("| 条目 | 被引用 | 元数据警告 |")
    md.append("|---|---|---|")
    for lid, used, w in meta_rows:
        md.append("| %s | %s | %s |" % (lid, used, w))
    md.append("")
    md.append("## 审计消息\n")
    if errors:
        md.append("### ERROR\n")
        md.extend("- %s" % e for e in errors)
    if warns:
        md.append("### WARN\n")
        md.extend("- %s" % w for w in warns)
    if infos:
        md.append("### INFO\n")
        md.extend("- %s" % i for i in infos)
    if not errors and not warns and not infos:
        md.append("- 无")
    md.append("")
    md.append("## 结论\n")
    md.append("**%s**（ERROR %d 条，WARN %d 条，INFO %d 条）"
              % ("FAIL" if errors else "PASS", len(errors), len(warns), len(infos)))
    md.append("")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    for e in errors:
        print("[ERR] %s" % e)
    for w in warns:
        print("[WARN] %s" % w)
    for i in infos:
        print("[INFO] %s" % i)
    print("正文引用 %d 处（去重 %d），文献表 %d 条；ERROR %d，WARN %d，INFO %d"
          % (len(cited), len(cited_set), len(bib), len(errors), len(warns), len(infos)))
    print("FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
