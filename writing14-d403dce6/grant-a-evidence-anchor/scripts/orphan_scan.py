#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orphan_scan.py — 章节稿"无出处数字"与待确认占位符扫描。

扫描章节稿 markdown，抽取所有阿拉伯数字（含小数与百分数）：
  - 凡未出现在 evidence_map 任一 quote（NFKC 归一化+空白折叠后）中的数字，
    且不在白名单内，列为"无出处数字"（orphan）。
  - 统计【待确认】与【待申请人确认：…】占位符数量（占位符本身不算错误，
    但必须如实计数并写入报告，便于交付前核对缺口清单）。

数字抽取规则（确定性）：正则 (?<![A-Za-z0-9_.])\\d+(?:\\.\\d+)?%?(?![A-Za-z0-9_])，
即忽略紧挨英文字母/数字/下划线的片段（G1、C1、E3 等要素/证据编号不视为数字）。
百分数按整体抽取；判定时带 % 与去 % 两种形式均与 quote 数字集合比对。

白名单：内置白名单为单个数字 0-9（章节号、要素编号常用，见
references/reviewer_checklist.md）；--whitelist 指定 JSON 字符串数组与之合并
（例如案例年份 2021/2023、年份范围词中的数字）；--no-builtin-whitelist 可关闭内置。

退出码：0 无无出处数字；1 存在无出处数字；2 参数/输入错误。
输出确定性：按文件名字典序、行号升序，JSON 排序键、无时间戳，二次运行字节一致。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?%?(?![A-Za-z0-9_])")
PLACEHOLDER_RES = {
    "【待确认】": re.compile(r"【待确认】"),
    "【待申请人确认：…】": re.compile(r"【待申请人确认[^】]*】"),
}
BUILTIN_WHITELIST = {str(i) for i in range(10)}


def normalize(s):
    return " ".join(unicodedata.normalize("NFKC", s).split())


def numbers_in(text):
    """返回 (token 集合, 去%核心集合)。"""
    tokens, cores = set(), set()
    for m in NUM_RE.finditer(text):
        tok = m.group(0)
        tokens.add(tok)
        cores.add(tok.rstrip("%"))
    return tokens, cores


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="扫描章节稿中的无出处数字与待确认占位符。",
        epilog="退出码：0 无无出处数字；1 存在无出处数字；2 参数/输入错误。",
    )
    ap.add_argument("--proposal", nargs="+", required=True, help="章节稿 markdown 文件（可多个）")
    ap.add_argument("--evidence", required=True, help="evidence_map.json 路径")
    ap.add_argument("--whitelist", default=None, help="白名单 JSON 数组（与内置 0-9 合并）")
    ap.add_argument("--no-builtin-whitelist", action="store_true", help="关闭内置单位数白名单")
    ap.add_argument("--out", default="orphan_report.json", help="报告输出路径")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.evidence):
        print("错误：evidence_map 不存在：%s" % args.evidence, file=sys.stderr)
        return 2
    try:
        with open(args.evidence, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print("错误：evidence_map 解析失败：%s" % exc, file=sys.stderr)
        return 2
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        print("错误：evidence_map 应为条目数组或含 entries 数组的对象", file=sys.stderr)
        return 2

    approved_tokens, approved_cores = set(), set()
    for entry in entries:
        q = entry.get("quote")
        if isinstance(q, str) and q:
            t, c = numbers_in(normalize(q))
            approved_tokens |= t
            approved_cores |= c

    whitelist = set() if args.no_builtin_whitelist else set(BUILTIN_WHITELIST)
    if args.whitelist:
        if not os.path.isfile(args.whitelist):
            print("错误：白名单文件不存在：%s" % args.whitelist, file=sys.stderr)
            return 2
        try:
            with open(args.whitelist, "r", encoding="utf-8") as f:
                user_wl = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print("错误：白名单解析失败：%s" % exc, file=sys.stderr)
            return 2
        if not isinstance(user_wl, list) or not all(isinstance(x, str) for x in user_wl):
            print("错误：白名单应为 JSON 字符串数组", file=sys.stderr)
            return 2
        whitelist |= set(user_wl)

    proposals = sorted(args.proposal)
    for p in proposals:
        if not os.path.isfile(p):
            print("错误：章节稿不存在：%s" % p, file=sys.stderr)
            return 2

    orphans = []
    placeholder_counts = {k: 0 for k in PLACEHOLDER_RES}
    for path in proposals:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        for lineno, line in enumerate(lines, 1):
            norm_line = normalize(line)
            for key, rx in PLACEHOLDER_RES.items():
                placeholder_counts[key] += len(rx.findall(norm_line))
            for m in NUM_RE.finditer(norm_line):
                tok = m.group(0)
                core = tok.rstrip("%")
                if tok in approved_tokens or core in approved_cores:
                    continue
                if tok in whitelist or core in whitelist:
                    continue
                orphans.append({
                    "file": path,
                    "line": lineno,
                    "token": tok,
                    "context": norm_line.strip()[:100],
                })

    report = {
        "files_scanned": proposals,
        "whitelist_used": sorted(whitelist),
        "approved_number_count": len(approved_tokens | approved_cores),
        "orphan_numbers": orphans,
        "placeholder_counts": placeholder_counts,
    }
    try:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as exc:
        print("错误：写入报告失败：%s" % exc, file=sys.stderr)
        return 2

    print("无出处数字扫描：%d 处；占位符 %s -> %s" % (len(orphans), placeholder_counts, args.out))
    for o in orphans:
        print("  [ORPHAN] %s:%d 数字 %r 无出处 | %s" % (o["file"], o["line"], o["token"], o["context"]))
    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main())
