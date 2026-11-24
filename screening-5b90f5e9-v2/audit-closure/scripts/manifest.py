#!/usr/bin/env python3
"""manifest.py -- 产物目录的内容寻址清单（sha256）与复核。

子命令：
  create  对目录下全部文件（相对路径序）计算 sha256 与字节数，
          写 manifest.json（清单自身不参与哈希）。
  verify  重算并比对：added / removed / changed 三类差异；
          全同 exit 0，有差异 exit 3，清单缺失 exit 2。

用途：交付前固化产物指纹；复核者重跑 verify 即可确认产物未被事后改动；
两次独立运行的 manifest 对比是"复跑确定性"的直接证据。
"""
import argparse
import hashlib
import json
import os
import sys

MANIFEST_NAME = "manifest.json"
SKIP = {MANIFEST_NAME, ".DS_Store"}


def hash_dir(root):
    items = {}
    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        for fn in sorted(files):
            if fn in SKIP:
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            items[rel] = {"sha256": h.hexdigest(),
                          "bytes": os.path.getsize(path)}
    return items


def main():
    ap = argparse.ArgumentParser(description="产物清单与复核")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--manifest", default="",
                    help="清单路径，默认 <dir>/manifest.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create")
    sub.add_parser("verify")
    args = ap.parse_args()

    root = args.dir
    if not os.path.isdir(root):
        print("MANIFEST-ERROR: 目录不存在：%s" % root, file=sys.stderr)
        sys.exit(2)
    mpath = args.manifest or os.path.join(root, MANIFEST_NAME)

    if args.cmd == "create":
        items = hash_dir(root)
        payload = {"root": os.path.abspath(root), "files": items,
                   "file_count": len(items),
                   "note": "清单自身与 .DS_Store 不参与哈希。"}
        with open(mpath, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print("MANIFEST created: %d files -> %s" % (len(items), mpath))
        sys.exit(0)

    # verify
    if not os.path.isfile(mpath):
        print("MANIFEST-ERROR: 清单缺失：%s" % mpath, file=sys.stderr)
        sys.exit(2)
    old = json.load(open(mpath, encoding="utf-8"))["files"]
    new = hash_dir(root)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(old) & set(new)
                     if old[k]["sha256"] != new[k]["sha256"])
    ok = not (added or removed or changed)
    report = {"status": "PASS" if ok else "FAIL",
              "added": added, "removed": removed, "changed": changed}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
