#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkpoint.py —— 阶段快照：中断恢复与"先存 partial 再迭代"（仅标准库）。

子命令：
  save <stage>     把 --out 目录顶层全部 .json 复制到 --work/checkpoints/<stage>/，
                   并写 manifest.json（阶段名、每文件 SHA-256 与字节数、保存时刻）
  list             列出全部快照（阶段名、保存时刻、文件清单）
  recover <stage>  先按 manifest 逐文件校验 SHA-256，全部通过后回滚到该快照

退出码：
  0  成功
  1  操作失败（无文件可存、快照不存在、SHA-256 校验不符）
  2  用法 / IO 错误（参数非法、--out 目录不存在等）

说明：manifest.json 中的 saved_at_* 字段是唯一的非确定性内容（时间戳），
仅用于人读，不参与任何门控判定；快照内的数据文件逐字节复制，无改写。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time

STAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def ckpt_root(work):
    return os.path.join(work, "checkpoints")


def valid_stage(stage):
    return bool(STAGE_RE.match(stage or ""))


def cmd_save(args):
    if not valid_stage(args.stage):
        print("[checkpoint] USAGE ERROR: 非法阶段名 {!r}（允许 [A-Za-z0-9_-]，字母数字开头）".format(
            args.stage))
        return 2
    if not os.path.isdir(args.out):
        print("[checkpoint] USAGE/IO ERROR: --out 目录不存在：{}".format(args.out))
        return 2
    files = sorted(f for f in os.listdir(args.out)
                   if f.endswith(".json") and os.path.isfile(os.path.join(args.out, f)))
    if not files:
        print("[checkpoint] FAIL: --out 顶层没有 .json 文件，无快照可存：{}".format(args.out))
        return 1
    dest = os.path.join(ckpt_root(args.work), args.stage)
    os.makedirs(dest, exist_ok=True)
    manifest = {
        "stage": args.stage,
        "saved_at_epoch": int(time.time()),
        "saved_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_out": os.path.abspath(args.out),
        "note": "saved_at_* 仅为人读时间戳，不参与门控；数据文件逐字节复制",
        "files": [],
    }
    for name in files:
        src = os.path.join(args.out, name)
        digest = sha256_of(src)
        shutil.copyfile(src, os.path.join(dest, name))
        manifest["files"].append({"name": name, "sha256": digest,
                                  "bytes": os.path.getsize(src)})
        print("[checkpoint]   + {} (sha256 {}…, {} bytes)".format(name, digest[:12],
                                                                  os.path.getsize(src)))
    dump_json(os.path.join(dest, "manifest.json"), manifest)
    print("[checkpoint] OK save stage={} files={} -> {}".format(args.stage, len(files), dest))
    return 0


def cmd_list(args):
    root = ckpt_root(args.work)
    if not os.path.isdir(root):
        print("[checkpoint] (无快照：{} 不存在)".format(root))
        return 0
    stages = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    if not stages:
        print("[checkpoint] (无快照)")
        return 0
    for stage in stages:
        mpath = os.path.join(root, stage, "manifest.json")
        try:
            with open(mpath, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
            names = [f.get("name") for f in manifest.get("files", [])]
            print("[checkpoint] {} | saved_at={} | files={} | {}".format(
                stage, manifest.get("saved_at_local", "?"), len(names), ", ".join(names)))
        except (OSError, json.JSONDecodeError):
            print("[checkpoint] {} | (manifest.json 缺失或损坏)".format(stage))
    return 0


def cmd_recover(args):
    if not valid_stage(args.stage):
        print("[checkpoint] USAGE ERROR: 非法阶段名 {!r}".format(args.stage))
        return 2
    src_dir = os.path.join(ckpt_root(args.work), args.stage)
    if not os.path.isdir(src_dir):
        print("[checkpoint] FAIL: 快照不存在：{}".format(src_dir))
        return 1
    mpath = os.path.join(src_dir, "manifest.json")
    try:
        with open(mpath, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("[checkpoint] FAIL: manifest.json 不可用：{}".format(exc))
        return 1
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        print("[checkpoint] FAIL: manifest.json 中 files 为空")
        return 1
    # 先全部校验，任何一个不符即整体中止，不做半恢复
    for entry in entries:
        name = entry.get("name")
        fpath = os.path.join(src_dir, name)
        if not os.path.isfile(fpath):
            print("[checkpoint] FAIL: 快照内文件缺失：{}".format(fpath))
            return 1
        actual = sha256_of(fpath)
        if actual != entry.get("sha256"):
            print("[checkpoint] FAIL: SHA-256 校验不符：{}（manifest {}… vs 实际 {}…）".format(
                name, str(entry.get("sha256"))[:12], actual[:12]))
            return 1
    os.makedirs(args.out, exist_ok=True)
    for entry in entries:
        name = entry["name"]
        shutil.copyfile(os.path.join(src_dir, name), os.path.join(args.out, name))
        print("[checkpoint]   <- {} (sha256 {}… 校验通过)".format(name, entry["sha256"][:12]))
    print("[checkpoint] OK recover stage={} files={} -> {}".format(
        args.stage, len(entries), os.path.abspath(args.out)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="阶段快照：save / list / recover")
    parser.add_argument("--out", default="/app/output", help="产物目录")
    parser.add_argument("--work", default="/app/work", help="工作目录（快照存于其 checkpoints/ 下）")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, helptext in (
            ("save", cmd_save, "保存 --out 顶层 .json 到 --work/checkpoints/<stage>/"),
            ("list", cmd_list, "列出全部快照"),
            ("recover", cmd_recover, "校验 SHA-256 后回滚到指定快照")):
        p = sub.add_parser(name, help=helptext)
        if name in ("save", "recover"):
            p.add_argument("stage", help="阶段名，如 s1-init、s3-search、s5-delivery")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
