#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version_diff.py — 比较两版章节稿，产出确定性 change_record.md。

输出内容：
  1. 变更统计表（新增/删除/修改行数；replace 块内 min(删,增) 计为修改）；
  2. 按小节归组的变更表（以 # 标题定位小节）；
  3. 人工确认项清单（从【待…确认…】占位符提取，标注所在文件与行号）；
  4. unified diff（difflib，固定上下文 2 行）。

确定性：同一对输入二次运行字节一致（不写时间戳、不写绝对路径）。

用法：
  python3 version_diff.py 旧版.md 新版.md [-o change_record.md]
退出码：0 成功（含两版完全一致的情形）；1 文件读取失败；2 参数错误。
"""
import argparse
import difflib
import re
import sys

CONFIRM_RE = re.compile(r"【待[^】]*确认[^】]*】")
HEADING_RE = re.compile(r"^#{1,3}\s+")


def section_at(lines, idx):
    """返回 lines 中 idx 行之前最近的小节标题；无则返回占位名。"""
    for k in range(min(idx, len(lines) - 1), -1, -1):
        if HEADING_RE.match(lines[k]):
            return lines[k].strip().lstrip("#").strip()
    return "（文首/无小节）"


def collect_stats(old_lines, new_lines):
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added = deleted = modified = 0
    per_section = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        n_del, n_add = i2 - i1, j2 - j1
        mod = min(n_del, n_add) if tag == "replace" else 0
        a = n_add - mod
        d = n_del - mod
        added += a
        deleted += d
        modified += mod
        section = section_at(new_lines, j1)
        if section == "（文首/无小节）":
            section = section_at(old_lines, i1)
        agg = per_section.setdefault(section, [0, 0, 0])
        agg[0] += a
        agg[1] += d
        agg[2] += mod
    return added, deleted, modified, per_section


def collect_confirmations(old_lines, new_lines):
    items = []

    def scan(lines, label):
        for n, line in enumerate(lines, 1):
            for m in CONFIRM_RE.findall(line):
                items.append((m, label, n))

    scan(new_lines, "新版")
    old_marks = {m for line in old_lines for m in CONFIRM_RE.findall(line)}
    new_marks = {t[0] for t in items}
    for m in sorted(old_marks - new_marks):
        items.append((m, "旧版有、新版已移除（请确认是否已解决）", 0))
    return items


def build_record(old_name, new_name, old_lines, new_lines):
    added, deleted, modified, per_section = collect_stats(old_lines, new_lines)
    out = []
    out.append("# 修改记录（change_record）")
    out.append("")
    out.append("- 旧版本：`%s`" % old_name)
    out.append("- 新版本：`%s`" % new_name)
    out.append("- 生成方式：version_diff.py（difflib unified diff，固定上下文 2 行，确定性输出）")
    out.append("")
    out.append("## 一、变更统计")
    out.append("")
    out.append("| 类型 | 行数 |")
    out.append("| --- | --- |")
    out.append("| 新增行 | %d |" % added)
    out.append("| 删除行 | %d |" % deleted)
    out.append("| 修改行 | %d |" % modified)
    out.append("")
    out.append("## 二、按小节归组的变更")
    out.append("")
    if per_section:
        out.append("| 小节 | 新增 | 删除 | 修改 |")
        out.append("| --- | --- | --- | --- |")
        for section in sorted(per_section):
            a, d, m = per_section[section]
            out.append("| %s | %d | %d | %d |" % (section, a, d, m))
    else:
        out.append("两版内容完全一致，无变更。")
    out.append("")
    out.append("## 三、人工确认项清单（自【待…确认…】占位符提取）")
    out.append("")
    confirmations = collect_confirmations(old_lines, new_lines)
    if confirmations:
        for mark, label, lineno in confirmations:
            loc = "%s 第 %d 行" % (label, lineno) if lineno else label
            out.append("- [ ] %s（%s）" % (mark, loc))
    else:
        out.append("未发现【待…确认…】占位符。")
    out.append("")
    out.append("## 四、Unified Diff（上下文 2 行）")
    out.append("")
    out.append("```diff")
    diff = difflib.unified_diff(old_lines, new_lines,
                                fromfile=old_name, tofile=new_name,
                                n=2, lineterm="")
    out.extend(diff)
    out.append("```")
    out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="比较两版章节稿，产出 unified diff + 统计 + 人工确认项的 change_record.md。")
    ap.add_argument("old", help="旧版本 Markdown（如 draft_v1.md）")
    ap.add_argument("new", help="新版本 Markdown（如 draft_v2.md）")
    ap.add_argument("-o", "--output", help="输出 change_record.md 路径（缺省打印到标准输出）")
    args = ap.parse_args(argv)

    try:
        with open(args.old, "r", encoding="utf-8") as fh:
            old_lines = fh.read().splitlines()
    except OSError as exc:
        print("错误：无法读取旧版文件 %s: %s" % (args.old, exc), file=sys.stderr)
        return 1
    try:
        with open(args.new, "r", encoding="utf-8") as fh:
            new_lines = fh.read().splitlines()
    except OSError as exc:
        print("错误：无法读取新版文件 %s: %s" % (args.new, exc), file=sys.stderr)
        return 1

    record = build_record(args.old, args.new, old_lines, new_lines)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(record)
        except OSError as exc:
            print("错误：无法写出 %s: %s" % (args.output, exc), file=sys.stderr)
            return 1
        added, deleted, modified, _ = collect_stats(old_lines, new_lines)
        print("change_record 已写出: %s（新增 %d 行 / 删除 %d 行 / 修改 %d 行）"
              % (args.output, added, deleted, modified))
    else:
        sys.stdout.write(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
