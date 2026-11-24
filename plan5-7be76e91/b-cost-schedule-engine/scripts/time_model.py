#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""time_model.py — 全阶段时间模型与预算/截止门（确定性算术核心，仅标准库）。

针对典型失败：只算实验执行、漏掉样品准备/设备排期/表征排队/返工。
本脚本把六个阶段全部入账，并区分 labor_hours（人力工时）与 elapsed_days（自然周期）：
排期等待(booking_wait)与表征排队(characterization_queue)只进 elapsed，不进 labor。

每个 time_item 字段：
  phase              sample_prep | booking_wait | execution |
                     characterization_queue | analysis | rework_buffer
  duration           时长（非负数字，必填）
  unit               hours | days（必填）
  rework_probability 返工概率，0..1（可选）
  rework_cost        单次返工代价，单位与该条目 unit 相同（给了概率则必填）
                     expected_rework = rework_probability * rework_cost，计入该 phase
  source / locator   来源留痕（可选）

单位换算：1 day = workday_hours 小时。workday_hours 必须在 plan_record 顶层
或 case.json 中显式给定；缺省报错 exit 2，绝不臆造 8 或 24。

硬约束门（从 --case case.json 读，可选键）：
  budget        总成本上限；需要 --ledger 提供 grand_total 才能判定；
                case 给了 budget 却没给 --ledger -> exit 2（无法判定不猜）。
  deadline_days 自然周期上限。
gate_status: pass | over_budget | past_deadline | over_budget+past_deadline
任一触发 -> exit 3，报告仍写出。

退出码：0=成功；2=输入/用法错误；3=质量门/校验拦截（缺陷清单写 stdout，产物仍写出）。
"""
import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

PHASES = ["sample_prep", "booking_wait", "execution",
          "characterization_queue", "analysis", "rework_buffer"]
PHASE_LABELS = {
    "sample_prep": "样品准备",
    "booking_wait": "设备排期等待",
    "execution": "实验执行",
    "characterization_queue": "表征排队",
    "analysis": "数据分析",
    "rework_buffer": "返工缓冲",
}
# 计入 labor_hours 的阶段；排期/排队只进自然周期。
LABOR_PHASES = {"sample_prep", "execution", "analysis", "rework_buffer"}
UNITS = ["hours", "days"]
SCHEMA_VERSION = "plan_record/1.0"


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
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, float):
        return None, "值以 float 进入（内部错误）"
    elif isinstance(value, str):
        try:
            d = Decimal(value.strip())
        except Exception:
            return None, "无法解析为数字: %r" % value
    else:
        return None, "非数字类型: %s" % type(value).__name__
    if not d.is_finite():
        return None, "非有限数字"
    return d, None


def load_json(path):
    p = Path(path)
    if not p.is_file():
        sys.stdout.write("INPUT_ERROR: 找不到文件: %s\n" % path)
        raise SystemExit(2)
    try:
        return json.loads(p.read_text(encoding="utf-8"), parse_float=Decimal)
    except json.JSONDecodeError as e:
        sys.stdout.write("INPUT_ERROR: %s 不是合法 JSON: %s\n" % (path, e))
        raise SystemExit(2)


def resolve_workday_hours(plan, case):
    """返回 (Decimal|None, source|None)。缺省返回 (None, None) —— 由调用方报 exit 2。"""
    for obj, src in ((plan, "plan_record.workday_hours"), (case, "case.workday_hours")):
        if isinstance(obj, dict) and "workday_hours" in obj:
            d, err = to_decimal(obj["workday_hours"])
            if err or d <= 0:
                sys.stdout.write("INPUT_ERROR: %s 必须是正数: %r\n" % (src, obj["workday_hours"]))
                raise SystemExit(2)
            return d, src
    return None, None


def build_time_model(plan, case, ledger):
    defects = []
    plan_id = plan.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        defects.append("plan_id 缺失或不是非空字符串")
        plan_id = "UNKNOWN"

    workday_hours, wh_source = resolve_workday_hours(plan, case)
    if workday_hours is None:
        sys.stdout.write(
            "INPUT_ERROR: 缺少 workday_hours（1 day = ? 小时）。"
            "必须在 plan_record 顶层或 case.json 中显式给定；本工具不臆造换算。\n")
        raise SystemExit(2)

    raw_items = plan.get("time_items")
    if raw_items is None:
        raw_items = []
        defects.append("time_items 字段缺失，按空列表处理")
    if not isinstance(raw_items, list):
        defects.append("time_items 不是列表，按空列表处理")
        raw_items = []

    phase_hours = {p: Decimal(0) for p in PHASES}        # 含期望返工
    phase_labor_hours = {p: Decimal(0) for p in PHASES}
    items = []

    for i, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            defects.append("time_items[%d] 不是对象，已跳过" % i)
            continue
        phase = raw.get("phase")
        if phase not in PHASES:
            defects.append("time_items[%d] phase 非法: %r（允许值: %s）"
                           % (i, phase, "/".join(PHASES)))
            phase = None

        dur, dur_err = (None, "缺 duration（必填）") if "duration" not in raw \
            else to_decimal(raw["duration"])
        if dur_err is None and dur < 0:
            dur_err = "duration 为负数: %s" % dstr(dur)
        if dur_err:
            defects.append("time_items[%d] %s" % (i, dur_err))

        unit = raw.get("unit")
        if unit not in UNITS:
            defects.append("time_items[%d] unit 非法: %r（允许值: hours/days）" % (i, unit))
            unit = None

        p_rework = raw.get("rework_probability")
        c_rework = raw.get("rework_cost")
        p_dec = c_dec = None
        expected_rework_hours = None
        if p_rework is not None or c_rework is not None:
            if p_rework is None:
                defects.append("time_items[%d] 给了 rework_cost 但缺 rework_probability" % i)
            else:
                p_dec, p_err = to_decimal(p_rework)
                if p_err is None and not (Decimal(0) <= p_dec <= Decimal(1)):
                    p_err = "rework_probability 必须在 [0,1]: %s" % dstr(p_dec)
                if p_err:
                    defects.append("time_items[%d] %s" % (i, p_err))
                    p_dec = None
            if c_rework is None:
                defects.append("time_items[%d] 给了 rework_probability 但缺 rework_cost" % i)
            else:
                c_dec, c_err = to_decimal(c_rework)
                if c_err is None and c_dec < 0:
                    c_err = "rework_cost 为负数: %s" % dstr(c_dec)
                if c_err:
                    defects.append("time_items[%d] %s" % (i, c_err))
                    c_dec = None

        duration_hours = None
        if dur is not None and dur_err is None and unit in UNITS and phase in PHASES:
            duration_hours = dur * (workday_hours if unit == "days" else Decimal(1))
            if p_dec is not None and c_dec is not None:
                expected_rework_hours = p_dec * c_dec * \
                    (workday_hours if unit == "days" else Decimal(1))
            total_hours = duration_hours + (expected_rework_hours or Decimal(0))
            phase_hours[phase] += total_hours
            if phase in LABOR_PHASES:
                phase_labor_hours[phase] += total_hours

        items.append({
            "index": i,
            "phase": phase,
            "phase_label": PHASE_LABELS.get(phase, "未知"),
            "duration": dstr(dur) if dur is not None and dur_err is None else None,
            "unit": unit,
            "duration_hours": dstr(duration_hours) if duration_hours is not None else None,
            "rework_probability": dstr(p_dec) if p_dec is not None else None,
            "rework_cost": dstr(c_dec) if c_dec is not None else None,
            "expected_rework_hours": dstr(expected_rework_hours)
            if expected_rework_hours is not None else None,
            "counts_toward": ("labor+elapsed" if phase in LABOR_PHASES else "elapsed_only")
            if phase in PHASES else "excluded",
            "source": raw.get("source"),
            "locator": raw.get("locator"),
        })

    labor_hours = sum(phase_labor_hours.values(), Decimal(0))
    elapsed_hours = sum(phase_hours.values(), Decimal(0))
    elapsed_days = elapsed_hours / workday_hours

    # ---- 硬约束门 ----
    gates = {}
    triggered = []
    budget = case.get("budget") if isinstance(case, dict) else None
    deadline = case.get("deadline_days") if isinstance(case, dict) else None

    total_cost = None
    if budget is not None:
        budget_dec, b_err = to_decimal(budget)
        if b_err or budget_dec < 0:
            sys.stdout.write("INPUT_ERROR: case.budget 必须是非负数字: %r\n" % budget)
            raise SystemExit(2)
        if ledger is None:
            sys.stdout.write(
                "INPUT_ERROR: case.json 含 budget，但未提供 --ledger（cost_ledger 产物），"
                "无法判定预算门；不猜。请先运行 cost_ledger.py。\n")
            raise SystemExit(2)
        total_cost, tc_err = to_decimal(ledger.get("grand_total"))
        if tc_err:
            sys.stdout.write("INPUT_ERROR: ledger.grand_total 非法: %r\n"
                             % ledger.get("grand_total"))
            raise SystemExit(2)
        ok = total_cost <= budget_dec
        gates["budget"] = {"limit": dstr(budget_dec), "total_cost": dstr(total_cost),
                           "status": "pass" if ok else "over_budget"}
        if not ok:
            triggered.append("over_budget")
    if deadline is not None:
        dl_dec, d_err = to_decimal(deadline)
        if d_err or dl_dec < 0:
            sys.stdout.write("INPUT_ERROR: case.deadline_days 必须是非负数字: %r\n" % deadline)
            raise SystemExit(2)
        ok = elapsed_days <= dl_dec
        gates["deadline"] = {"limit_days": dstr(dl_dec), "elapsed_days": dstr(elapsed_days),
                             "status": "pass" if ok else "past_deadline"}
        if not ok:
            triggered.append("past_deadline")

    gate_status = "+".join(triggered) if triggered else "pass"

    result = {
        "artifact": "time_model",
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "workday_hours": dstr(workday_hours),
        "workday_hours_source": wh_source,
        "items": items,
        "phase_totals_hours": {PHASE_LABELS[p]: dstr(phase_hours[p]) for p in PHASES},
        "phase_labor_hours": {PHASE_LABELS[p]: dstr(phase_labor_hours[p]) for p in PHASES},
        "labor_hours": dstr(labor_hours),
        "elapsed_hours": dstr(elapsed_hours),
        "elapsed_days": dstr(elapsed_days),
        "total_cost": dstr(total_cost) if total_cost is not None else None,
        "gates": gates,
        "gate_status": gate_status,
        "defects": defects,
        "status": "defects" if defects else "ok",
    }
    notice = plan.get("_notice") or (case.get("_notice") if isinstance(case, dict) else None)
    if isinstance(notice, str) and notice.strip():
        result["notice"] = notice
    return result


def render_md(r):
    lines = []
    if r.get("notice"):
        lines.append("> " + r["notice"])
        lines.append("")
    lines.append("# 时间模型台账 — 方案 %s" % r["plan_id"])
    lines.append("")
    lines.append("- 状态: %s" % r["status"])
    lines.append("- 换算: 1 day = %s h（来源: %s）" % (r["workday_hours"], r["workday_hours_source"]))
    lines.append("- **labor_hours（人力工时）: %s h**" % r["labor_hours"])
    lines.append("- **elapsed_days（自然周期）: %s 天**（elapsed_hours=%s h）"
                 % (r["elapsed_days"], r["elapsed_hours"]))
    lines.append("- 门判定 gate_status: **%s**" % r["gate_status"])
    lines.append("")
    lines.append("| # | 阶段 | 时长 | 单位 | 折算小时 | 返工概率 | 返工代价 | 期望返工(h) | 计入 | 来源 |")
    lines.append("|---|------|------|------|----------|----------|----------|--------------|------|------|")
    for it in r["items"]:
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            it["index"], it["phase_label"],
            it["duration"] if it["duration"] is not None else "缺失",
            it["unit"] or "缺失",
            it["duration_hours"] if it["duration_hours"] is not None else "无法计算",
            it["rework_probability"] or "-",
            it["rework_cost"] or "-",
            it["expected_rework_hours"] or "-",
            it["counts_toward"],
            (it["source"] or "-") + (" / " + it["locator"] if it.get("locator") else ""),
        ))
    lines.append("")
    lines.append("## 逐阶段合计（小时，含期望返工）")
    lines.append("")
    for label, v in r["phase_totals_hours"].items():
        lines.append("- %s: %s h（其中计人力 %s h）" % (label, v, r["phase_labor_hours"][label]))
    lines.append("")
    if r["gates"]:
        lines.append("## 硬约束门")
        lines.append("")
        for g, info in r["gates"].items():
            lines.append("- %s: %s" % (g, json.dumps(info, ensure_ascii=False, sort_keys=True)))
        lines.append("")
    if r["defects"]:
        lines.append("## 缺陷清单（exit 3）")
        lines.append("")
        for d in r["defects"]:
            lines.append("- %s" % d)
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="全阶段时间模型 + 预算/截止门：plan_record.json -> time_model json/md")
    ap.add_argument("--plan", required=True, help="plan_record.json 路径（含 time_items）")
    ap.add_argument("--case", help="case.json 路径（可选；提供 budget/deadline_days/workday_hours）")
    ap.add_argument("--ledger", help="cost_ledger 产出的 ledger_*.json（budget 门判定必需）")
    ap.add_argument("--out-dir", required=True, help="输出目录")
    args = ap.parse_args(argv)

    plan = load_json(args.plan)
    if not isinstance(plan, dict):
        sys.stdout.write("INPUT_ERROR: plan_record 顶层必须是 JSON 对象\n")
        return 2
    case = load_json(args.case) if args.case else {}
    if not isinstance(case, dict):
        sys.stdout.write("INPUT_ERROR: case.json 顶层必须是 JSON 对象\n")
        return 2
    ledger = None
    if args.ledger:
        ledger = load_json(args.ledger)
        if not isinstance(ledger, dict) or ledger.get("artifact") != "cost_ledger":
            sys.stdout.write("INPUT_ERROR: --ledger 必须是 cost_ledger.py 的产物\n")
            return 2
        if ledger.get("status") != "ok":
            sys.stdout.write("INPUT_ERROR: ledger 含缺陷（status!=ok），先修复成本台账\n")
            return 2

    result = build_time_model(plan, case, ledger)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "time_%s" % result["plan_id"]
    (out_dir / (stem + ".json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / (stem + ".md")).write_text(render_md(result), encoding="utf-8")

    if result["defects"]:
        sys.stdout.write("DEFECTS (exit 3):\n")
        for d in result["defects"]:
            sys.stdout.write("- %s\n" % d)
        return 3
    if result["gate_status"] != "pass":
        sys.stdout.write("GATE_TRIGGERED (exit 3): %s\n" % result["gate_status"])
        for g, info in result["gates"].items():
            sys.stdout.write("- %s: %s\n" % (g, json.dumps(info, ensure_ascii=False,
                                                           sort_keys=True)))
        return 3
    sys.stdout.write("OK: plan=%s labor_hours=%s elapsed_days=%s gate=pass -> %s\n"
                     % (result["plan_id"], result["labor_hours"], result["elapsed_days"],
                        out_dir / (stem + ".json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
