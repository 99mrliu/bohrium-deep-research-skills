#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkpoint.py —— 阶段快照：长跑任务的中断恢复与"先存 partial 再迭代"
（仅 Python3 标准库）。

治理意图：slides 任务跨六个阶段、产物多（result.json、deck、预览、映射），
任何一次修复回路都可能改坏已有成果。每个阶段结束存一次命名快照，改坏即回滚。

子命令：
  save <name>     把 --out 目录全部文件（递归，相对路径）复制到
                  --work/checkpoints/<name>/，并写 manifest.json
                  （快照名、每文件 SHA-256 与字节数、保存时刻）。
                  若 checkpoints 目录恰在 --out 内则自动跳过，防止自嵌套
  list            列出全部快照（名称、保存时刻、文件数）
  verify <name>   只按 manifest 逐文件重算 SHA-256 校验，不回滚
  recover <name>  先全量校验（任一文件不符即整体中止、点名篡改文件、
                  不做半恢复），全部通过后把快照复制回 --out

退出码：
  0  成功
  1  操作失败（无文件可存、快照不存在、manifest 损坏、SHA-256 校验不符）
  2  用法 / IO 错误（参数非法、--out 不存在等）

说明：manifest.json 的 saved_at_* 是唯一的非确定性内容（人读时间戳），
不参与任何门控判定；快照内数据文件逐字节复制，无改写。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
CHECKPOINTS_DIRNAME = "checkpoints"


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
    return os.path.join(work, CHECKPOINTS_DIRNAME)


def valid_name(name):
    return bool(NAME_RE.match(name or ""))


def collect_files(out_dir):
    """递归收集 --out 下全部文件的相对路径；跳过顶层 checkpoints/ 防自嵌套。"""
    rels = []
    for root, dirs, files in os.walk(out_dir):
        rel_root = os.path.relpath(root, out_dir)
        if rel_root == ".":
            dirs[:] = [d for d in dirs if d != CHECKPOINTS_DIRNAME]
        for name in files:
            full = os.path.join(root, name)
            if os.path.isfile(full):
                rels.append(os.path.relpath(full, out_dir))
    return sorted(rels)


def load_manifest(src_dir):
    mpath = os.path.join(src_dir, "manifest.json")
    try:
        with open(mpath, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "manifest.json 不可用：{}".format(exc)
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        return None, "manifest.json 中 files 为空或非法"
    return manifest, None


def verify_entries(src_dir, entries):
    """逐文件校验，返回 (ok, 第一个失败细节)。"""
    for entry in entries:
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            return False, "manifest 条目缺 name"
        fpath = os.path.join(src_dir, name)
        if not os.path.isfile(fpath):
            return False, "快照内文件缺失：{}".format(name)
        actual = sha256_of(fpath)
        if actual != entry.get("sha256"):
            return False, ("SHA-256 校验不符：{}（manifest 记录 {}…，实际 {}…）".format(
                name, str(entry.get("sha256"))[:12], actual[:12]))
    return True, None


def cmd_save(args):
    if not valid_name(args.name):
        print("[checkpoint] USAGE ERROR: 非法快照名 {!r}（允许 [A-Za-z0-9_-]，字母数字开头）".format(
            args.name))
        return 2
    if not os.path.isdir(args.out):
        print("[checkpoint] USAGE/IO ERROR: --out 目录不存在：{}".format(args.out))
        return 2
    rels = collect_files(args.out)
    if not rels:
        print("[checkpoint] FAIL: --out 下没有文件，无快照可存：{}".format(args.out))
        return 1
    dest = os.path.join(ckpt_root(args.work), args.name)
    os.makedirs(dest, exist_ok=True)
    manifest = {
        "name": args.name,
        "saved_at_epoch": int(time.time()),
        "saved_at_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_out": os.path.abspath(args.out),
        "note": "saved_at_* 仅为人读时间戳，不参与门控；数据文件逐字节复制",
        "files": [],
    }
    for rel in rels:
        src = os.path.join(args.out, rel)
        tgt = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        digest = sha256_of(src)
        shutil.copyfile(src, tgt)
        manifest["files"].append({"name": rel, "sha256": digest,
                                  "bytes": os.path.getsize(src)})
        print("[checkpoint]   + {} (sha256 {}…, {} bytes)".format(rel, digest[:12],
                                                                  os.path.getsize(src)))
    dump_json(os.path.join(dest, "manifest.json"), manifest)
    print("[checkpoint] OK save name={} files={} -> {}".format(args.name, len(rels), dest))
    return 0


def cmd_list(args):
    root = ckpt_root(args.work)
    if not os.path.isdir(root):
        print("[checkpoint] (无快照：{} 不存在)".format(root))
        return 0
    names = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    if not names:
        print("[checkpoint] (无快照)")
        return 0
    for name in names:
        manifest, err = load_manifest(os.path.join(root, name))
        if err:
            print("[checkpoint] {} | ({})".format(name, err))
        else:
            files = manifest.get("files", [])
            print("[checkpoint] {} | saved_at={} | files={}".format(
                name, manifest.get("saved_at_local", "?"), len(files)))
    return 0


def cmd_verify(args):
    if not valid_name(args.name):
        print("[checkpoint] USAGE ERROR: 非法快照名 {!r}".format(args.name))
        return 2
    src_dir = os.path.join(ckpt_root(args.work), args.name)
    if not os.path.isdir(src_dir):
        print("[checkpoint] FAIL: 快照不存在：{}".format(src_dir))
        return 1
    manifest, err = load_manifest(src_dir)
    if err:
        print("[checkpoint] FAIL: {}".format(err))
        return 1
    ok, detail = verify_entries(src_dir, manifest["files"])
    if not ok:
        print("[checkpoint] FAIL: {}".format(detail))
        return 1
    print("[checkpoint] OK verify name={} files={} 全部 SHA-256 相符".format(
        args.name, len(manifest["files"])))
    return 0


def cmd_recover(args):
    if not valid_name(args.name):
        print("[checkpoint] USAGE ERROR: 非法快照名 {!r}".format(args.name))
        return 2
    src_dir = os.path.join(ckpt_root(args.work), args.name)
    if not os.path.isdir(src_dir):
        print("[checkpoint] FAIL: 快照不存在：{}".format(src_dir))
        return 1
    manifest, err = load_manifest(src_dir)
    if err:
        print("[checkpoint] FAIL: {}".format(err))
        return 1
    # 先全量校验，任何一个不符即整体中止并点名，不做半恢复
    ok, detail = verify_entries(src_dir, manifest["files"])
    if not ok:
        print("[checkpoint] FAIL: 拒绝恢复（快照完整性受损）：{}".format(detail))
        return 1
    os.makedirs(args.out, exist_ok=True)
    for entry in manifest["files"]:
        name = entry["name"]
        tgt = os.path.join(args.out, name)
        os.makedirs(os.path.dirname(os.path.abspath(tgt)), exist_ok=True)
        shutil.copyfile(os.path.join(src_dir, name), tgt)
        print("[checkpoint]   <- {} (sha256 {}… 校验通过)".format(name, entry["sha256"][:12]))
    print("[checkpoint] OK recover name={} files={} -> {}".format(
        args.name, len(manifest["files"]), os.path.abspath(args.out)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="阶段快照：save / list / verify / recover")
    parser.add_argument("--out", default="/app/output", help="产物目录")
    parser.add_argument("--work", default="/app/work",
                        help="工作目录（快照存于其 checkpoints/ 下）")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("save", help="保存 --out 全部文件到 --work/checkpoints/<name>/")
    p.add_argument("name", help="快照名，如 p0-intake、p3-deck、p5-delivery")
    p.set_defaults(func=cmd_save)
    p = sub.add_parser("list", help="列出全部快照")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("verify", help="只校验快照 SHA-256，不回滚")
    p.add_argument("name", help="快照名")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("recover", help="先校验 SHA-256，再回滚到指定快照")
    p.add_argument("name", help="快照名")
    p.set_defaults(func=cmd_recover)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
