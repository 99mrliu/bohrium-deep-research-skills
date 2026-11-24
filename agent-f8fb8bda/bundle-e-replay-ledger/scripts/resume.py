#!/usr/bin/env python3
"""resume.py — 阶段检查点（中断续跑 + 产物防改）。

子命令：
  mark-done     --stage NAME [--out DIR] [--file PATH 可重复]
                把该阶段声明的产物文件哈希记录到 <out>/checkpoints/stages.json
                （--out 默认 /app/work）。--file 给出相对 --out 的产物路径；
                不给出时哈希 --out 下全部文件（排除 checkpoints/）。
  status        [--out DIR]
                打印各阶段完成态与产物清单。
  verify-resume [--out DIR]
                重算已完成阶段的产物哈希：被改/缺失 -> exit 1 并点名需重跑的阶段；
                全部一致 -> exit 0，可安全续跑后续阶段。

退出码：0 通过；1 门控违例；2 用法/IO 错误。
"""
import argparse
import hashlib
import json
import os
import sys
import time

DEFAULT_OUT = "/app/work"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ck_path(out_dir):
    return os.path.join(out_dir, "checkpoints", "stages.json")


def load_ck(out_dir):
    p = ck_path(out_dir)
    if not os.path.exists(p):
        return {"stages": {}}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_ck(out_dir, data):
    p = ck_path(out_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cmd_mark_done(args):
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    files = {}
    if args.file:
        rels = args.file
    else:
        rels = []
        for dirpath, dirnames, filenames in os.walk(out_dir):
            dirnames[:] = sorted(d for d in dirnames if d != "checkpoints")
            for name in sorted(filenames):
                rels.append(os.path.relpath(os.path.join(dirpath, name), out_dir))
    missing = []
    for rel in rels:
        full = os.path.join(out_dir, rel)
        if not os.path.exists(full):
            missing.append(rel)
        else:
            files[rel] = {"sha256": sha256_file(full), "bytes": os.path.getsize(full)}
    if missing:
        print("[ERROR] 声明的产物文件不存在：", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(2)
    data = load_ck(out_dir)
    data["stages"][args.stage] = {
        "done": True,
        "marked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "artifacts": files,
    }
    save_ck(out_dir, data)
    print(f"[OK] stage '{args.stage}' 标记完成，登记产物 {len(files)} 个 -> {ck_path(out_dir)}")
    sys.exit(0)


def cmd_status(args):
    data = load_ck(args.out)
    stages = data.get("stages", {})
    if not stages:
        print("[INFO] 尚无已完成阶段（checkpoints 为空或不存在）")
        sys.exit(0)
    print(json.dumps({"out": os.path.abspath(args.out), "stages": stages},
                     ensure_ascii=False, indent=2))
    sys.exit(0)


def cmd_verify_resume(args):
    out_dir = args.out
    data = load_ck(out_dir)
    stages = data.get("stages", {})
    if not stages:
        print("[ERROR] 无检查点可校验（stages.json 为空或不存在）", file=sys.stderr)
        sys.exit(2)
    bad = {}
    for name, st in sorted(stages.items()):
        problems = []
        for rel, meta in sorted(st.get("artifacts", {}).items()):
            full = os.path.join(out_dir, rel)
            if not os.path.exists(full):
                problems.append(f"产物缺失: {rel}")
                continue
            actual = sha256_file(full)
            if actual != meta["sha256"]:
                problems.append(f"产物被改: {rel} expect={meta['sha256'][:16]}… "
                                f"actual={actual[:16]}…")
        if problems:
            bad[name] = problems
    if bad:
        print("[GATE FAIL] 检查点校验未通过，以下阶段产物已被改动，必须重跑对应阶段：")
        for name, problems in bad.items():
            print(f"  stage '{name}':")
            for pr in problems:
                print(f"    - {pr}")
        sys.exit(1)
    ok = ", ".join(sorted(stages))
    print(f"[OK] 检查点校验通过：已完成阶段（{ok}）产物哈希全部一致，可从下一阶段续跑")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(description="阶段检查点 mark-done/status/verify-resume")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("mark-done")
    pm.add_argument("--stage", required=True)
    pm.add_argument("--out", default=DEFAULT_OUT)
    pm.add_argument("--file", action="append", default=[])
    pm.set_defaults(fn=cmd_mark_done)

    ps = sub.add_parser("status")
    ps.add_argument("--out", default=DEFAULT_OUT)
    ps.set_defaults(fn=cmd_status)

    pv = sub.add_parser("verify-resume")
    pv.add_argument("--out", default=DEFAULT_OUT)
    pv.set_defaults(fn=cmd_verify_resume)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
