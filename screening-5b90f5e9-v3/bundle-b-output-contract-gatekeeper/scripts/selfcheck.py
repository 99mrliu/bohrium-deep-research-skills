#!/usr/bin/env python3
"""selfcheck.py — Skill bundle 平台约束自查。

检查：文件数 ≤50、单文件 ≤500KB、总计 ≤2MB、全部 UTF-8 文本、无符号链接、
SKILL.md frontmatter 合法（--- 包裹、含 name 与 description）。

退出码：0=通过；2=用法/内部错误；3=存在违规。
幂等：只读。

仅使用 Python 标准库。
"""
import argparse
import os
import sys

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024


def parse_frontmatter(text):
    """极简 YAML frontmatter 解析：只支持顶层 key: value（本 bundle 自用足够）。"""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    meta = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="bundle 平台约束自查")
    ap.add_argument("--root", default=None, help="bundle 根目录（默认脚本上一级）")
    args = ap.parse_args(argv)

    try:
        root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        violations = []
        n_files, total_bytes = 0, 0
        utf8_checked = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, root)
                if os.path.islink(path):
                    violations.append(f"符号链接: {rel}")
                    continue
                n_files += 1
                size = os.path.getsize(path)
                total_bytes += size
                if size > MAX_FILE_BYTES:
                    violations.append(f"单文件超限: {rel} ({size}B > {MAX_FILE_BYTES}B)")
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        f.read()
                    utf8_checked += 1
                except (UnicodeDecodeError, ValueError):
                    violations.append(f"非 UTF-8 文本: {rel}")

        if n_files > MAX_FILES:
            violations.append(f"文件数超限: {n_files} > {MAX_FILES}")
        if total_bytes > MAX_TOTAL_BYTES:
            violations.append(f"总大小超限: {total_bytes}B > {MAX_TOTAL_BYTES}B")

        skill_md = os.path.join(root, "SKILL.md")
        if not os.path.isfile(skill_md):
            violations.append("缺 SKILL.md")
        else:
            with open(skill_md, "r", encoding="utf-8") as f:
                meta = parse_frontmatter(f.read())
            if meta is None:
                violations.append("SKILL.md frontmatter 缺失或未被 --- 正确包裹")
            else:
                if not meta.get("name"):
                    violations.append("frontmatter 缺 name")
                if not meta.get("description"):
                    violations.append("frontmatter 缺 description")

        print(f"root={root}")
        print(f"files={n_files}/{MAX_FILES} total_bytes={total_bytes}/{MAX_TOTAL_BYTES} "
              f"utf8_checked={utf8_checked}")
        for v in violations:
            print(f"VIOLATION: {v}", file=sys.stderr)
        print("selfcheck verdict=" + ("PASS" if not violations else "FAIL"))
        return 0 if not violations else 3
    except SystemExit:
        raise
    except Exception as e:
        print(f"FATAL: selfcheck 内部错误: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
