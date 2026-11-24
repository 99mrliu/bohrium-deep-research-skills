#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pareto.py — 成本-时间 Pareto 前沿与推荐（确定性，仅标准库）。

输入为 cost_ledger.py 与 time_model.py 的真实产物（不手抄数字，避免转录误差）：
  --plan P1:ledger_P1.json:time_P1.json   （可重复，至少 2 个）

每个方案取 (plan_id, total_cost, elapsed_days, gate_status)，全部按最小化处理。

支配定义：A 支配 B 当且仅当 A.cost <= B.cost 且 A.elapsed <= B.elapsed
且至少一个严格小于。被支配方案列出全部支配者。

推荐规则（字典序，rule_source 必声明）：
  1) 先 gate：仅 gate_status == "pass" 的方案进入候选；全部不过门 ->
     诚实报告 all_infeasible，不推荐任何方案，exit 3。
  2) 再 Pareto：候选中被支配者出局，前沿进入决胜。
  3) 决胜：case.json 含 rubric.weights {cost, time}（非负、非全零）->
     加权归一化得分最小者，rule_source="case_rubric"；
     否则默认成本优先（成本最小，平手比时间，再平手按 plan_id 字典序），
     rule_source="default_cost_first"。

退出码：0=成功；2=输入/用法错误；3=质量门拦截（如全部方案不过门；产物仍写出）。
"""
import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path


def dstr(d):
    if not isinstance(d, Decimal):
        d = Decimal(d)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def to_decimal(value):
    if isinstance(value, bool):
        return None, "布尔值不是数字"
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None, "非有限数字"
        return value, None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            d = Decimal(value.strip())
        except Exception:
            return None, "无法解析为数字: %r" % value
        if not d.is_finite():
            return None, "非有限数字"
        return d, None
    return None, "非数字类型: %s" % type(value).__name__


def load_json(path, what):
    p = Path(path)
    if not p.is_file():
        sys.stdout.write("INPUT_ERROR: 找不到 %s 文件: %s\n" % (what, path))
        raise SystemExit(2)
    try:
        return json.loads(p.read_text(encoding="utf-8"), parse_float=Decimal)
    except json.JSONDecodeError as e:
        sys.stdout.write("INPUT_ERROR: %s 不是合法 JSON: %s\n" % (path, e))
        raise SystemExit(2)


def dominates(a, b):
    """a 是否支配 b（两者都是 (cost, elapsed) 的 Decimal 对）。"""
    return (a[0] <= b[0] and a[1] <= b[1]) and (a[0] < b[0] or a[1] < b[1])


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="成本-时间 Pareto 前沿、被支配分析与推荐（读取 ledger/time 真实产物）")
    ap.add_argument("--plan", action="append", required=True, metavar="ID:LEDGER:TIME",
                    help="方案三元组：plan_id:ledger_json:time_json（可重复，至少 2 个）")
    ap.add_argument("--case", help="case.json（可选；rubric.weights {cost,time} 用于决胜）")
    ap.add_argument("--out-dir", required=True, help="输出目录")
    args = ap.parse_args(argv)

    if len(args.plan) < 2:
        sys.stdout.write("INPUT_ERROR: 至少需要 2 个 --plan 才能做 Pareto 比较\n")
        return 2

    plans = []
    seen_ids = set()
    notices = []
    for spec in args.plan:
        parts = spec.split(":")
        if len(parts) != 3 or not parts[0]:
            sys.stdout.write("INPUT_ERROR: --plan 格式应为 plan_id:ledger.json:time.json，收到: %r\n"
                             % spec)
            return 2
        pid, ledger_path, time_path = parts
        if pid in seen_ids:
            sys.stdout.write("INPUT_ERROR: plan_id 重复: %s\n" % pid)
            return 2
        seen_ids.add(pid)
        ledger = load_json(ledger_path, "ledger")
        tmodel = load_json(time_path, "time_model")
        if ledger.get("artifact") != "cost_ledger":
            sys.stdout.write("INPUT_ERROR: %s 不是 cost_ledger 产物\n" % ledger_path)
            return 2
        if tmodel.get("artifact") != "time_model":
            sys.stdout.write("INPUT_ERROR: %s 不是 time_model 产物\n" % time_path)
            return 2
        for doc, path in ((ledger, ledger_path), (tmodel, time_path)):
            n = doc.get("notice")
            if isinstance(n, str) and n.strip():
                notices.append(n)
        if ledger.get("plan_id") != pid or tmodel.get("plan_id") != pid:
            sys.stdout.write("INPUT_ERROR: 方案 %s 的 ledger/time 内 plan_id 不一致（%s / %s）\n"
                             % (pid, ledger.get("plan_id"), tmodel.get("plan_id")))
            return 2
        if ledger.get("status") != "ok" or tmodel.get("status") != "ok":
            sys.stdout.write("INPUT_ERROR: 方案 %s 的 ledger/time 含缺陷（status!=ok），先修复\n"
                             % pid)
            return 2
        cost, err1 = to_decimal(ledger.get("grand_total"))
        elapsed, err2 = to_decimal(tmodel.get("elapsed_days"))
        if err1 or err2 or cost < 0 or elapsed < 0:
            sys.stdout.write("INPUT_ERROR: 方案 %s 的 total_cost/elapsed_days 非法\n" % pid)
            return 2
        gate = tmodel.get("gate_status")
        if not isinstance(gate, str) or not gate:
            sys.stdout.write("INPUT_ERROR: 方案 %s 缺 gate_status\n" % pid)
            return 2
        plans.append({"plan_id": pid, "total_cost": cost, "elapsed_days": elapsed,
                      "gate_status": gate,
                      # 只留文件名，保证产物与运行目录无关（双跑字节一致）
                      "ledger_file": Path(ledger_path).name,
                      "time_file": Path(time_path).name})

    # ---- 支配关系（对全部方案计算，客观属性与门无关）----
    for p in plans:
        p["dominated_by"] = sorted(
            q["plan_id"] for q in plans
            if q["plan_id"] != p["plan_id"]
            and dominates((q["total_cost"], q["elapsed_days"]),
                          (p["total_cost"], p["elapsed_days"])))
        p["dominated"] = bool(p["dominated_by"])
    frontier_all = sorted(p["plan_id"] for p in plans if not p["dominated"])

    # ---- 推荐（字典序：gate -> Pareto -> rubric/default）----
    candidates = [p for p in plans if p["gate_status"] == "pass"]
    gate_failed = sorted(p["plan_id"] for p in plans if p["gate_status"] != "pass")
    recommendation = None
    rule_source = None
    status_note = "ok"
    exit_code = 0

    if not candidates:
        status_note = ("all_infeasible: 全部方案未过硬约束门（%s）；"
                       "不推荐任何方案，须如实上报并组织方裁决（放宽预算/截止或补新方案）。"
                       % ", ".join(gate_failed))
        exit_code = 3
    else:
        cand_frontier = [p for p in candidates if not any(
            d in {c["plan_id"] for c in candidates} for d in p["dominated_by"])]
        # 只被「不过门方案」支配的候选仍在候选前沿上（支配者不可行，不构成威胁）
        rule_source = None
        if len(cand_frontier) == 1:
            recommendation = cand_frontier[0]["plan_id"]
            rule_source = "pareto_unique"
        else:
            weights = None
            if args.case:
                case = load_json(args.case, "case")
                if isinstance(case, dict):
                    n = case.get("_notice")
                    if isinstance(n, str) and n.strip():
                        notices.append(n)
                    w = (case.get("rubric") or {}).get("weights")
                    if isinstance(w, dict) and "cost" in w and "time" in w:
                        wc, e1 = to_decimal(w["cost"])
                        wt, e2 = to_decimal(w["time"])
                        if e1 or e2 or wc < 0 or wt < 0 or (wc == 0 and wt == 0):
                            sys.stdout.write(
                                "INPUT_ERROR: case.rubric.weights 的 cost/time 必须非负且非全零\n")
                            return 2
                        weights = (wc, wt)
            if weights is not None:
                rule_source = "case_rubric"
                wc, wt = weights
                max_c = max(p["total_cost"] for p in cand_frontier)
                max_t = max(p["elapsed_days"] for p in cand_frontier)
                scored = []
                for p in cand_frontier:
                    nc = (p["total_cost"] / max_c) if max_c > 0 else Decimal(0)
                    nt = (p["elapsed_days"] / max_t) if max_t > 0 else Decimal(0)
                    score = wc * nc + wt * nt
                    scored.append((score, p["total_cost"], p["elapsed_days"], p["plan_id"]))
                    p["rubric_score"] = dstr(score)
                scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
                recommendation = scored[0][3]
            else:
                rule_source = "default_cost_first"
                cand_frontier.sort(key=lambda p: (p["total_cost"], p["elapsed_days"],
                                                  p["plan_id"]))
                recommendation = cand_frontier[0]["plan_id"]

    result = {
        "artifact": "pareto",
        "objectives": {"total_cost": "min", "elapsed_days": "min"},
        "plans": [{
            "plan_id": p["plan_id"],
            "total_cost": dstr(p["total_cost"]),
            "elapsed_days": dstr(p["elapsed_days"]),
            "gate_status": p["gate_status"],
            "dominated": p["dominated"],
            "dominated_by": p["dominated_by"],
            "rubric_score": p.get("rubric_score"),
            "ledger_file": p["ledger_file"],
            "time_file": p["time_file"],
        } for p in sorted(plans, key=lambda x: x["plan_id"])],
        "pareto_frontier_all": frontier_all,
        "gate_failed": gate_failed,
        "recommendation": recommendation,
        "rule_source": rule_source,
        "rule_explanation": ("字典序：先 gate pass，再 Pareto 前沿，再按 %s 决胜。"
                             % (rule_source or "无（无可行方案）")),
        "status_note": status_note,
    }
    if notices:
        result["notice"] = notices[0]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pareto.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "pareto.md").write_text(render_md(result), encoding="utf-8")

    if exit_code == 3:
        sys.stdout.write("GATE_TRIGGERED (exit 3): %s\n" % status_note)
        return 3
    sys.stdout.write("OK: frontier=%s recommendation=%s rule=%s -> %s\n"
                     % (frontier_all, recommendation, rule_source, out_dir / "pareto.json"))
    return 0


def render_md(r):
    lines = []
    if r.get("notice"):
        lines.append("> " + r["notice"])
        lines.append("")
    lines.append("# 成本-时间 Pareto 分析")
    lines.append("")
    lines.append("- 目标: total_cost ↓, elapsed_days ↓")
    lines.append("- Pareto 前沿（全体方案）: %s" % ", ".join(r["pareto_frontier_all"]))
    lines.append("- 推荐: **%s**（rule_source: %s）" % (r["recommendation"] or "无",
                                                       r["rule_source"] or "无"))
    lines.append("- 规则: %s" % r["rule_explanation"])
    lines.append("- 状态: %s" % r["status_note"])
    lines.append("")
    lines.append("| 方案 | 总成本 | 自然周期(天) | 门 | 被支配 | 支配者 | rubric得分 |")
    lines.append("|------|--------|--------------|----|--------|--------|------------|")
    for p in r["plans"]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            p["plan_id"], p["total_cost"], p["elapsed_days"], p["gate_status"],
            "是" if p["dominated"] else "否",
            ", ".join(p["dominated_by"]) or "-",
            p["rubric_score"] or "-",
        ))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
