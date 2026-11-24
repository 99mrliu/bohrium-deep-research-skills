#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replay_pack.py — 运行日志 → replay manifest → fresh/stale 复跑核验

子命令：
  log     向 run_log.jsonl 追加一步：命令 + 每个输入/输出文件的 SHA-256 + UTC 时间戳；
  pack    把 run_log.jsonl 编译为 replay_manifest.json（有序步骤、文件哈希、环境说明）；
  verify  按 manifest 重新哈希所引用的文件，逐步报告 fresh（未变化）/ stale（哈希不符）/
          missing-input（输入缺失，无法复跑）。

退出码：log/pack 成功 0；verify 只要任一步骤输入文件缺失即 1（无法复跑），
否则 0（stale 仅如实报告，不算失败）；用法/输入错误一律 2。
"""
import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_entry(path, role):
    """role 仅用于报错措辞。文件缺失：input → exit 2；output → 记录 null + 警告。"""
    if not os.path.isfile(path):
        if role == "input":
            print(f"[错误] 输入文件不存在: {path}", file=sys.stderr)
            sys.exit(2)
        print(f"[警告] 输出文件当前不存在: {path}（sha256 记为 null）", file=sys.stderr)
        return {"path": path, "sha256": None}
    return {"path": path, "sha256": sha256_file(path)}


def cmd_log(args):
    entry = {
        "ts": utc_now(),
        "cmd": args.cmd,
        "workdir": os.path.abspath(args.workdir or os.getcwd()),
        "inputs": [hash_entry(p, "input") for p in (args.inputs or [])],
        "outputs": [hash_entry(p, "output") for p in (args.outputs or [])],
    }
    n = 0
    if os.path.isfile(args.runlog):
        with open(args.runlog, "r", encoding="utf-8") as f:
            n = sum(1 for line in f if line.strip())
    entry["step"] = n + 1
    d = os.path.dirname(os.path.abspath(args.runlog))
    os.makedirs(d, exist_ok=True)
    with open(args.runlog, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[完成] 已追加步骤 {entry['step']} → {args.runlog}")
    print(f"  cmd    : {entry['cmd']}")
    print(f"  inputs : {len(entry['inputs'])} 个文件已哈希")
    print(f"  outputs: {len(entry['outputs'])} 个文件已哈希")
    return 0


def load_runlog(path):
    if not os.path.isfile(path):
        print(f"[错误] run log 不存在: {path}", file=sys.stderr)
        sys.exit(2)
    steps = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                steps.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[错误] run log 第 {i} 行 JSON 解析失败: {e}", file=sys.stderr)
                sys.exit(2)
    return steps


def cmd_pack(args):
    steps = load_runlog(args.runlog)
    manifest = {
        "manifest_version": 1,
        "generated_at": utc_now(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "note": ("路径按记录时的工作目录写入；第三方复跑前请将各 path 还原到等价位置，"
                     "或以 verify 确认文件哈希一致后再按 cmd 顺序重放。"),
        },
        "steps": steps,
    }
    d = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(d, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[完成] replay manifest 已写入: {args.out}（{len(steps)} 个步骤）")
    return 0


def verify_step(step):
    """返回 (status, details)。status ∈ fresh / stale / missing-input。"""
    details = []
    missing_input = False
    stale = False
    for group, role in (("inputs", "输入"), ("outputs", "输出")):
        for fe in step.get(group, []):
            path, want = fe.get("path"), fe.get("sha256")
            if not os.path.isfile(path):
                details.append(f"{role}缺失: {path}")
                if group == "inputs":
                    missing_input = True
                else:
                    stale = True
                continue
            got = sha256_file(path)
            if want is None or got != want:
                details.append(f"{role}哈希不符: {path}")
                stale = True
    if missing_input:
        return "missing-input", details
    return ("stale" if stale else "fresh"), details


def cmd_verify(args):
    if not os.path.isfile(args.manifest):
        print(f"[错误] manifest 不存在: {args.manifest}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[错误] manifest JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(2)

    steps = manifest.get("steps", [])
    n_fresh = n_stale = n_missing = 0
    print(f"[verify] manifest 生成于 {manifest.get('generated_at')}，共 {len(steps)} 步")
    for i, step in enumerate(steps, 1):
        status, details = verify_step(step)
        if status == "fresh":
            n_fresh += 1
        elif status == "stale":
            n_stale += 1
        else:
            n_missing += 1
        label = {"fresh": "fresh（可复跑，文件未变化）",
                 "stale": "stale（文件已变化，重放结果可能不同）",
                 "missing-input": "missing-input（输入缺失，无法复跑）"}[status]
        print(f"  步骤 {i}: {label}")
        print(f"    cmd: {step.get('cmd')}")
        for d in details:
            print(f"    - {d}")
    print(f"[汇总] fresh={n_fresh} stale={n_stale} missing-input={n_missing}")
    if n_missing:
        print("[结论] 存在输入缺失的步骤，无法完整复跑", file=sys.stderr)
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="subcmd", required=True)

    p_log = sub.add_parser("log", help="追加一条带哈希的运行日志")
    p_log.add_argument("--runlog", required=True)
    p_log.add_argument("--cmd", required=True)
    p_log.add_argument("--inputs", nargs="*", default=[])
    p_log.add_argument("--outputs", nargs="*", default=[])
    p_log.add_argument("--workdir", default=None)
    p_log.set_defaults(func=cmd_log)

    p_pack = sub.add_parser("pack", help="编译 replay manifest")
    p_pack.add_argument("--runlog", required=True)
    p_pack.add_argument("--out", required=True)
    p_pack.set_defaults(func=cmd_pack)

    p_ver = sub.add_parser("verify", help="核验 fresh/stale/missing-input")
    p_ver.add_argument("--manifest", required=True)
    p_ver.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
