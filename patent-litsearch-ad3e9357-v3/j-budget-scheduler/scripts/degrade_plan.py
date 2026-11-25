#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""degrade_plan.py — 止损 / 降级计划生成器。

输入当前 budget_state.json、output_contract（case 文件或裸契约）、task_queue.json
与已完成 id 列表；输出：
  - degrade_plan.json：每个契约字段的处置（强制字段 → fill-partial；
    非强制字段 → null + uncertainty 条目）；
  - degradation_report.json：逐项列出被放弃的核验、原因、后果，
    以及哪些契约字段因此置 null。

设计目标：降级是显式的、可审计的决策，绝不静默丢字段。
退出码：0 正常；1 违反（契约不含任何强制字段之外的结构性错误、输入损坏）；2 用法错误。
仅使用 Python 标准库。
"""
import argparse
import datetime
import json
import sys

DIMS = ("requests", "seconds", "tokens")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def extract_contract(obj):
    """接受整份 case 文件或裸 output_contract。"""
    if isinstance(obj, dict):
        if "output_contract" in obj:
            return obj["output_contract"]
        if "fields" in obj:
            return obj
    raise ValueError("无法从输入中定位 output_contract.fields")


def main(argv=None):
    ap = argparse.ArgumentParser(description="止损/降级计划生成器")
    ap.add_argument("--state", required=True, help="budget_state.json")
    ap.add_argument("--contract", required=True, help="case.json 或 output_contract JSON")
    ap.add_argument("--queue", required=True, help="task_queue.json")
    ap.add_argument("--completed", help="已完成任务 id JSON 数组文件")
    ap.add_argument("--out-plan", required=True, help="degrade_plan.json 输出路径")
    ap.add_argument("--report", required=True, help="degradation_report.json 输出路径")
    args = ap.parse_args(argv)

    try:
        state = load_json(args.state)
        contract = extract_contract(load_json(args.contract))
        queue = load_json(args.queue)
        completed = set(str(x) for x in load_json(args.completed)) if args.completed else set()
    except (ValueError, OSError) as exc:
        print("错误：输入不可读或结构非法：%s" % exc, file=sys.stderr)
        return 2

    fields = contract.get("fields", {})
    if not isinstance(fields, dict) or not fields:
        print("错误：output_contract.fields 为空或非法", file=sys.stderr)
        return 2

    items = queue.get("items", []) if isinstance(queue, dict) else list(queue)
    pending = [it for it in items if it.get("id") not in completed]
    remaining = state.get("remaining", {})
    threshold = state.get("below_threshold")

    # 被放弃核验所波及的契约字段。
    field_dropped_by = {}
    dropped = []
    for it in sorted(pending, key=lambda x: str(x.get("id"))):
        covers = list(it.get("covers", []))
        consequence = ("该项核验未执行；关联契约字段 [%s] 将置 null 并记录 uncertainty"
                       % ", ".join(covers)) if covers else \
                      "该项核验未执行；不直接关联契约字段，但整体证据覆盖度下降"
        dropped.append({
            "id": it.get("id"),
            "kind": it.get("kind", "verify"),
            "priority": it.get("priority", 0),
            "mandatory": bool(it.get("mandatory", False)),
            "reason": "degrade-mode: 剩余预算不足（remaining=%s）" % (remaining,),
            "consequence": consequence,
            "covers": covers,
        })
        for f in covers:
            field_dropped_by.setdefault(f, []).append(it.get("id"))

    field_actions = {}
    null_fields = []
    mandatory_filled = []
    for name in sorted(fields):
        spec = fields[name] or {}
        if spec.get("mandatory"):
            field_actions[name] = {
                "action": "fill-partial",
                "mandatory": True,
                "note": "强制字段：以当前已核验证据尽力填写；证据不足处在字段内"
                        "如实标注，并在 uncertainty 中登记",
            }
            mandatory_filled.append(name)
        else:
            field_actions[name] = {
                "action": "null+uncertainty",
                "mandatory": False,
                "note": "降级模式置 null；uncertainty 条目说明该字段因预算止损未核验",
            }
            null_fields.append(name)

    plan = {
        "version": 1,
        "mode": "degrade",
        "generated_at": now_iso(),
        "remaining_budget": remaining,
        "below_threshold": threshold if threshold is not None else "见 budget_state.json",
        "field_actions": field_actions,
        "rules": ["fill-mandatory-only", "null-plus-uncertainty",
                  "emit-degradation-report"],
    }
    with open(args.out_plan, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    report = {
        "version": 1,
        "generated_at": now_iso(),
        "trigger": "预算止损：剩余预算低于阈值或强制任务不可调度",
        "remaining_budget": remaining,
        "dropped_verifications": dropped,
        "dropped_count": len(dropped),
        "contract_null_fields": null_fields,
        "contract_mandatory_filled": mandatory_filled,
        "field_dropped_by": {k: field_dropped_by[k] for k in sorted(field_dropped_by)},
        "consequence_summary": (
            "共放弃 %d 项核验；%d 个非强制契约字段置 null（%s）；"
            "%d 个强制字段以部分证据填写。"
            % (len(dropped), len(null_fields),
               ", ".join(null_fields) if null_fields else "无",
               len(mandatory_filled))),
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print(json.dumps({"degrade_plan": args.out_plan, "report": args.report,
                      "dropped": len(dropped), "null_fields": len(null_fields)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
