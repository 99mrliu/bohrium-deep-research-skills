#!/usr/bin/env python3
"""consistency_check.py — 阶段-产物一致性校验（bundle B 签名脚本 3）。

校验项：
  1. state.json 中标记 completed 的阶段，其产物真实存在且非空（目录须含文件）。
  2. out/result.json 含 output_contract 全部字段（缺字段=失败；
     status=in_progress 时 null 记 pending 不算失败，终态下 null 记失败）。
  3. work/change_log.json 覆盖 run_plan.json 中全部阶段（每阶段至少一条含阶段名的记录）。
输出 out/consistency_report.json；退出码 0=通过，1=存在问题。
"""
import json
import os
import sys


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def artifact_ok(path):
    if not path or not os.path.exists(path):
        return False
    if os.path.isdir(path):
        return any(os.scandir(path))
    return os.path.getsize(path) > 0


def run(work, out):
    state = load_json(os.path.join(work, "state.json"), {})
    plan = load_json(os.path.join(work, "run_plan.json"), {})
    cmap = load_json(os.path.join(work, "contract_map.json"), {})
    result = load_json(os.path.join(out, "result.json"), {})
    change_log = load_json(os.path.join(work, "change_log.json"), [])

    problems, pending_notes = [], []

    # 1. 阶段-产物一致性
    planned_artifact = {e.get("phase"): e.get("planned_artifact")
                        for e in plan.get("phases", [])}

    def resolve_planned(phase):
        p = planned_artifact.get(phase)
        if not p:
            return None
        if p.startswith("out:"):
            return os.path.join(out, p[4:])
        return os.path.join(work, p)

    phase_checks = []
    for phase, ph in state.get("phases", {}).items():
        artifact = ph.get("artifact") or resolve_planned(phase)
        exists = artifact_ok(artifact)
        if ph.get("status") == "completed":
            phase_checks.append({"phase": phase, "status": "completed",
                                 "artifact": artifact, "exists": exists})
            if not exists:
                problems.append(f"阶段 {phase} 标记 completed 但产物缺失或为空：{artifact}"
                                "（疑似中断或虚报，需重做该阶段或改回 pending）")
        else:
            phase_checks.append({"phase": phase, "status": ph.get("status", "pending"),
                                 "artifact": artifact, "exists": exists})
            if not exists:
                problems.append(f"阶段 {phase} 未完成且产物缺失（预期 {planned_artifact.get(phase)}）"
                                "——缺失阶段，需补齐后重新 check")
            else:
                pending_notes.append(f"阶段 {phase} 产物已存在但未登记 completed，"
                                     "可用 budget_ledger.py mark 补登记")

    # 2. 契约字段完备性
    contract_fields = [f["field"] for f in cmap.get("fields", [])]
    result_status = result.get("status")
    missing = [f for f in contract_fields if f not in result]
    null_fields = [f for f in contract_fields
                   if f in result and result[f] is None and f not in ("status", "case_id")]
    for f in missing:
        problems.append(f"result.json 缺少 output_contract 字段 '{f}'（漏字段不允许，null 可以）")
    if result_status == "in_progress":
        for f in null_fields:
            pending_notes.append(f"契约字段 '{f}' 暂为 null（in_progress，待 finalize 填充）")
    else:
        for f in null_fields:
            problems.append(f"终态 result.json 契约字段 '{f}' 为 null，须在 uncertainties 说明并已核实无产出途径")
    if result_status not in ("in_progress", "completed", "partial", "blocked"):
        problems.append(f"result.json status 非法：{result_status!r}")

    # 3. change_log 覆盖所有阶段
    log_text = "\n".join(str(x) for x in change_log)
    uncovered = []
    for entry in plan.get("phases", []):
        phase = entry.get("phase")
        if phase and phase not in log_text:
            uncovered.append(phase)
            problems.append(f"change_log 未覆盖阶段 {phase}（规划与执行记录均缺失）")

    completed = [c for c in phase_checks if c["status"] == "completed"]
    report = {
        "case_id": state.get("case_id") or cmap.get("case_id"),
        "ok": not problems,
        "budget": {"total": state.get("budget_total"),
                   "used": state.get("requests_used"),
                   "remaining": (state.get("budget_total", 0) or 0) - (state.get("requests_used", 0) or 0)},
        "phase_checks": phase_checks,
        "completed_phases": [c["phase"] for c in completed],
        "contract": {"fields": contract_fields, "missing": missing,
                     "null_fields": null_fields, "result_status": result_status},
        "change_log_uncovered_phases": uncovered,
        "problems": problems,
        "pending_notes": pending_notes,
    }
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "consistency_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    report = run(args.work, args.out)
    print(json.dumps({"ok": report["ok"], "problems": len(report["problems"]),
                      "completed_phases": report["completed_phases"],
                      "remaining_budget": report["budget"]["remaining"]},
                     ensure_ascii=False))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
