#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulate_stages.py — 示例驱动器（合成示例专用，非真实评测流程）

真实调用同目录的 plan_run.py / budget_ledger.py / checkpoint.py / flush_partial.py，
用确定性的模拟阶段产物演示一次多阶段运行：plan → scaffold → 循环
[执行阶段 → ledger charge → checkpoint → flush] → 终检。

演示能力：
  --fail-at STAGE   在该阶段前模拟崩溃（exit 3），产生真实的中间现场
  --resume          从最近完好检查点续跑（产物被删/被改也能被 sha256 校验发现并重做）

退出码：0 全部完成；2 用法错误；3 模拟崩溃或运行时失败。
仅使用 Python 标准库。所有"判定"均为占位模拟，不含真实筛选结论。
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_cli(script, *cli_args, expect=0):
    """真实以子进程方式调用兄弟脚本并透传退出码。"""
    cmd = [PY, os.path.join(HERE, script)] + [str(a) for a in cli_args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    for line in (proc.stdout or "").splitlines():
        print("  " + line)
    if proc.returncode != expect:
        for line in (proc.stderr or "").splitlines():
            print("  [stderr] " + line, file=sys.stderr)
        raise SystemExit("[simulate] %s 退出码 %d（期望 %d）" % (script, proc.returncode, expect))
    return proc


def dump(work, name, obj):
    path = os.path.join(work, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def append_change_record(work, record):
    record = dict(record)
    record["ts"] = now_iso()
    with open(os.path.join(work, "change_records.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------- 模拟阶段产物（确定性、占位内容，明确标注非真实判定） ----------

def stage_inventory(work, case, plan):
    srcs = [{"record_id": r.get("record_id"),
             "citation": r.get("citation"),
             **({"fixture_note": r["fixture_note"]} if r.get("fixture_note") else {})}
            for r in case["records"]]
    return dump(work, "inventory.json",
                {"total_records": len(srcs), "sources": srcs,
                 "note": "盘点产物（模拟）"}), []


def stage_scaffold(work, case, plan):
    fields = (case.get("output_contract") or {}).get("required_fields", [])
    return dump(work, "skeleton.json",
                {"contract_fields": fields, "status": "in_progress",
                 "note": "result.json 骨架（模拟）"}), []


def stage_normalize(work, case, plan):
    rows = [{"record_id": r.get("record_id"),
             "title_key": (r.get("title") or "").strip().lower(),
             "year": r.get("year")} for r in case["records"]]
    return dump(work, "normalized.json", {"normalized": rows}), []


def stage_dedupe(work, case, plan):
    seen, clusters, conflict = {}, [], []
    for r in case["records"]:
        key = (r.get("title") or "").strip().lower()
        if key in seen:
            clusters.append({"canonical": seen[key], "duplicate": r.get("record_id"),
                             "basis": "title_key 完全一致（合成夹具重复导出）"})
        else:
            seen[key] = r.get("record_id")
        if r.get("conflicting_reviews"):
            conflict.append({"record_id": r.get("record_id"),
                             "reviews": r["conflicting_reviews"],
                             "resolution": "保守置 uncertain，留待人工复核（模拟）"})
    for c in clusters:
        append_change_record(work, {"action": "merge_duplicate_export",
                                    "canonical": c["canonical"], "duplicate": c["duplicate"],
                                    "basis": c["basis"], "actor": "simulate_stages（合成示例）"})
    return dump(work, "dedup_report.json",
                {"duplicate_clusters": clusters, "conflict_flags": conflict,
                 "note": "去重与冲突标记（模拟）"}), []


def stage_decide(work, case, plan):
    dedup = json.load(open(os.path.join(work, "dedup_report.json"), encoding="utf-8"))
    dups = {c["duplicate"] for c in dedup["duplicate_clusters"]}
    conflicts = {c["record_id"] for c in dedup["conflict_flags"]}
    level = plan["selected_level"]
    evidence = "skeleton" if level == "L2" else "full"
    cycle = ["include", "exclude", "include", "uncertain", "exclude"]
    decisions, i = [], 0
    for r in case["records"]:
        rid = r.get("record_id")
        if rid in dups:
            continue  # 重复导出已合并，不重复判定
        dec = "uncertain" if rid in conflicts else cycle[i % len(cycle)]
        i += 1
        decisions.append({"record_id": rid, "decision": dec,
                          "evidence_level": evidence,
                          "rationale": "（模拟占位判定，非真实筛选结论）"})
    return dump(work, "decisions.json",
                {"decisions": decisions, "batch_size": plan["batch_size"],
                 "evidence_level": evidence,
                 "note": "判定结果（模拟占位）"}), []


def stage_diagnose(work, case, plan):
    decisions = json.load(open(os.path.join(work, "decisions.json"), encoding="utf-8"))
    ids = [d["record_id"] for d in decisions["decisions"]]
    if plan["selected_level"] == "L1":
        ids = ids[: math.ceil(len(ids) / 3)]  # L1：仅诊断子集
    rows = [{"record_id": rid, "note": "（模拟诊断，非真实分析）"} for rid in ids]
    return dump(work, "diagnostics.json",
                {"diagnostics": rows, "coverage": "%d/%d（模拟）"
                 % (len(rows), len(decisions["decisions"]))}), []


def stage_fill(work, case, plan):
    return dump(work, "fill_notes.json",
                {"filled_free_text": True,
                 "note": "自由文本字段填充完成（模拟）"}), []


def stage_final_check(work, case, plan, result_path):
    missing = []
    try:
        result = json.load(open(result_path, encoding="utf-8"))
        for f in (case.get("output_contract") or {}).get("required_fields", []):
            if f not in result:
                missing.append(f)
    except (OSError, json.JSONDecodeError):
        missing = ["<result.json 不可读>"]
    return dump(work, "final_check.json",
                {"all_contract_fields_present": not missing, "missing_fields": missing,
                 "note": "终检（模拟）：合同字段在位性核对，不核对判定内容"}), []


STAGE_FUNCS = ["inventory", "scaffold", "normalize", "dedupe",
               "decide", "diagnose", "fill", "final_check"]


def execute_stage(stage, work, case, plan, output_dir):
    func = globals()["stage_" + stage]
    if stage == "final_check":
        path, extra = func(work, case, plan, os.path.join(output_dir, "result.json"))
    else:
        path, extra = func(work, case, plan)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="合成示例驱动器：真实调用调度器脚本跑多阶段运行")
    ap.add_argument("--case", required=True, help="合成 case.json")
    ap.add_argument("--root", required=True, help="运行根目录（下建 input/work/output）")
    ap.add_argument("--budget-requests", type=int, default=64)
    ap.add_argument("--budget-seconds", type=float, default=900)
    ap.add_argument("--fail-at", default=None, choices=STAGE_FUNCS, help="在该阶段前模拟崩溃")
    ap.add_argument("--resume", action="store_true", help="从最近完好检查点续跑")
    args = ap.parse_args(argv)

    input_dir = os.path.join(args.root, "input")
    work = os.path.join(args.root, "work")
    output = os.path.join(args.root, "output")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    os.makedirs(output, exist_ok=True)
    case_path = os.path.join(input_dir, "case.json")
    if not os.path.isfile(case_path) or not args.resume:
        shutil.copyfile(args.case, case_path)  # 幂等：重复运行重置输入快照
    case = json.load(open(case_path, encoding="utf-8"))
    cr = os.path.join(work, "change_records.jsonl")
    if not args.resume and os.path.isfile(cr):
        os.remove(cr)  # 全新运行重置变更日志，保证幂等；续跑模式保留既有记录

    print("== [simulate] 1/4 生成运行计划（plan_run.py）==")
    run_cli("plan_run.py", "--case", case_path, "--work", work,
            "--budget-requests", args.budget_requests,
            "--budget-seconds", args.budget_seconds)
    plan = json.load(open(os.path.join(work, "run_plan.json"), encoding="utf-8"))
    stages = [p["name"] for p in plan["phases"]]
    est = {p["name"]: p for p in plan["phases"]}

    print("== [simulate] 2/4 初始化预算台账（budget_ledger.py）==")
    ledger_exists = os.path.isfile(os.path.join(work, "budget_ledger.json"))
    if args.resume and ledger_exists:
        print("  [simulate] 续跑模式：保留既有台账，已消耗预算继续计数。")
    else:
        run_cli("budget_ledger.py", "--work", work, "init",
                "--budget-requests", args.budget_requests,
                "--budget-seconds", args.budget_seconds,
                "--reserve", plan["budget"]["reserve_requests"], "--force")

    print("== [simulate] 3/4 定位续跑起点（checkpoint.py resume-point）==")
    if args.resume:
        proc = run_cli("checkpoint.py", "--work", work, "resume-point")
        start = (proc.stdout or "").strip().splitlines()[-1].strip()
        start = start.split()[-1]
        if start == "ALL_DONE":
            print("  [simulate] 全部阶段产物完好，仅重新落盘 result.json。")
            run_cli("flush_partial.py", "--case", case_path, "--work", work, "--output", output)
            return 0
        start_idx = stages.index(start)
        print("  [simulate] 续跑起点：%s（已完成阶段跳过）" % start)
    else:
        start_idx = 0

    print("== [simulate] 4/4 逐阶段执行：执行 → charge → checkpoint → flush ==")
    for stage in stages[start_idx:]:
        if args.fail_at == stage:
            print("!! [simulate] 模拟崩溃：在阶段 %s 前中断（exit 3）。现场已保留在 %s" % (stage, work))
            return 3
        info = est[stage]
        print("-- 阶段 %s（est_requests=%d）--" % (stage, info["est_requests"]))
        out_path = execute_stage(stage, work, case, plan, output)
        secs = float(info.get("est_seconds", 5.0))  # 模拟墙钟，不真正等待
        if info["est_requests"] or secs:
            run_cli("budget_ledger.py", "--work", work, "charge", "--stage", stage,
                    "--requests", info["est_requests"], "--seconds", secs,
                    "--note", "模拟消耗（合成示例）")
        deps = [os.path.join(work, est[d]["output"]) for d in info.get("deps", [])
                if est.get(d, {}).get("output")]
        run_cli("checkpoint.py", "--work", work, "record", "--stage", stage,
                "--inputs", ",".join(deps), "--outputs", out_path)
        run_cli("flush_partial.py", "--case", case_path, "--work", work, "--output", output)

    print("== [simulate] 运行完成，最终落盘 ==")
    run_cli("flush_partial.py", "--case", case_path, "--work", work, "--output", output)
    run_cli("budget_ledger.py", "--work", work, "status")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("[simulate] 致命错误: %r" % e, file=sys.stderr)
        sys.exit(3)
