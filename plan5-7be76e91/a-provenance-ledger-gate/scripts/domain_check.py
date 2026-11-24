#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""domain_check.py — 有限参数域 / 硬约束 / 跨方案单位一致性校验
（provenance-ledger-gate 步骤 3 的第二道确定性门）

输入：
  --case    case.json，含：
              "parameter_domains": {
                  "temperature_c": {"min": 20, "max": 39},   # 区间域（min/max 可缺省其一）
                  "medium_type": ["DMEM", "RPMI-1640"]        # 枚举域
              }
              可选 "hard_constraints": {"budget_cny": .., "deadline_days": ..}
  --plans   一个或多个候选方案 JSON 文件（或含方案 JSON 的目录，递归 *.json）。
            每个方案：{"plan_id": "..",
                       "parameters": {"temperature_c": {"value": 37, "unit": "°C"}, ...},
                       "totals": {"total_cost_cny": .., "duration_days": ..}}

校验：
  1. 参数域：方案中每个出现在 parameter_domains 里的参数值必须在区间/枚举内，
     否则 violation(out_of_domain)。方案给出但域表没有的参数只记录为 no_domain（提示，不判负）。
  2. 硬约束（若 case 给出）：totals.total_cost_cny > budget_cny -> violation(over_budget)；
     totals.duration_days > deadline_days -> violation(past_deadline)。
  3. 跨方案单位一致性：同一参数名在所有方案中非空 unit 的集合若多于 1 个 ->
     violation(unit_inconsistent)。

输出 --out domain_report.json（键排序、无时间戳，双跑逐字节一致）。

退出码：0=无违例；2=输入/用法错误；3=存在违例（清单打印 stdout，报告仍写出）。
"""

import argparse
import json
import os
import sys

TOOL_VERSION = "1.0"


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("ERROR: 无法读取 %s (%s): %s" % (what, path, exc), file=sys.stderr)
        sys.exit(2)


def collect_plan_paths(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames.sort()
                for fn in sorted(filenames):
                    if fn.lower().endswith(".json"):
                        files.append(os.path.join(dirpath, fn))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("ERROR: 方案路径不存在: %s" % p, file=sys.stderr)
            sys.exit(2)
    return files


def norm_param(p):
    """参数条目统一为 (value, unit)；允许裸值写法。"""
    if isinstance(p, dict):
        return p.get("value"), p.get("unit")
    return p, None


def check_domain(field, value, domain):
    """返回违例描述字符串或 None。"""
    if isinstance(domain, dict):
        lo, hi = domain.get("min"), domain.get("max")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "值 %r 不是数值，无法落入区间域 [%r, %r]" % (value, lo, hi)
        if lo is not None and value < lo:
            return "值 %r 低于域下限 %r" % (value, lo)
        if hi is not None and value > hi:
            return "值 %r 高于域上限 %r" % (value, hi)
        return None
    if isinstance(domain, list):
        if value not in domain:
            return "值 %r 不在枚举域 %r 内" % (value, domain)
        return None
    return None  # 无法识别的域定义，不判负


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="对照 case.json 的 parameter_domains 与硬约束校验候选方案参数，并做跨方案单位一致性检查。")
    parser.add_argument("--case", required=True, help="case.json 路径")
    parser.add_argument("--plans", required=True, nargs="+",
                        help="一个或多个方案 JSON 文件，或含方案 JSON 的目录")
    parser.add_argument("--out", required=True, help="domain_report.json 输出路径")
    parser.add_argument("--note", default=None,
                        help="写入输出的备注（示例数据必须写：合成示例 / SYNTHETIC EXAMPLE）")
    args = parser.parse_args(argv)

    case = load_json(args.case, "case.json")
    domains = case.get("parameter_domains") or {}
    hard = case.get("hard_constraints") or {}
    if not isinstance(domains, dict):
        print("ERROR: case.json 的 parameter_domains 必须是对象", file=sys.stderr)
        return 2

    violations = []
    no_domain_notes = []
    units_by_field = {}
    plans_seen = []

    for path in collect_plan_paths(args.plans):
        plan = load_json(path, "方案文件")
        plan_id = str(plan.get("plan_id", os.path.basename(path)))
        plans_seen.append(plan_id)
        params = plan.get("parameters") or {}
        if not isinstance(params, dict):
            print("ERROR: 方案 %s 的 parameters 必须是对象" % plan_id, file=sys.stderr)
            return 2
        for field in sorted(params):
            value, unit = norm_param(params[field])
            if unit is not None:
                units_by_field.setdefault(field, {}).setdefault(str(unit), []).append(plan_id)
            if field in domains:
                problem = check_domain(field, value, domains[field])
                if problem:
                    violations.append({
                        "kind": "out_of_domain", "plan_id": plan_id,
                        "field": field, "value": value, "unit": unit,
                        "detail": problem,
                    })
            else:
                no_domain_notes.append({
                    "plan_id": plan_id, "field": field, "value": value, "unit": unit,
                    "detail": "该参数不在 parameter_domains 中，未做域校验",
                })
        totals = plan.get("totals") or {}
        budget = hard.get("budget_cny")
        if budget is not None and totals.get("total_cost_cny") is not None:
            if totals["total_cost_cny"] > budget:
                violations.append({
                    "kind": "over_budget", "plan_id": plan_id,
                    "field": "totals.total_cost_cny", "value": totals["total_cost_cny"],
                    "unit": "CNY",
                    "detail": "总价 %r 超过预算上限 %r" % (totals["total_cost_cny"], budget),
                })
        deadline = hard.get("deadline_days")
        if deadline is not None and totals.get("duration_days") is not None:
            if totals["duration_days"] > deadline:
                violations.append({
                    "kind": "past_deadline", "plan_id": plan_id,
                    "field": "totals.duration_days", "value": totals["duration_days"],
                    "unit": "days",
                    "detail": "工期 %r 超过期限上限 %r 天" % (totals["duration_days"], deadline),
                })

    for field in sorted(units_by_field):
        unit_set = units_by_field[field]
        if len(unit_set) > 1:
            violations.append({
                "kind": "unit_inconsistent", "plan_id": "*",
                "field": field, "value": sorted(unit_set), "unit": None,
                "detail": "同一参数跨方案单位不一致: %s" % sorted(unit_set),
            })

    report = {
        "tool": "domain_check.py",
        "tool_version": TOOL_VERSION,
        "case_file": args.case,
        "case_id": case.get("case_id"),
        "plans_checked": plans_seen,
        "parameter_domains": domains,
        "hard_constraints": hard,
        "violations": violations,
        "no_domain_notes": no_domain_notes,
        "unit_sets": {f: sorted(u) for f, u in sorted(units_by_field.items())},
        "summary": {
            "plans": len(plans_seen),
            "violations": len(violations),
            "out_of_domain": sum(1 for v in violations if v["kind"] == "out_of_domain"),
            "over_budget": sum(1 for v in violations if v["kind"] == "over_budget"),
            "past_deadline": sum(1 for v in violations if v["kind"] == "past_deadline"),
            "unit_inconsistent": sum(1 for v in violations if v["kind"] == "unit_inconsistent"),
        },
    }
    if args.note is not None:
        report["note"] = args.note

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    if violations:
        print("域校验拦截：%d 条违例：" % len(violations))
        for v in violations:
            print("VIOLATION\t%s\t%s\t%s\t%s" % (
                v["kind"], v["plan_id"], v["field"], v["detail"]))
        return 3
    print("OK domain_check: %d 个方案全部落入参数域/硬约束 -> %s"
          % (len(plans_seen), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
