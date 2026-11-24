#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""snapshot_freeze.py — 输入冻结：在任何处理之前固证原始材料。

把输入文件复制到冻结目录（只读副本），并生成 manifest.json：
{files: {路径: {sha256, bytes, frozen_copy}}}。审计的检查 A 据此发现
"原始文件在处理过程中被偷改"。退出码：0 正常；2 参数错误。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", help="要冻结的原始文件")
    ap.add_argument("--out", required=True, help="冻结目录")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    man = {"files": {}}
    for p in args.files:
        if not os.path.isfile(p):
            print("ERROR: 文件不存在: %s" % p, file=sys.stderr)
            sys.exit(2)
        dst = os.path.join(args.out, os.path.basename(p))
        shutil.copy2(p, dst)
        man["files"][os.path.abspath(p)] = {
            "sha256": sha256_file(p), "bytes": os.path.getsize(p),
            "frozen_copy": os.path.abspath(dst)}
    mpath = os.path.join(args.out, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "frozen": len(man["files"]),
                      "manifest": os.path.abspath(mpath)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
