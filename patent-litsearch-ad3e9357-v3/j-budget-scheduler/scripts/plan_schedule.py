#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_schedule.py — 确定性贪心调度器。

读取 task_queue.json + budget_state.json + scheduling_policy.json，输出 plan.json。
规则（详见 references/scheduling_rules.md）：
  R0  第 0 步永远是「诚实部分骨架」检查点写入——从第一分钟起就存在可交付物。
  R1  强制（mandatory）任务优先层。
  R2  同层内按 priority / 归一化成本 之比贪心，平手按 priority 降序、id 升序。
  R3  任一维剩余预算低于 policy.degrade_threshold → 立即进入降级计划。
  R4  成本未知的任务使用 policy.default_cost，并把安全边际放宽为 unknown_cost_margin。
  R5  存在不可调度的强制任务 → 转入降级计划（而非硬失败）。
  R6  依赖被跳过的任务连带跳过并注明原因。
  R7  依赖序：被依赖者必须先于依赖者调度。

确定性：同一输入必得同一 plan.json（除 generated_at 时间戳外）。
退出码：0 正常；1 违反（预算连降级计划都无法容纳）；2 用法错误。
仅使用 Python 标准库。
"""
import argparse
import datetime
import json
import sys

DIMS = ("requests", "seconds", "tokens")
EPS = 1e-9


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_id_list(path):
    if not path:
        return []
    data = load_json(path)
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict) and "completed" in data:
        return [str(x) for x in data["completed"]]
    return []


def norm_cost(cost, budget):
    return sum(cost[d] / max(float(budget[d]), EPS) for d in DIMS)


def effective_cost(item, policy):
    """返回 (cost, unknown_dims)。缺失维度用 default_cost 补齐并标记未知。"""
    default = policy.get("default_cost", {"requests": 4, "seconds": 60, "tokens": 3000})
    est = item.get("est_cost") or {}
    cost, unknown = {}, []
    for d in DIMS:
        if d in est and est[d] is not None:
            cost[d] = float(est[d])
        else:
            cost[d] = float(default.get(d, 0))
            unknown.append(d)
    return cost, unknown


def fits(cost, remaining, margin):
    return all(cost[d] * margin <= remaining[d] for d in DIMS)


def build_degrade_plan(step0, dg_cost, pending_items, skipped, state, trigger_rule,
                       trigger_note):
    step1 = {
        "seq": 1,
        "id": "__degrade__",
        "kind": "degrade_write",
        "rule": trigger_rule,
        "cost": dg_cost,
        "note": trigger_note + "；仅填写 output_contract 强制字段，其余置 null 并记录 "
                              "uncertainty，输出 degradation_report.json",
    }
    all_skipped = list(skipped)
    known = {s["id"] for s in all_skipped}
    for it in pending_items:
        if it["id"] not in known:
            all_skipped.append({
                "id": it["id"],
                "mandatory": bool(it.get("mandatory", False)),
                "reason": trigger_rule + ": 降级模式，整体放弃该项核验",
            })
    return {
        "version": 1,
        "mode": "degrade",
        "generated_at": now_iso(),
        "budget_state": {"remaining": state["remaining"], "budget": state["budget"]},
        "steps": [step0, step1],
        "skipped": sorted(all_skipped, key=lambda s: s["id"]),
        "rules": [trigger_rule, "R0-checkpoint-first"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="预算内确定性贪心调度器")
    ap.add_argument("--queue", required=True, help="task_queue.json")
    ap.add_argument("--state", required=True, help="budget_state.json（由账本重算）")
    ap.add_argument("--policy", required=True, help="scheduling_policy.json")
    ap.add_argument("--completed", help="已完成任务 id 列表（JSON 数组文件）")
    ap.add_argument("--out", required=True, help="plan.json 输出路径")
    args = ap.parse_args(argv)

    try:
        queue = load_json(args.queue)
        state = load_json(args.state)
        policy = load_json(args.policy)
    except (ValueError, OSError) as exc:
        print("错误：输入文件不可读或不是合法 JSON：%s" % exc, file=sys.stderr)
        return 2

    items = queue.get("items", []) if isinstance(queue, dict) else list(queue)
    for key in ("budget", "remaining"):
        if key not in state:
            print("错误：budget_state.json 缺少 %s" % key, file=sys.stderr)
            return 2
    budget = state["budget"]
    remaining = {d: float(state["remaining"].get(d, 0)) for d in DIMS}

    th = policy.get("degrade_threshold", {"requests": 8, "seconds": 120, "tokens": 4096})
    margin = float(policy.get("safety_margin", 1.15))
    unk_margin = float(policy.get("unknown_cost_margin", 1.5))
    ck_cost = {d: float(policy.get("checkpoint_cost", {}).get(d, 0)) for d in DIMS}
    dg_cost = {d: float(policy.get("degrade_cost", {}).get(d, 0)) for d in DIMS}

    completed = set(load_id_list(args.completed))
    pending = [it for it in items if it.get("id") not in completed]
    by_id = {it.get("id"): it for it in items}

    step0 = {
        "seq": 0,
        "id": "__checkpoint__",
        "kind": "checkpoint_write",
        "rule": "R0-checkpoint-first",
        "cost": ck_cost,
        "note": "写入诚实部分骨架 result.json 草稿（未填字段=null + uncertainty 占位），"
                "保证从第一分钟起存在可交付物",
    }

    # 预算连「检查点 + 降级报告」都容纳不下 → 硬失败。
    min_need = {d: ck_cost[d] + dg_cost[d] for d in DIMS}
    if not fits(min_need, remaining, 1.0):
        print("违反：剩余预算 %s 不足以执行最低降级计划（需要 %s），拒绝生成计划。"
              % (remaining, min_need), file=sys.stderr)
        return 1

    # R3：剩余低于阈值 → 立即降级。
    below = [d for d in DIMS if remaining[d] < float(th.get(d, 0))]
    if below:
        plan = build_degrade_plan(
            step0, dg_cost, pending, [], state, "R3-degrade-threshold",
            "剩余预算维度 %s 低于阈值 %s" % (below, th))
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        print(json.dumps({"mode": "degrade", "reason": "R3", "below": below,
                          "plan": args.out}, ensure_ascii=False))
        return 0

    # 正常贪心调度。
    rem = {d: remaining[d] - ck_cost[d] for d in DIMS}
    scheduled_ids = set(completed)
    steps = [step0]
    skipped = {}
    rules_used = {"R0-checkpoint-first"}

    while True:
        # R6：依赖被跳过或不存在的任务连带跳过。
        progressed_skip = True
        while progressed_skip:
            progressed_skip = False
            for it in pending:
                iid = it.get("id")
                if iid in scheduled_ids or iid in skipped:
                    continue
                for dep in it.get("deps", []):
                    if dep in skipped:
                        skipped[iid] = {"reason": "R6-dependency-skipped:%s" % dep,
                                        "mandatory": bool(it.get("mandatory", False))}
                        rules_used.add("R6-dependency-skipped")
                        progressed_skip = True
                        break
                    if dep not in by_id:
                        skipped[iid] = {"reason": "R6-dependency-unknown:%s" % dep,
                                        "mandatory": bool(it.get("mandatory", False))}
                        rules_used.add("R6-dependency-skipped")
                        progressed_skip = True
                        break

        cands = [it for it in pending
                 if it.get("id") not in scheduled_ids
                 and it.get("id") not in skipped
                 and all(d in scheduled_ids for d in it.get("deps", []))]
        if not cands:
            break

        def sort_key(it):
            cost, _ = effective_cost(it, policy)
            score = float(it.get("priority", 0)) / max(norm_cost(cost, budget), EPS)
            return (0 if it.get("mandatory") else 1, -score,
                    -float(it.get("priority", 0)), str(it.get("id")))

        cands.sort(key=sort_key)
        placed = False
        for it in cands:
            iid = it.get("id")
            cost, unknown = effective_cost(it, policy)
            m = unk_margin if unknown else margin
            if fits(cost, rem, m):
                rule = "R1-mandatory-first" if it.get("mandatory") else "R2-priority-cost-ratio"
                if unknown:
                    rule += "+R4-unknown-cost-default"
                rules_used.add(rule.split("+")[0])
                if unknown:
                    rules_used.add("R4-unknown-cost-default")
                steps.append({
                    "seq": len(steps),
                    "id": iid,
                    "kind": it.get("kind", "verify"),
                    "rule": rule,
                    "priority": it.get("priority", 0),
                    "cost": {d: cost[d] for d in DIMS},
                    "margin_applied": m,
                    "deps": list(it.get("deps", [])),
                    "covers": list(it.get("covers", [])),
                })
                rules_used.add("R7-dependency-order")
                for d in DIMS:
                    rem[d] -= cost[d]
                scheduled_ids.add(iid)
                placed = True
                break
            else:
                skipped[iid] = {
                    "reason": "budget-insufficient: 估计成本 %s×%.2f 超出剩余 %s"
                              % ({d: cost[d] for d in DIMS}, m,
                                 {d: round(rem[d], 2) for d in DIMS}),
                    "mandatory": bool(it.get("mandatory", False)),
                }
        if not placed:
            break

    # R5：强制任务未能调度 → 转入降级而非交付缺失强制字段的结果。
    mand_lost = [iid for iid, s in skipped.items() if s.get("mandatory")]
    if mand_lost:
        plan = build_degrade_plan(
            step0, dg_cost, pending,
            [{"id": iid, "mandatory": s.get("mandatory", False), "reason": s["reason"]}
             for iid, s in skipped.items()],
            state, "R5-mandatory-unschedulable",
            "强制任务 %s 在剩余预算内不可调度" % sorted(mand_lost))
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        print(json.dumps({"mode": "degrade", "reason": "R5",
                          "mandatory_unschedulable": sorted(mand_lost),
                          "plan": args.out}, ensure_ascii=False))
        return 0

    plan = {
        "version": 1,
        "mode": "normal",
        "generated_at": now_iso(),
        "budget_state": {"remaining": state["remaining"], "budget": state["budget"]},
        "steps": steps,
        "skipped": sorted(
            [{"id": iid, "mandatory": s.get("mandatory", False), "reason": s["reason"]}
             for iid, s in skipped.items()],
            key=lambda s: s["id"]),
        "projected_remaining_after_plan": {d: round(rem[d], 2) for d in DIMS},
        "rules": sorted(rules_used),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"mode": "normal", "steps": len(steps),
                      "skipped": len(skipped), "plan": args.out},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
