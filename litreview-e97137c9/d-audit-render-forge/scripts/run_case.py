#!/usr/bin/env python3
"""run_case.py — bundle D 编排器。

用法：
  python3 run_case.py init     --case /input/case.json --task /input/task.md \
                               --input-dir /input --work /app/work --out /app/output
  python3 run_case.py render   --work /app/work --out /app/output
  python3 run_case.py finalize --work /app/work --out /app/output

init     = ingest（防御式解析 + 锚点化 + 分级）+ 数秒内写出 partial result.json（in_progress）。
render   = compile_audit（审计包锻造）+ link_check（链接闸口，失败则本命令非零退出）。
finalize = build_result（组装 + 契约镜像）+ validate_result（schema 闸口，失败非零退出）。
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_result  # noqa: E402
import compile_audit  # noqa: E402
import ingest  # noqa: E402
import link_check  # noqa: E402
import validate_result  # noqa: E402


def append_log(work, msg):
    log_path = os.path.join(work, "change_log.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else []
    log.append(msg)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def cmd_init(args):
    profile, docs, groups = ingest.build_corpus(args.case, args.task, args.input_dir, args.work)
    os.makedirs(args.out, exist_ok=True)
    tiers = {}
    for d in docs:
        tiers[d["tier"]] = tiers.get(d["tier"], 0) + 1
    partial = {
        "case_id": profile["case_id"],
        "status": "in_progress",
        "note": "init 完成：解析与锚点化已落盘；模型阶段（筛选/主题/证据表/草稿）进行中。",
        "docs": len(docs), "tiers": tiers, "dup_groups": len(groups),
    }
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(partial, f, ensure_ascii=False, indent=2)
    append_log(args.work, f"init: 解析 {len(docs)} 篇（tiers {tiers}），近重复组 {len(groups)} 个")
    print(json.dumps(partial, ensure_ascii=False))
    return 0


def cmd_render(args):
    stats = compile_audit.run(args.work, args.out)
    rc = link_check.run(args.work, args.out)
    draft_src = os.path.join(args.work, "review_draft.md")
    if os.path.exists(draft_src):
        shutil.copy(draft_src, os.path.join(args.out, "review_draft.md"))
    append_log(args.work,
               f"render: 论断 {stats['claims']} 句、证据 {stats['evidence']} 行；"
               f"link_check {'通过' if rc == 0 else '失败'}")
    return rc


def cmd_finalize(args):
    result = build_result.build(args.work, args.out)
    append_log(args.work, f"finalize: result.json 组装完成（status={result.get('status')}）")
    # build 之后再补一次日志落盘进 result 的 change_log
    build_result.build(args.work, args.out)
    report_path = os.path.join(args.out, "validation_report.json")
    rc = validate_result.validate(
        os.path.join(HERE, "..", "schemas", "result.schema.json"),
        os.path.join(args.out, "result.json"),
        os.path.join(args.work, "case_profile.json"),
        report_path)
    print(json.dumps({"status": result.get("status"),
                      "validation_ok": rc == 0}, ensure_ascii=False))
    return rc


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--case", required=True)
    p.add_argument("--task", default=None)
    p.add_argument("--input-dir", default=None)
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    for name in ("render", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True)
        p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rc = {"init": cmd_init, "render": cmd_render, "finalize": cmd_finalize}[args.cmd](args)
    sys.exit(rc)


if __name__ == "__main__":
    main(sys.argv[1:])
