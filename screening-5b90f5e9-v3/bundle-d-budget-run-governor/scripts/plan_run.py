#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_run.py — budget-run-governor 运行计划生成器

读取 case.json，把案例工作分解为阶段 DAG（盘点→骨架→归一→去重→判定→诊断→填充→终检），
按题录规模 N 估算模型请求数与墙钟时间，预先选择降级档位（L0–L3），
写出 <work>/run_plan.json。

退出码：0 成功；2 用法/输入错误；3 运行时失败。
幂等：同一输入重复运行覆盖生成同一计划（除时间戳）。
仅使用 Python 标准库。本脚本只调度执行过程与预算，不做任何判定内容。
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

DEFAULT_CASE = os.environ.get("BRG_CASE", "/input/case.json")
DEFAULT_WORK = os.environ.get("BRG_WORK", "/app/work")
DEFAULT_BUDGET_REQUESTS = 64
DEFAULT_BUDGET_SECONDS = 900

RESERVE_REQUESTS = 2        # 预留：fill(1) + final_check(1)，任何情况下不得挪用
SECONDS_PER_REQUEST = 12.0  # 单次模型请求的经验墙钟估值（含排队与解析）
STAGE_OVERHEAD_SECONDS = 5.0
RESPONSE_TOKEN_LIMIT = 16384   # 单次响应 token 上限
TOKENS_PER_DECISION = 700      # 单条判定 JSON 的经验 token 估值

# 阶段 DAG（拓扑序）。kind: deterministic=不耗模型请求；model=耗模型请求
PHASES = [
    ("inventory",   [],                     "deterministic"),
    ("scaffold",    ["inventory"],          "model"),
    ("normalize",   ["inventory"],          "deterministic"),
    ("dedupe",      ["normalize"],          "model"),
    ("decide",      ["dedupe", "scaffold"], "model"),
    ("diagnose",    ["decide"],             "model"),
    ("fill",        ["diagnose"],           "model"),
    ("final_check", ["fill"],               "model"),
]

STAGE_OUTPUT = {
    "inventory":   "inventory.json",
    "scaffold":    "skeleton.json",
    "normalize":   "normalized.json",
    "dedupe":      "dedup_report.json",
    "decide":      "decisions.json",
    "diagnose":    "diagnostics.json",
    "fill":        "fill_notes.json",
    "final_check": "final_check.json",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def choose_batch(n):
    """规模自适应判定批量：N 大调大批量，N 小走小批量深备注。"""
    if n <= 15:
        batch = 3
    elif n <= 40:
        batch = 5
    elif n <= 100:
        batch = 8
    else:
        batch = 12
    # 单次响应 16384 tokens 约束：批量判定输出必须装得下
    token_cap = max(1, RESPONSE_TOKEN_LIMIT // TOKENS_PER_DECISION)
    return min(batch, token_cap)


def enabled_stages(level):
    """各降级档位启用的阶段集合。L3 为最小诚实 partial：仅盘点+骨架+填充+终检。"""
    all_stages = [p[0] for p in PHASES]
    if level in ("L0", "L1"):
        return list(all_stages)
    if level == "L2":
        return [s for s in all_stages if s != "diagnose"]
    return ["inventory", "scaffold", "fill", "final_check"]  # L3


def stage_est_requests(stage, level, n, batch):
    if stage == "scaffold":
        return 1
    if stage == "dedupe":
        return 1 if n > 0 else 0
    if stage == "decide":
        return math.ceil(n / batch) if n > 0 else 0
    if stage == "diagnose":
        if level == "L0":
            return n
        if level == "L1":
            return math.ceil(n / 3)  # 仅深度诊断被标记/不确定的子集（估算 1/3）
        return 0
    if stage == "fill":
        return 1
    if stage == "final_check":
        return 1
    return 0  # inventory / normalize 为确定性处理


def build_plan(case, budget_requests, budget_seconds):
    records = case.get("records") or []
    n = len(records)
    batch = choose_batch(n)
    available = budget_requests - RESERVE_REQUESTS

    selected, selected_est, selected_secs, level_reason = None, None, None, None
    for level in ("L0", "L1", "L2", "L3"):
        stages = enabled_stages(level)
        est = {s: stage_est_requests(s, level, n, batch) for s in stages}
        total = sum(est.values())
        secs = total * SECONDS_PER_REQUEST + STAGE_OVERHEAD_SECONDS * len(stages)
        fits_req = total <= available
        fits_time = secs <= budget_seconds * 0.9
        if fits_req and fits_time:
            selected, selected_est, selected_secs = level, est, secs
            level_reason = (
                "预估 %d 次模型请求 / %.0f 秒，在预算（%d 次可用，预留 %d 次）"
                "与 90%% 墙钟线内，选择最完整可行档位 %s。"
                % (total, secs, available, RESERVE_REQUESTS, level)
            )
            break
    if selected is None:  # 理论上 L3 必然可行；兜底
        selected = "L3"
        stages = enabled_stages("L3")
        selected_est = {s: stage_est_requests(s, "L3", n, batch) for s in stages}
        selected_secs = sum(selected_est.values()) * SECONDS_PER_REQUEST
        level_reason = "任何更高档位均超预算，直接以 L3 最小诚实 partial 交付。"

    stages = enabled_stages(selected)
    phases = []
    for name, deps, kind in PHASES:
        if name not in stages:
            continue
        eff_deps = [d for d in deps if d in stages]
        req = selected_est.get(name, 0)
        phases.append({
            "name": name,
            "deps": eff_deps,
            "kind": kind,
            "est_requests": req,
            "est_seconds": round(req * SECONDS_PER_REQUEST + STAGE_OVERHEAD_SECONDS, 1),
            "output": STAGE_OUTPUT.get(name),
        })

    risk_points = []
    flagged = [r for r in records if isinstance(r, dict) and r.get("fixture_note")]
    if flagged:
        risk_points.append(
            "输入含组织方标注的夹具记录（合成重复导出/冲突双人意见）共 %d 条："
            "dedupe 阶段必须保守合并并写 change_records，不得静默丢弃。" % len(flagged))
    if n > 40:
        risk_points.append("N=%d 较大：decide 阶段为预算主要消耗点，批量已调至 %d。" % (n, batch))
    if selected != "L0":
        risk_points.append("已预选降级档位 %s：result.json 必须如实反映缩减范围。" % selected)
    if selected_secs > budget_seconds * 0.75:
        risk_points.append("预估墙钟超过预算 75%%：运行中须密切监控 ledger 的时间信号。")

    return {
        "plan_version": "1.0",
        "created_at": now_iso(),
        "case_id": case.get("case_id"),
        "record_count": n,
        "batch_size": batch,
        "budget": {
            "requests": budget_requests,
            "seconds": budget_seconds,
            "reserve_requests": RESERVE_REQUESTS,
            "seconds_per_request_est": SECONDS_PER_REQUEST,
            "response_token_limit": RESPONSE_TOKEN_LIMIT,
        },
        "selected_level": selected,
        "level_reason": level_reason,
        "phases": phases,
        "est_total_requests": sum(p["est_requests"] for p in phases),
        "est_total_seconds": round(sum(p["est_seconds"] for p in phases), 1),
        "risk_points": risk_points,
        "degradation_policy": "见 references/degradation_ladder.md；运行中由 budget_ledger.py status 发出降级信号。",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成预算感知运行计划 run_plan.json")
    ap.add_argument("--case", default=DEFAULT_CASE, help="case.json 路径（默认 %(default)s，可用 BRG_CASE 覆盖）")
    ap.add_argument("--work", default=DEFAULT_WORK, help="中间产物目录（默认 %(default)s，可用 BRG_WORK 覆盖）")
    ap.add_argument("--budget-requests", type=int, default=DEFAULT_BUDGET_REQUESTS)
    ap.add_argument("--budget-seconds", type=float, default=DEFAULT_BUDGET_SECONDS)
    args = ap.parse_args(argv)

    if not os.path.isfile(args.case):
        print("[plan_run] 错误：case.json 不存在: %s" % args.case, file=sys.stderr)
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("[plan_run] 错误：case.json 解析失败: %s" % e, file=sys.stderr)
        return 2
    if not isinstance(case.get("records"), list):
        print("[plan_run] 错误：case.json 缺少 records 数组。", file=sys.stderr)
        return 2
    if args.budget_requests <= RESERVE_REQUESTS:
        print("[plan_run] 错误：预算请求数必须大于预留数 %d。" % RESERVE_REQUESTS, file=sys.stderr)
        return 2

    plan = build_plan(case, args.budget_requests, args.budget_seconds)
    os.makedirs(args.work, exist_ok=True)
    out = os.path.join(args.work, "run_plan.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("[plan_run] 已写出 %s" % out)
    print("[plan_run] N=%d batch=%d 档位=%s 预估请求=%d/%d 预估秒数=%.0f/%d"
          % (plan["record_count"], plan["batch_size"], plan["selected_level"],
             plan["est_total_requests"], args.budget_requests,
             plan["est_total_seconds"], args.budget_seconds))
    for r in plan["risk_points"]:
        print("[plan_run] 风险点: %s" % r)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 顶层兜底：任何意外都以退出码 3 失败，绝不留半写状态误导
        print("[plan_run] 致命错误: %r" % e, file=sys.stderr)
        sys.exit(3)
