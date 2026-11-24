#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_manifest.py — 生成可复算清单：给定输入/输出路径，记录每个文件的 SHA-256 与字节数。

用法:
    python3 make_manifest.py <path...> [-o OUT_DIR] [--commands CMD_FILE]

- <path> 可以是目录（递归遍历）或单个文件；manifest.json / manifest.md 自身始终被跳过；
- --commands 指定一个文本文件，每行是本次流程实际执行过的命令行，原样写入清单，
  使第三方可以按命令重跑并按哈希核验字节一致性。

产出: OUT_DIR/manifest.json 与 OUT_DIR/manifest.md（默认当前目录）。
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

SKIP_NAMES = {"manifest.json", "manifest.md"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(paths):
    seen, out = set(), []
    for p in paths:
        ap = os.path.abspath(p)
        if not os.path.exists(ap):
            print("错误：路径不存在: %s" % p, file=sys.stderr)
            sys.exit(2)
        if os.path.isfile(ap):
            cand = [ap]
        else:
            cand = []
            for root, dirs, files in os.walk(ap):
                dirs.sort()
                for fn in sorted(files):
                    cand.append(os.path.join(root, fn))
        for fp in cand:
            if os.path.basename(fp) in SKIP_NAMES or os.path.islink(fp):
                continue
            rp = os.path.realpath(fp)
            if rp in seen:
                continue
            seen.add(rp)
            out.append(fp)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 SHA-256 可复算清单（manifest.json/.md）")
    ap.add_argument("paths", nargs="+", help="输入/输出的文件或目录")
    ap.add_argument("-o", "--out", default=".", help="清单输出目录（默认当前目录）")
    ap.add_argument("--commands", default=None,
                    help="记录实际执行命令行的文本文件（每行一条）")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    files = collect(args.paths)
    if not files:
        print("错误：未收集到任何文件", file=sys.stderr)
        return 2

    entries = []
    for fp in files:
        st = os.stat(fp)
        entries.append({"path": fp, "bytes": st.st_size, "sha256": sha256_file(fp)})

    commands = []
    if args.commands:
        if not os.path.isfile(args.commands):
            print("错误：--commands 文件不存在: %s" % args.commands, file=sys.stderr)
            return 2
        with open(args.commands, "r", encoding="utf-8") as f:
            commands = [ln.rstrip("\n") for ln in f if ln.strip()]

    now = datetime.datetime.now().isoformat(timespec="seconds")
    manifest = {"tool": "make_manifest.py", "generated_at": now,
                "commands": commands, "files": entries}
    mjson = os.path.join(args.out, "manifest.json")
    with open(mjson, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    lines = ["# 可复算清单（manifest）", "",
             "- 生成时间：%s" % now,
             "- 文件总数：%d" % len(entries), "",
             "| 文件 | 字节数 | SHA-256 |", "| --- | --- | --- |"]
    for e in entries:
        lines.append("| `%s` | %d | `%s` |" % (e["path"], e["bytes"], e["sha256"]))
    if commands:
        lines += ["", "## 复算命令", "",
                  "以下为本流程实际执行的命令行（按序重跑后可用上表哈希核验字节一致性）：", ""]
        lines += ["%d. `%s`" % (i, c) for i, c in enumerate(commands, 1)]
    mmd = os.path.join(args.out, "manifest.md")
    with open(mmd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("已写出: %s（%d 个文件）" % (mjson, len(entries)))
    print("已写出: %s" % mmd)
    for e in entries:
        print("  %s  %d B  %s" % (e["sha256"][:16], e["bytes"], e["path"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
