#!/usr/bin/env python3
"""runlog.py — 追加式运行日志（断点续跑与防篡改登记账）。

子命令：
  record  登记一个步骤的输入/产物（SHA-256 + 路径 + 字节数），追加进 runlog.jsonl
  verify  重算所有已登记文件哈希，任一被篡改/缺失 → exit 3 并指名步骤与文件
  status  列出已完成步骤与产物清单，并给出断点续跑的下一个标准环节

约定：
- 路径按登记时所给字符串原样存储；verify/status 将相对路径解析到 runlog 所在目录。
- 同一路径被多次登记（步骤重跑）时，以最后一次登记为准。
- runlog 自身是账本（含时间戳），不参与 replay 字节比对；产物文件必须保持确定性。

退出码：0=通过；2=runlog 或登记文件缺失（R1/R2）；3=校验失败（V1 篡改 / V2 缺失）。
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

STANDARD_STEPS = ["ingest", "dedupe", "screen_ta", "screen_ft",
                  "appraise", "extract", "synthesize", "deliver"]


def eprint(*a):
    print(*a, file=sys.stderr)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_entries(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                eprint(f"R2: runlog 第 {i} 行 JSON 非法: {e}")
                sys.exit(2)
    return entries


def file_meta(path):
    return {"path": path, "sha256": sha256_file(path), "bytes": os.path.getsize(path)}


def cmd_record(args):
    metas = {"inputs": [], "outputs": []}
    for kind in ("inputs", "outputs"):
        for p in getattr(args, kind):
            if not os.path.isfile(p):
                eprint(f"R2: 登记文件不存在: {p}（步骤 {args.step} 未登记，请先确认产物已生成）")
                return 2
            metas[kind].append(file_meta(p))
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": args.step,
        "actor": args.actor,
        "inputs": metas["inputs"],
        "outputs": metas["outputs"],
        "note": args.note or "",
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
    with open(args.log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"已登记 step={args.step} actor={args.actor} "
          f"inputs={len(metas['inputs'])} outputs={len(metas['outputs'])} → {args.log}")
    return 0


def cmd_verify(args):
    if not os.path.isfile(args.log):
        eprint(f"R1: runlog 不存在: {args.log}（尚无可校验的登记）")
        return 2
    entries = load_entries(args.log)
    logdir = os.path.dirname(os.path.abspath(args.log))
    latest = {}  # path -> (step, sha256)
    for e in entries:
        for kind in ("inputs", "outputs"):
            for m in e.get(kind, []):
                latest[m["path"]] = (e.get("step", "?"), m["sha256"])
    bad = 0
    for path, (step, want) in sorted(latest.items()):
        real = path if os.path.isabs(path) else os.path.join(logdir, path)
        if not os.path.isfile(real):
            eprint(f"V2: 校验失败：步骤 {step} 的登记文件缺失: {path}")
            bad += 1
            continue
        got = sha256_file(real)
        if got != want:
            eprint(f"V1: 校验失败：步骤 {step} 的文件 {path} 哈希不符"
                   f"（登记 {want[:12]}… / 实际 {got[:12]}…），该文件在登记后被修改")
            bad += 1
    if bad:
        eprint(f"verify: {bad} 个文件未通过校验（共登记 {len(latest)} 个）")
        return 3
    print(f"verify: {len(latest)} 个登记文件全部一致，0 个被篡改")
    return 0


def cmd_status(args):
    if not os.path.isfile(args.log):
        print(f"runlog 不存在: {args.log}；尚无任何步骤登记，请从首个标准环节 {STANDARD_STEPS[0]} 开始。")
        return 0
    entries = load_entries(args.log)
    by_step = {}
    for e in entries:
        by_step[e.get("step", "?")] = e  # 最后一次登记为准
    if not by_step:
        print("runlog 为空：尚无任何步骤登记。")
        return 0
    print(f"已完成步骤（{len(by_step)} 个，按 runlog 登记顺序）：")
    seen = []
    for e in entries:
        s = e.get("step", "?")
        if s not in seen:
            seen.append(s)
    for s in seen:
        e = by_step[s]
        outs = ", ".join(f"{m['path']}({m['bytes']}B)" for m in e.get("outputs", [])) or "无产物"
        print(f"  - {s}: actor={e.get('actor','?')} ts={e.get('ts','?')} 产物: {outs}")
    done = set(by_step)
    nxt = next((s for s in STANDARD_STEPS if s not in done), None)
    if nxt:
        print(f"断点续跑建议：首个未登记的标准环节是 {nxt}，请先 verify 再从该环节继续。")
    else:
        print("全部标准环节均已登记；交付前请执行 verify 与 replay 自证。")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default="runlog.jsonl", help="runlog.jsonl 路径（默认当前目录）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record", help="登记步骤的输入与产物哈希")
    p.add_argument("--step", required=True, help="步骤标识，如 dedupe / screen_ta")
    p.add_argument("--actor", required=True, help="操作者，如 agent / human / selfcheck")
    p.add_argument("--inputs", nargs="*", default=[], help="输入文件路径列表")
    p.add_argument("--outputs", nargs="*", default=[], help="产物文件路径列表")
    p.add_argument("--note", default="", help="备注")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("verify", help="重算登记文件哈希并比对")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("status", help="列出已完成步骤与断点续跑建议")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
