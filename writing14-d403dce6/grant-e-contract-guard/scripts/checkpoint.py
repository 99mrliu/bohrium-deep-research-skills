#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checkpoint.py — 检查点：截断后找回最近合法状态。

子命令：
  save     记录当前输出目录关键文件清单（路径+字节数+md5）到 checkpoints.jsonl
           （追加一行），并把 result.json 复制为 result.<stage>.json 快照
  list     按时间线显示全部检查点
  restore  把指定阶段的 result.<stage>.json 快照复制回 result.json（实际复制）

退出码：0 成功；1 输入/环境错误（阶段不存在、result.json 缺失等）。

确定性：不读墙钟；时间线以追加序号排序，--now 仅为可选标注，默认固定值。
阶段名仅允许 [A-Za-z0-9_-]，防止路径注入。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

STAGE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# 纳入清单的关键文件（存在才记录；其余 .md/.json 也会被发现）
KEY_NAMES = ("result.json", "plan.json", "proposal_draft.md",
             "element_mapping.md", "sources.md")


def eprint(msg):
    sys.stderr.write(msg + "\n")


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_files(output_dir):
    """收集输出目录内关键文件清单：KEY_NAMES 优先，外加其余顶层 .md/.json。"""
    seen = []
    candidates = list(KEY_NAMES)
    try:
        for name in sorted(os.listdir(output_dir)):
            if name.endswith((".md", ".json")) and not name.startswith("result."):
                candidates.append(name)
    except OSError as exc:
        eprint("错误：无法列出输出目录 %s：%s" % (output_dir, exc))
        sys.exit(1)
    for name in candidates:
        path = os.path.join(output_dir, name)
        if name in seen or not os.path.isfile(path):
            continue
        seen.append(name)
    files = []
    for name in seen:
        path = os.path.join(output_dir, name)
        files.append({"path": name,
                      "bytes": os.path.getsize(path),
                      "md5": md5_of(path)})
    return files


def load_store(store):
    entries = []
    if not os.path.exists(store):
        return entries
    try:
        with open(store, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    eprint("错误：%s 第 %d 行 JSON 损坏：%s" % (store, lineno, exc))
                    sys.exit(1)
    except OSError as exc:
        eprint("错误：无法读取 %s：%s" % (store, exc))
        sys.exit(1)
    return entries


def valid_stage(stage):
    return bool(STAGE_RE.match(stage))


def cmd_save(args):
    if not valid_stage(args.stage):
        eprint("错误：阶段名非法：%r（仅允许 [A-Za-z0-9_-]，≤64 字符）" % args.stage)
        sys.exit(1)
    result_path = os.path.join(args.output_dir, "result.json")
    if not os.path.isfile(result_path):
        eprint("错误：%s 不存在——先运行 contract_probe.py 落保底 result.json。" % result_path)
        sys.exit(1)
    entries = load_store(args.store)
    entry = {
        "seq": len(entries) + 1,
        "stage": args.stage,
        "note": args.note or "",
        "recorded_at": args.now,
        "files": snapshot_files(args.output_dir),
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.store)), exist_ok=True)
        with open(args.store, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as exc:
        eprint("错误：无法写入 %s：%s" % (args.store, exc))
        sys.exit(1)
    snap_path = os.path.join(args.output_dir, "result.%s.json" % args.stage)
    try:
        shutil.copyfile(result_path, snap_path)
    except OSError as exc:
        eprint("错误：快照复制失败：%s" % exc)
        sys.exit(1)
    print("检查点 #%d 已保存：stage=%s note=%s" % (entry["seq"], args.stage, args.note or ""))
    for fi in entry["files"]:
        print("  %s  %dB  md5=%s" % (fi["path"], fi["bytes"], fi["md5"]))
    print("result.json 快照 -> %s" % snap_path)
    sys.exit(0)


def cmd_list(args):
    entries = load_store(args.store)
    if not entries:
        print("（尚无检查点）")
        sys.exit(0)
    print("检查点时间线（共 %d 个）：" % len(entries))
    for e in entries:
        names = "、".join(fi["path"] for fi in e.get("files", []))
        print("  #%d  stage=%s  note=%s  文件：%s" % (
            e.get("seq"), e.get("stage"), e.get("note") or "", names))
    sys.exit(0)


def cmd_restore(args):
    if not valid_stage(args.stage):
        eprint("错误：阶段名非法：%r" % args.stage)
        sys.exit(1)
    entries = [e for e in load_store(args.store) if e.get("stage") == args.stage]
    if not entries:
        eprint("错误：未找到阶段 %r 的检查点（用 list 查看已有阶段）。" % args.stage)
        sys.exit(1)
    entry = entries[-1]
    snap_path = os.path.join(args.output_dir, "result.%s.json" % args.stage)
    if not os.path.isfile(snap_path):
        eprint("错误：快照文件缺失：%s（检查点记录存在但快照已被删除）" % snap_path)
        sys.exit(1)
    dest = os.path.join(args.output_dir, "result.json")
    try:
        shutil.copyfile(snap_path, dest)
    except OSError as exc:
        eprint("错误：恢复失败：%s" % exc)
        sys.exit(1)
    print("已从检查点 #%d（stage=%s）恢复：%s -> %s" % (entry.get("seq"), args.stage, snap_path, dest))
    print("恢复后请运行 contract_probe.py --validate 复核合同合法性。")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(
        description="检查点：save 存快照 / list 看时间线 / restore 恢复快照。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功；1 输入或环境错误。")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("save", help="保存检查点")
    p.add_argument("--stage", required=True, help="阶段名 [A-Za-z0-9_-]")
    p.add_argument("--note", default="", help="说明")
    p.add_argument("--output-dir", default="/app/output", help="输出目录")
    p.add_argument("--store", default="/app/work/checkpoints.jsonl", help="检查点记录文件")
    p.add_argument("--now", default="1970-01-01T00:00:00Z",
                   help="可选时间标注（默认固定值保证确定性；真实运行由调用方传入）")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("list", help="列出检查点时间线")
    p.add_argument("--store", default="/app/work/checkpoints.jsonl", help="检查点记录文件")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("restore", help="从快照恢复 result.json")
    p.add_argument("--stage", required=True, help="要恢复的阶段名")
    p.add_argument("--output-dir", default="/app/output", help="输出目录")
    p.add_argument("--store", default="/app/work/checkpoints.jsonl", help="检查点记录文件")
    p.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
