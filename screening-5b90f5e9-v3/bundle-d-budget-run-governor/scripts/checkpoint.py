#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checkpoint.py — 检查点与断点续跑日志

每阶段完成后写检查点：阶段名、输入/输出产物的 sha256、时间。
崩溃/中断后按 run_plan.json 的阶段顺序找到第一个"未记录或产物已变/丢失"
的阶段，从该处续跑；已完成且产物完好的阶段绝不重来。

子命令：
  record        --stage S [--inputs p1,p2] [--outputs p3,p4]
  verify        重算全部已记录产物的 sha256 并比对（0=全部完好，3=有缺失/不一致）
  list          列出已记录检查点
  resume-point  依据 run_plan.json 输出续跑起点阶段名（全部完好输出 ALL_DONE）

退出码：0 成功；2 用法/输入错误；3 运行时失败或产物校验不通过。
幂等：同一阶段重复 record 覆盖旧记录。
仅使用 Python 标准库。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT_WORK = os.environ.get("BRG_WORK", "/app/work")
CP_NAME = "checkpoint.json"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cp_path(work):
    return os.path.join(work, CP_NAME)


def load_cp(work):
    try:
        with open(cp_path(work), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "updated_at": None, "order": [], "stages": {}}


def save_cp(work, cp):
    cp["updated_at"] = now_iso()
    tmp = cp_path(work) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, cp_path(work))


def hash_paths(paths, role):
    """返回 {path: sha256}；任一文件缺失则抛 FileNotFoundError。"""
    out = {}
    for p in paths:
        if not os.path.isfile(p):
            raise FileNotFoundError("%s 产物缺失: %s" % (role, p))
        out[p] = sha256_file(p)
    return out


def verify_stage(entry):
    """返回 (ok, problems[list])。"""
    problems = []
    for role in ("inputs", "outputs"):
        for path, expect in (entry.get(role) or {}).items():
            if not os.path.isfile(path):
                problems.append("缺失: %s" % path)
                continue
            actual = sha256_file(path)
            if actual != expect:
                problems.append("sha256 不一致: %s" % path)
    return (not problems, problems)


def cmd_record(args):
    inputs = [p for p in (args.inputs or "").split(",") if p]
    outputs = [p for p in (args.outputs or "").split(",") if p]
    try:
        in_map = hash_paths(inputs, "输入")
        out_map = hash_paths(outputs, "输出")
    except FileNotFoundError as e:
        print("[checkpoint] 错误：%s。阶段未完成不得记录检查点。" % e, file=sys.stderr)
        return 3
    cp = load_cp(args.work)
    if args.stage not in cp["order"]:
        cp["order"].append(args.stage)
    cp["stages"][args.stage] = {
        "seq": cp["order"].index(args.stage) + 1,
        "ts": now_iso(),
        "inputs": in_map,
        "outputs": out_map,
    }
    save_cp(args.work, cp)
    print("[checkpoint] 已记录阶段 %s（输入 %d 项，输出 %d 项）"
          % (args.stage, len(in_map), len(out_map)))
    return 0


def cmd_verify(args):
    cp = load_cp(args.work)
    if not cp["stages"]:
        print("[checkpoint] 无任何检查点。")
        return 0
    bad = 0
    for name in cp["order"]:
        ok, problems = verify_stage(cp["stages"][name])
        if ok:
            print("[checkpoint] %-12s OK" % name)
        else:
            bad += 1
            for p in problems:
                print("[checkpoint] %-12s 问题: %s" % (name, p))
    if bad:
        print("[checkpoint] %d 个阶段校验不通过，续跑将从最早的问题阶段开始。" % bad)
        return 3
    print("[checkpoint] 全部 %d 个阶段产物完好。" % len(cp["stages"]))
    return 0


def cmd_list(args):
    cp = load_cp(args.work)
    print(json.dumps({"order": cp["order"],
                      "stages": {k: {"seq": v["seq"], "ts": v["ts"]}
                                 for k, v in cp["stages"].items()}},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_resume_point(args):
    plan_path = args.plan or os.path.join(args.work, "run_plan.json")
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("[checkpoint] 错误：无法读取运行计划 %s: %s" % (plan_path, e), file=sys.stderr)
        return 2
    cp = load_cp(args.work)
    for phase in plan.get("phases", []):
        name = phase.get("name")
        entry = cp["stages"].get(name)
        if entry is None:
            print(name)
            return 0
        ok, _ = verify_stage(entry)
        if not ok:
            print(name)  # 产物缺失或被改动：从该阶段重做，其后续阶段一并重跑
            return 0
    print("ALL_DONE")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="检查点日志与断点续跑定位")
    ap.add_argument("--work", default=DEFAULT_WORK, help="中间产物目录（默认 %(default)s，可用 BRG_WORK 覆盖）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record", help="记录阶段检查点")
    p.add_argument("--stage", required=True)
    p.add_argument("--inputs", default="", help="逗号分隔的输入产物路径")
    p.add_argument("--outputs", default="", help="逗号分隔的输出产物路径")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("verify", help="校验全部检查点产物")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("list", help="列出检查点")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("resume-point", help="输出续跑起点阶段名")
    p.add_argument("--plan", default=None, help="run_plan.json 路径（默认 <work>/run_plan.json）")
    p.set_defaults(func=cmd_resume_point)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[checkpoint] 致命错误: %r" % e, file=sys.stderr)
        sys.exit(3)
