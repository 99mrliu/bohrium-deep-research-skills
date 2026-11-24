#!/usr/bin/env python3
"""run_case.py — bundle B 编排器（contract-first-budget-orchestrator）。

用法：
  python3 run_case.py init     --case /input/case.json --task /input/task.md \
                               --input-dir /input --work /app/work --out /app/output [--budget 64]
  python3 run_case.py check    --work /app/work --out /app/output
  python3 run_case.py finalize --work /app/work --out /app/output

init 在数秒内完成：防御式解析（ingest）→ 契约探针（contract_probe，立即写
status=in_progress 的 partial result.json 与 requirements.md）→ 预算编排
（budget_ledger plan，写 run_plan.json 与 state.json checkpoint）。
check 执行阶段-产物一致性校验；finalize 组装终版 result.json。
中断恢复：任意时刻可用 `budget_ledger.py status` 查看剩余预算与已完成阶段，
`check` 会指出"标记完成但产物缺失"的阶段。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_result  # noqa: E402
import consistency_check  # noqa: E402
import contract_probe  # noqa: E402
import ingest  # noqa: E402


def _run_budget_plan(work, budget):
    """以子进程方式调用 budget_ledger.py plan（保持其 CLI 契约）。"""
    import subprocess
    cmd = [sys.executable, os.path.join(HERE, "budget_ledger.py"), "plan",
           "--work", work, "--budget", str(budget)]
    subprocess.run(cmd, check=True)


def cmd_init(args):
    profile, docs, groups = ingest.build_corpus(args.case, args.task, args.input_dir, args.work)
    cmap, reqs = contract_probe.probe(args.work, args.out)  # 内部已写 partial result.json
    _run_budget_plan(args.work, args.budget)
    log_path = os.path.join(args.work, "change_log.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else []
    log.insert(0, f"init: 解析 {len(docs)} 篇，契约字段 {len(cmap['fields'])} 个，"
                  f"硬性要求 {len(reqs)} 条，近重复组 {len(groups)} 个；"
                  f"partial result.json 已写出")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps({"init": "ok", "case_id": profile["case_id"], "docs": len(docs),
                      "contract_fields": len(cmap["fields"]),
                      "partial_result": os.path.join(args.out, "result.json")},
                     ensure_ascii=False))


def cmd_check(args):
    report = consistency_check.run(args.work, args.out)
    print(json.dumps({"ok": report["ok"], "problems": report["problems"],
                      "completed_phases": report["completed_phases"]},
                     ensure_ascii=False))
    if not report["ok"]:
        sys.exit(1)


def cmd_finalize(args):
    result = build_result.build(args.work, args.out)
    print(json.dumps({"status": result.get("status"), "fields": len(result)},
                     ensure_ascii=False))


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
    p.add_argument("--budget", type=int, default=64)
    p = sub.add_parser("check")
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("finalize")
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    {"init": cmd_init, "check": cmd_check, "finalize": cmd_finalize}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
