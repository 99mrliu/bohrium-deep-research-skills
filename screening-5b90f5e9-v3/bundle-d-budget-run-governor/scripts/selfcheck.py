#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selfcheck.py — bundle 平台约束自查

检查项（对应挑战赛平台约束）：
  1. 文件数 ≤ 50；2. 总计 ≤ 2MB；3. 单文件 ≤ 500KB；
  4. 全部 UTF-8 文本（无二进制）；5. 无符号链接；
  6. SKILL.md 存在且 frontmatter 合法（--- 包裹，含 name 与一段 description）。

退出码：0 全部通过；2 用法错误；3 存在违规项。
仅使用 Python 标准库。幂等：只读检查，不写任何文件。
"""
import argparse
import os
import sys

MAX_FILES = 50
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 500 * 1024

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_frontmatter(text):
    """极简 YAML frontmatter 校验：--- 包裹，含 name: 与非空 description:。"""
    if not text.startswith("---"):
        return None, "缺少起始 ---"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "缺少结束 ---"
    body = text[3:end].strip().splitlines()
    fm = {}
    for line in body:
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    if fm.get("name") != "budget-run-governor":
        return fm, "name 必须为 budget-run-governor"
    if not fm.get("description"):
        return fm, "description 缺失或为空"
    return fm, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="bundle 平台约束自查")
    ap.add_argument("--root", default=BUNDLE_ROOT, help="bundle 根目录（默认本脚本上两级）")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("[selfcheck] 错误：目录不存在: %s" % root, file=sys.stderr)
        return 2

    failures, files = [], []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            files.append(os.path.join(dirpath, name))

    for path in files:
        rel = os.path.relpath(path, root)
        if os.path.islink(path):
            failures.append("符号链接禁止: %s" % rel)
            continue
        size = os.path.getsize(path)
        total += size
        if size > MAX_FILE_BYTES:
            failures.append("单文件超 500KB: %s（%d 字节）" % (rel, size))
        try:
            with open(path, "r", encoding="utf-8") as f:
                f.read()
        except (UnicodeDecodeError, ValueError):
            failures.append("非 UTF-8 文本（疑似二进制）: %s" % rel)

    if len(files) > MAX_FILES:
        failures.append("文件数超限: %d > %d" % (len(files), MAX_FILES))
    if total > MAX_TOTAL_BYTES:
        failures.append("总大小超限: %d > %d 字节" % (total, MAX_TOTAL_BYTES))

    skill_md = os.path.join(root, "SKILL.md")
    if not os.path.isfile(skill_md):
        failures.append("缺少 SKILL.md")
    else:
        with open(skill_md, "r", encoding="utf-8") as f:
            fm, err = parse_frontmatter(f.read())
        if err:
            failures.append("SKILL.md frontmatter 不合法: %s" % err)

    print("[selfcheck] 根目录: %s" % root)
    print("[selfcheck] 文件数: %d / %d；总大小: %d / %d 字节"
          % (len(files), MAX_FILES, total, MAX_TOTAL_BYTES))
    if failures:
        for f_ in failures:
            print("[selfcheck] FAIL: %s" % f_)
        print("[selfcheck] 结果: FAIL（%d 项违规）" % len(failures))
        return 3
    print("[selfcheck] frontmatter: name=%r, description 长度=%d"
          % (fm.get("name"), len(fm.get("description", ""))))
    print("[selfcheck] 结果: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[selfcheck] 致命错误: %r" % e, file=sys.stderr)
        sys.exit(3)
