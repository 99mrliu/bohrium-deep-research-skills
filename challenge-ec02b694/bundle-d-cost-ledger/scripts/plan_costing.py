#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_costing.py — 逐版本核算候选方案成本表。

输入：cost_model.json（cost_model.py 产物）+ 候选方案版本 JSON。
每个版本字段：version、runs、hours_per_run{value,unit}、samples_per_run、
replicates、consumables_per_run{value,unit}、predicted_response{value,direction,unit}。

输出 cost_sheet.json：逐版本 总机时/总耗材/总成本/总历时（工作日，含每日可用机时
预约窗口约束）/通量（样品/天），每行附 formula 与代入数字的算术痕迹；
verdict：within_budget、within_deadline。

金额/时间一律 Decimal 语义，输出保留两位小数；工作日用向上取整（占用即算一天）。
任何输入不得 traceback。退出码：0 ok/partial；2 全部版本因单位不自洽被拒；
3 输入结构非法；1 内部错误（尽量落盘）。
"""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

SCHEMA_VERSION = "cost-sheet/1.0"
CENT = Decimal("0.01")


def D(x):
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def q2(d):
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def s2(d):
    return str(q2(d))


def fmt(d):
    return format(d.normalize(), "f")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:  # noqa: BLE001
        return None, "无法读取 JSON 文件 %s: %s" % (path, e)


def ceil_days(hours, daily):
    """总机时 / 每日可用机时 -> 工作日（向上取整）。返回 (days_int, ratio)。"""
    if daily is None or daily <= 0:
        return None, None
    ratio = hours / daily
    days = int(ratio.to_integral_value(rounding=ROUND_CEILING))
    return days, ratio


def cost_one_plan(plan, model_fields, model_conversions, uncertainty):
    """核算单个版本。返回 (entry_dict, rejected_bool)。"""
    version = str(plan.get("version", "<unnamed>"))
    trace = []

    def reject(reason):
        uncertainty.append("版本 %s 被拒：%s" % (version, reason))
        return ({
            "version": version,
            "status": "rejected",
            "reason": reason,
            "within_budget": False,
            "within_deadline": False,
        }, True)

    # --- 读取并校验数值 ---
    runs = D(plan.get("runs"))
    samples_per_run = D(plan.get("samples_per_run"))
    replicates = D(plan.get("replicates", 1))
    hpr_entry = plan.get("hours_per_run")
    cons_entry = plan.get("consumables_per_run")
    hpr = D(hpr_entry.get("value") if isinstance(hpr_entry, dict) else hpr_entry)
    cons = D(cons_entry.get("value") if isinstance(cons_entry, dict) else cons_entry)
    for label, v in [("runs", runs), ("samples_per_run", samples_per_run),
                     ("replicates", replicates), ("hours_per_run", hpr),
                     ("consumables_per_run", cons)]:
        if v is None or v < 0:
            return reject("字段 %s 缺失或为负数" % label)

    # --- 单位一致性：plan 单位必须等于成本模型声明单位，或经契约白名单换算 ---
    hour_unit = (hpr_entry.get("unit") if isinstance(hpr_entry, dict) else None) or "hour"
    declared_hour = model_fields.get("typical_run_hours", {}).get("unit", "hour")
    if hour_unit != declared_hour:
        conv = (model_conversions or {}).get(hour_unit)
        if isinstance(conv, dict) and conv.get("to") == declared_hour and D(conv.get("divide_by")):
            factor = D(conv["divide_by"])
            old = hpr
            hpr = hpr / factor
            trace.append("unit_conversion = hours_per_run(%s %s) / %s = %s %s （契约白名单换算，非静默）"
                         % (fmt(old), hour_unit, fmt(factor), fmt(hpr), declared_hour))
        else:
            return reject("hours_per_run 单位 %r 与声明单位 %r 不一致且无换算白名单，拒绝核算"
                          % (hour_unit, declared_hour))
    cons_unit = (cons_entry.get("unit") if isinstance(cons_entry, dict) else None) or "portion"
    declared_cons = model_fields.get("consumable_price", {}).get("unit", "CNY/portion").split("/")[-1]
    if cons_unit != declared_cons:
        return reject("consumables_per_run 单位 %r 与声明单位 %r 不一致，拒绝核算"
                      % (cons_unit, declared_cons))

    # --- 成本模型取值 ---
    def mf(name):
        e = model_fields.get(name)
        return D(e["value"]) if isinstance(e, dict) else None

    rate = mf("machine_rate")
    price = mf("consumable_price")
    daily = mf("daily_machine_hours")
    budget = mf("budget")
    deadline = mf("deadline")
    prep = mf("sample_prep_time")

    missing = [n for n, v in [("machine_rate", rate), ("consumable_price", price),
                              ("daily_machine_hours", daily), ("budget", budget),
                              ("deadline", deadline)] if v is None]
    if missing:
        return reject("成本模型缺少必需字段：%s" % ", ".join(missing))

    # --- 真实算术 ---
    total_machine_hours = runs * hpr
    trace.append("total_machine_hours = runs(%s) x hours_per_run(%s hour) = %s hour"
                 % (fmt(runs), fmt(hpr), s2(total_machine_hours)))

    machine_cost = total_machine_hours * rate
    trace.append("machine_cost = total_machine_hours(%s hour) x rate(%s 元/hour) = %s 元"
                 % (s2(total_machine_hours), fmt(rate), s2(machine_cost)))

    total_consumables = runs * cons
    trace.append("total_consumables = runs(%s) x consumables_per_run(%s 份) = %s 份"
                 % (fmt(runs), fmt(cons), s2(total_consumables)))

    consumable_cost = total_consumables * price
    trace.append("consumable_cost = total_consumables(%s 份) x price(%s 元/份) = %s 元"
                 % (s2(total_consumables), fmt(price), s2(consumable_cost)))

    total_cost = machine_cost + consumable_cost
    trace.append("total_cost = machine_cost(%s 元) + consumable_cost(%s 元) = %s 元"
                 % (s2(machine_cost), s2(consumable_cost), s2(total_cost)))

    days, ratio = ceil_days(total_machine_hours, daily)
    trace.append("total_days = ceil(total_machine_hours(%s hour) / daily_machine_hours(%s hour/day)) "
                 "= ceil(%s) = %d 工作日" % (s2(total_machine_hours), fmt(daily),
                                            str(ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                                            days))

    total_samples = runs * samples_per_run * replicates
    trace.append("total_samples = runs(%s) x samples_per_run(%s) x replicates(%s) = %s 样品"
                 % (fmt(runs), fmt(samples_per_run), fmt(replicates), fmt(total_samples)))

    throughput = (total_samples / Decimal(days)) if days else Decimal(0)
    trace.append("throughput = total_samples(%s) / total_days(%d) = %s 样品/天"
                 % (fmt(total_samples), days, s2(throughput)))

    prep_hours = None
    if prep is not None:
        prep_hours = total_samples * prep
        trace.append("total_prep_hours = total_samples(%s) x sample_prep_time(%s hour/sample) = %s hour"
                     "（样品制备时间，单列展示；历时工作日按机时预约口径计算）"
                     % (fmt(total_samples), fmt(prep), s2(prep_hours)))
    else:
        trace.append("total_prep_hours = 未提供 sample_prep_time，跳过（已记入 uncertainty）")
        uncertainty.append("版本 %s：成本模型缺 sample_prep_time，样品制备时间未核算。" % version)

    within_budget = total_cost <= budget
    within_deadline = days <= int(deadline)
    trace.append("within_budget = total_cost(%s 元) <= budget(%s 元) -> %s"
                 % (s2(total_cost), fmt(budget), str(within_budget).lower()))
    trace.append("within_deadline = total_days(%d) <= deadline(%s 工作日) -> %s"
                 % (days, fmt(deadline), str(within_deadline).lower()))

    entry = {
        "version": version,
        "status": "ok",
        "total_machine_hours": s2(total_machine_hours),
        "total_consumables": s2(total_consumables),
        "machine_cost": s2(machine_cost),
        "consumable_cost": s2(consumable_cost),
        "total_cost": s2(total_cost),
        "total_days": days,
        "total_samples": str(int(total_samples)) if total_samples == total_samples.to_integral_value() else fmt(total_samples),
        "throughput_samples_per_day": s2(throughput),
        "total_prep_hours": s2(prep_hours) if prep_hours is not None else None,
        "duration_basis": "machine_hours_only（预约窗口约束；样品制备单列）",
        "within_budget": within_budget,
        "within_deadline": within_deadline,
        "predicted_response": plan.get("predicted_response"),
        "trace": trace,
    }
    return (entry, False)


def main():
    ap = argparse.ArgumentParser(description="逐版本成本核算")
    ap.add_argument("--cost-model", required=True, help="cost_model.json 路径")
    ap.add_argument("--plans", required=True, help="候选方案版本 JSON 路径")
    ap.add_argument("--out", required=True, help="输出 cost_sheet.json 路径")
    args = ap.parse_args()

    out_path = Path(args.out)
    uncertainty = []

    def emit(payload, code):
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"status": "error", "error": "无法写输出: %s" % e},
                             ensure_ascii=False))
        return code

    try:
        model, err = load_json(args.cost_model)
        if err:
            return emit({"schema_version": SCHEMA_VERSION, "status": "error",
                         "error": err, "uncertainty": [err]}, 3)
        if not isinstance(model, dict) or model.get("status") == "refused":
            reason = (model or {}).get("reason", "成本模型不可用或被拒绝")
            return emit({"schema_version": SCHEMA_VERSION, "status": "refused",
                         "reason": "上游 cost_model 不可用：%s" % reason,
                         "uncertainty": [reason]}, 3)
        model_fields = model.get("fields") or {}
        model_conversions = model.get("declared_conversions") or {}
        if model.get("status") == "partial":
            uncertainty.append("上游 cost_model 为 partial：%s"
                               % "; ".join(model.get("uncertainty", [])))

        plans_data, err = load_json(args.plans)
        if err:
            return emit({"schema_version": SCHEMA_VERSION, "status": "error",
                         "error": err, "uncertainty": uncertainty + [err]}, 3)
        plans = (plans_data or {}).get("plans") if isinstance(plans_data, dict) else None
        if not isinstance(plans, list):
            return emit({"schema_version": SCHEMA_VERSION, "status": "error",
                         "error": "plans JSON 缺少 plans 数组", "uncertainty": uncertainty}, 3)
        if len(plans) == 0:
            uncertainty.append("方案版本为空：无任何候选方案可核算。")
            return emit({"schema_version": SCHEMA_VERSION, "status": "partial",
                         "budget": (model_fields.get("budget") or {}).get("value"),
                         "deadline_working_days": (model_fields.get("deadline") or {}).get("value"),
                         "plans": [], "uncertainty": uncertainty}, 0)

        entries, n_rejected = [], 0
        for plan in plans:
            if not isinstance(plan, dict):
                uncertainty.append("跳过非法方案条目（非对象）：%r" % (plan,))
                continue
            entry, rejected = cost_one_plan(plan, model_fields, model_conversions, uncertainty)
            entries.append(entry)
            n_rejected += 1 if rejected else 0

        if entries and n_rejected == len(entries):
            return emit({"schema_version": SCHEMA_VERSION, "status": "refused",
                         "reason": "全部版本因单位不自洽或数据非法被拒。",
                         "plans": entries, "uncertainty": uncertainty}, 2)

        status = "ok" if n_rejected == 0 else "partial"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "budget": (model_fields.get("budget") or {}).get("value"),
            "deadline_working_days": (model_fields.get("deadline") or {}).get("value"),
            "plans": entries,
            "uncertainty": uncertainty,
        }
        return emit(payload, 0)
    except Exception as e:  # noqa: BLE001
        return emit({"schema_version": SCHEMA_VERSION, "status": "error",
                     "error": "内部错误：%s: %s" % (type(e).__name__, e),
                     "uncertainty": uncertainty}, 1)


if __name__ == "__main__":
    sys.exit(main())
