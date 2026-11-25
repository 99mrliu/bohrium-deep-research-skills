#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flush_partial.py — 增量落盘：把当前最好结果刷进 <output>/result.json

每阶段结束后调用一次。任何时刻中断，/app/output/result.json 都是合法交付：
- output_contract 要求的字段一个不少；填不了的填 null 并在 uncertainty 说明；
- status 诚实：in_progress（运行中）/ completed（启用阶段全部完成且非 L3）/
  partial（L3 最小交付，或运行被迫终止时未满完成条件）；
- 降级档位与预算台账摘要写入 scheduler 元信息块（合同外附加字段，不删合同字段）。

退出码：0 成功；2 用法/输入错误；3 运行时失败。
幂等：结果完全由 <work> 当前产物决定，重复执行得到同一 result.json。
仅使用 Python 标准库。本脚本只做组装与诚实标注，不生成任何判定内容。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT_CASE = os.environ.get("BRG_CASE", "/input/case.json")
DEFAULT_WORK = os.environ.get("BRG_WORK", "/app/work")
DEFAULT_OUTPUT = os.environ.get("BRG_OUTPUT", "/app/output")

# 合同字段 → 提供它的工作产物（缺失则填 null 并说明）
FIELD_SOURCES = {
    "decisions": "decisions.json",
    "screening_summary": None,   # 由 inventory + decisions 汇总生成
    "dedup_report": "dedup_report.json",
    "sources": None,             # 由 inventory 提取
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        pass
    return rows


def wpath(work, name):
    return os.path.join(work, name)


def build_result(case, work, status_override, final):
    plan = load_json(wpath(work, "run_plan.json")) or {}
    level = plan.get("selected_level", "L0")
    enabled = [p.get("name") for p in plan.get("phases", [])]
    cp = load_json(wpath(work, "checkpoint.json")) or {"order": [], "stages": {}}
    done = set((cp.get("stages") or {}).keys())
    ledger = load_json(wpath(work, "budget_ledger.json")) or {}

    contract = ((case.get("output_contract") or {}).get("required_fields")
                or ["case_id", "status", "decisions", "screening_summary",
                    "dedup_report", "sources", "uncertainty", "change_records", "notes"])

    inventory = load_json(wpath(work, "inventory.json"))
    decisions = load_json(wpath(work, "decisions.json"))
    dedup = load_json(wpath(work, "dedup_report.json"))

    uncertainty, notes = [], []

    # ---- 汇总类字段 ----
    sources = None
    if inventory:
        sources = inventory.get("sources")
    summary = None
    if inventory:
        summary = {"total_records": inventory.get("total_records")}
        if decisions:
            dl = decisions.get("decisions") or []
            summary["decided"] = len(dl)
            for d in dl:
                key = {"include": "included", "exclude": "excluded"}.get(d.get("decision"), "uncertain")
                summary[key] = summary.get(key, 0) + 1
        else:
            uncertainty.append("decisions 尚未生成：判定阶段未完成，计数仅含 total_records。")

    available = {
        "case_id": case.get("case_id"),
        "decisions": (decisions or {}).get("decisions"),
        "screening_summary": summary,
        "dedup_report": dedup,
        "sources": sources,
        "uncertainty": uncertainty,   # 占位，最后统一回填
        "change_records": load_jsonl(wpath(work, "change_records.jsonl")),
        "notes": notes,
    }

    # ---- 缺失字段诚实标注 ----
    stage_of_field = {"decisions": "decide", "dedup_report": "dedupe",
                      "sources": "inventory", "screening_summary": "inventory"}
    for field in contract:
        if field in ("case_id", "status", "uncertainty", "change_records", "notes"):
            continue
        val = available.get(field)
        if val is None:
            stage = stage_of_field.get(field, "?")
            if enabled and stage not in enabled:
                reason = "当前档位 %s 未启用 %s 阶段" % (level, stage)
            elif stage not in done:
                reason = "%s 阶段尚未完成" % stage
            else:
                reason = "%s 阶段产物缺失" % stage
            uncertainty.append("字段 %s 为 null：%s。" % (field, reason))
            available[field] = None

    # ---- 降级诚实表述 ----
    if level != "L0":
        uncertainty.append(
            "本次运行处于降级档位 %s：%s。缩减的范围不得以任何形式声称已完成。"
            % (level, plan.get("level_reason", "预算约束").rstrip("。")))
    if decisions:
        undecided = [d.get("record_id") for d in (decisions.get("decisions") or [])
                     if d.get("decision") == "uncertain"]
        if undecided:
            uncertainty.append("以下记录判为 uncertain，需人工复核（本调度器不做内容判定）：%s。"
                               % "、".join(str(r) for r in undecided))

    # ---- status 判定 ----
    finished = "final_check" in done
    if status_override != "auto":
        status = status_override
    elif level == "L3":
        status = "partial"   # L3 按定义就是最小诚实 partial
    elif finished:
        status = "completed"
    elif final:
        status = "partial"   # 运行终止但未完成：诚实 partial
    else:
        status = "in_progress"

    notes.append("调度器：budget-run-governor；档位=%s；判定批量=%s；本文件由 flush_partial.py 增量落盘，"
                 "任何时刻中断均为合法交付。" % (level, plan.get("batch_size")))
    notes.append("边界声明：本调度器只调度执行过程与预算，不含任何判定内容、诊断分析或渲染结论。")

    events = ledger.get("events", []) if ledger else []
    result = {"status": status}
    for field in contract:
        if field in ("status",):
            continue
        if field == "uncertainty":
            result["uncertainty"] = uncertainty
        elif field == "notes":
            result["notes"] = notes
        elif field in available:
            result[field] = available[field]
        else:
            result[field] = None
            uncertainty.append("字段 %s 为 null：调度器无法从现有产物推导该合同字段。" % field)
    result["scheduler"] = {
        "skill": "budget-run-governor",
        "level": level,
        "flushed_at": now_iso(),
        "completed_stages": cp.get("order", []),
        "pending_stages": [s for s in enabled if s not in done],
        "ledger": {
            "spent_requests": sum(e.get("requests", 0) for e in events),
            "budget_requests": ledger.get("budget_requests"),
            "reserve_requests": ledger.get("reserve_requests"),
            "elapsed_seconds": round(sum(e.get("seconds", 0.0) for e in events), 1),
            "budget_seconds": ledger.get("budget_seconds"),
        },
    }
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="把当前最好结果增量落盘到 result.json")
    ap.add_argument("--case", default=DEFAULT_CASE)
    ap.add_argument("--work", default=DEFAULT_WORK)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--status", choices=["auto", "in_progress", "partial", "completed"],
                    default="auto", help="默认 auto：按检查点与档位诚实推导")
    ap.add_argument("--final", action="store_true",
                    help="标记运行已终止：未完成时状态落为 partial 而非 in_progress")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.case):
        print("[flush] 错误：case.json 不存在: %s" % args.case, file=sys.stderr)
        return 2
    case = load_json(args.case)
    if case is None:
        print("[flush] 错误：case.json 解析失败。", file=sys.stderr)
        return 2

    result = build_result(case, args.work, args.status, args.final)
    os.makedirs(args.output, exist_ok=True)
    out = os.path.join(args.output, "result.json")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, out)
    print("[flush] 已落盘 %s（status=%s, level=%s, 已完成阶段=%s）"
          % (out, result["status"], result["scheduler"]["level"],
             "、".join(result["scheduler"]["completed_stages"]) or "无"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[flush] 致命错误: %r" % e, file=sys.stderr)
        sys.exit(3)
