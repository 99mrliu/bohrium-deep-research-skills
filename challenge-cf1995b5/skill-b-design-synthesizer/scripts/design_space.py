#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
design_space.py — exp-design-synthesizer 核心脚本（bundle B）

子命令：
  enumerate  从 case.json 的 parameter_domains 展开合法参数网格 -> design_space.json
  score      对候选方案/设计策略逐点核算成本与工期（整数/Decimal 算术）-> design_table.json
  select     在 feasible 设计中按排序规则选推荐设计与备选 -> selection.json

硬性约束：
  - 仅 Python 3 标准库；确定性输出；缺键不崩（exit 0 + partial 报告）；支持 --help；
  - 所有算术用 int / Decimal，不允许浮点误差；试剂按 pack_size 向上取整计价；
  - 机时->周数向上取整；不同设备并行预约，关键设备决定 est_days。
"""
import argparse
import json
import re
import sys
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from itertools import product
from pathlib import Path

MAX_ROWS = 10000  # enumerate 输出的组合表行数上限（总数仍精确给出）
POINTS_PREVIEW = 50  # design_table 每行内嵌 points 预览上限
DEFAULT_WEIGHTS = {"conditions": 10, "pairs": 5, "levels": 2, "replicates": 1}
REP_CAP = 3  # 信息度里重复次数的封顶


# ---------------------------------------------------------------- 基础工具

def D(x):
    """安全转 Decimal；失败返回 None。"""
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def num(d):
    """Decimal -> int（整数值）或 float（仅用于 JSON 展示层，不参与算术）。"""
    if d is None:
        return None
    if d == d.to_integral_value():
        return int(d)
    return float(d)


def ceil_div_decimal(a, b):
    """ceil(a/b)，a,b 为 Decimal；b<=0 返回 None。"""
    if a is None or b is None or b <= 0:
        return None
    return int((a / b).to_integral_value(rounding=ROUND_CEILING))


def json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else str(o)
    raise TypeError(repr(o))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_out(obj, out_path):
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=json_default)
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")
    return text


def domain_values(spec):
    """展开一个参数域为有序水平列表。无法展开返回 None。"""
    if not isinstance(spec, dict):
        return None
    t = spec.get("type")
    if t == "range":
        mn, mx, st = D(spec.get("min")), D(spec.get("max")), D(spec.get("step"))
        if mn is None or mx is None or st is None or st <= 0 or mx < mn:
            return None
        vals, v = [], mn
        while v <= mx:
            vals.append(num(v))
            v += st
        return vals
    if t == "enum":
        vals = spec.get("values")
        return list(vals) if isinstance(vals, list) and vals else None
    return None


def pick_levels(values, n):
    """确定性抽取至多 n 个水平：n=1 取中位水平；否则等距抽取且含两端。"""
    if not values:
        return []
    if n is None or len(values) <= n:
        return list(values)
    if n <= 1:
        return [values[len(values) // 2]]
    idxs = sorted({(i * (len(values) - 1)) // (n - 1) for i in range(n)})
    return [values[i] for i in idxs]


def in_domain(spec, value):
    """检查 value 是否落在域内。返回 (ok, msg)。域缺失视为 ok 但给提示。"""
    if not isinstance(spec, dict):
        return True, "no_domain_info(未提供该因子域，按假设处理)"
    t = spec.get("type")
    if t == "range":
        mn, mx, st = D(spec.get("min")), D(spec.get("max")), D(spec.get("step"))
        v = D(value)
        if None in (mn, mx, st, v) or st <= 0:
            return False, "domain_unparseable"
        if v < mn or v > mx:
            return False, f"out_of_range[{num(mn)},{num(mx)}]"
        if (v - mn) % st != 0:
            return False, f"off_grid(step={num(st)})"
        return True, ""
    if t == "enum":
        vals = spec.get("values") or []
        return (value in vals), ("" if value in vals else f"not_in_enum{vals}")
    return True, "unknown_domain_type"


# ---------------------------------------------------------------- 资源模型

def parse_embedded_equipment(note):
    """从 equipment_domain_note 文本中提取内嵌 JSON 设备片段（```json 围栏或首尾大括号）。"""
    found = []
    if not isinstance(note, str) or not note.strip():
        return found
    blobs = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", note, re.S)
    if not blobs and "{" in note and "}" in note:
        blobs = [note[note.index("{"): note.rindex("}") + 1]]
    for blob in blobs:
        try:
            obj = json.loads(blob)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("equipment"), list):
            found.extend(e for e in obj["equipment"] if isinstance(e, dict) and e.get("id"))
        elif isinstance(obj, dict) and obj.get("id"):
            found.append(obj)
    return found


def build_context(case, model_override=None):
    """从 case.json 构建核算上下文；缺键时对应字段为 None 并记录 assumptions。"""
    ctx = {"assumptions": [], "warnings": []}
    rc = case.get("resource_contract") or {}
    ctx["currency"] = rc.get("currency", "CNY")
    ctx["budget_cap"] = D(rc.get("budget_cap"))
    ctx["deadline_days"] = D(rc.get("deadline_days"))
    if ctx["budget_cap"] is None:
        ctx["assumptions"].append("resource_contract.budget_cap 缺失：预算可行性无法判定")
    if ctx["deadline_days"] is None:
        ctx["assumptions"].append("resource_contract.deadline_days 缺失：工期可行性无法判定")

    # 设备：列表 + equipment_domain_note 内嵌片段合并（对账）
    equipment = {}
    for e in rc.get("equipment") or []:
        if isinstance(e, dict) and e.get("id"):
            equipment[e["id"]] = dict(e, _source="resource_contract.equipment")
    embedded = parse_embedded_equipment(case.get("equipment_domain_note", ""))
    for e in embedded:
        if e["id"] in equipment:
            ctx["warnings"].append(f"设备 {e['id']} 同时出现在 equipment 列表与 equipment_domain_note，以列表为准")
        else:
            equipment[e["id"]] = dict(e, _source="equipment_domain_note(内嵌解析)")
    for eid, e in equipment.items():
        bk = e.get("booking") or {}
        e["_weekly_hours"] = (D(bk.get("slots_per_week")) or D(0)) * (D(bk.get("slot_hours")) or D(0))
        if e["_weekly_hours"] <= 0:
            ctx["warnings"].append(f"设备 {eid} 每周可用机时为 0（booking 缺失或为 0）")
    ctx["equipment"] = equipment
    if not equipment:
        ctx["assumptions"].append("无可用设备信息：机时/工期核算降级为 unknown")

    ctx["reagents"] = {r["id"]: r for r in (rc.get("reagents") or []) if isinstance(r, dict) and r.get("id")}

    # 单样本消耗模型：case.experiment_model.per_sample，可被 --model 覆盖
    model = (case.get("experiment_model") or {}).get("per_sample") or {}
    if model_override:
        model = model_override.get("per_sample", model_override)
        ctx["assumptions"].append("per_sample 消耗模型来自 --model 覆盖文件（视为显式假设）")
    ctx["eq_hours_per_sample"] = {k: dv for k, dv in
                                  ((k, D(v)) for k, v in (model.get("equipment_hours") or {}).items())
                                  if dv is not None}
    ctx["reagent_per_sample"] = {k: dv for k, dv in
                                 ((k, D(v)) for k, v in (model.get("reagent_use") or {}).items())
                                 if dv is not None}
    if not ctx["eq_hours_per_sample"]:
        ctx["assumptions"].append(
            "缺少 experiment_model.per_sample.equipment_hours：机时与 est_days 记为 unknown；"
            "Agent 应从任务步骤推导各设备单样本机时并以 --model 显式提供（写入 result.json 的 assumptions）")
    if not ctx["reagent_per_sample"]:
        ctx["assumptions"].append("缺少 experiment_model.per_sample.reagent_use：试剂成本记为 unknown")

    ctx["domains"] = case.get("parameter_domains") or {}
    if not ctx["domains"]:
        ctx["assumptions"].append("parameter_domains 缺失：域合法性无法判定")
    return ctx


# ---------------------------------------------------------------- 设计展开

RESERVED_KEYS = {"replicates"}


def candidate_to_points(params, domains):
    """候选方案 parameters -> (points, replicates, notes)。数组=扫描，标量=固定。"""
    notes = []
    reps = params.get("replicates", 1)
    if "replicates" not in params:
        notes.append("candidate 未声明 replicates，按 1 处理（假设）")
    reps = int(D(reps) or 1)
    factors = {k: v for k, v in params.items() if k not in RESERVED_KEYS}
    lists, fixed = {}, {}
    for k, v in factors.items():
        if isinstance(v, list) and v:
            lists[k] = v
        else:
            fixed[k] = v
    order = sorted(lists) + sorted(fixed)
    points = []
    for combo in product(*[lists[k] for k in sorted(lists)]):
        pt = dict(zip(sorted(lists), combo))
        pt.update(fixed)
        points.append({k: pt[k] for k in order})
    if not points and fixed:
        points = [{k: fixed[k] for k in order}]
    return points, reps, notes


def expand_strategy(st, domains):
    """策略 JSON -> (points, replicates, notes)。类型: explicit / full_factorial / orthogonal / ofat_scan。"""
    notes = []
    name = st.get("name", "unnamed")
    typ = st.get("type", "explicit")
    reps = int(D(st.get("replicates", 1)) or 1)
    levels_cap = st.get("levels_per_factor")
    levels_cap = int(D(levels_cap)) if levels_cap is not None else None
    fixed = dict(st.get("fixed") or {})
    all_factors = sorted(domains.keys())

    def picked(f):
        vals = domain_values(domains.get(f))
        if vals is None:
            notes.append(f"因子 {f} 域无法展开，已跳过")
            return None
        return pick_levels(vals, levels_cap)

    if typ == "explicit":
        pts = st.get("points") or []
        return [dict(p) for p in pts if isinstance(p, dict)], reps, notes

    if typ == "full_factorial":
        varied = st.get("factors") or all_factors
        per = {}
        for f in varied:
            lv = picked(f)
            if lv:
                per[f] = lv
        for f in all_factors:
            if f not in per:
                if f in fixed:
                    per[f] = [fixed[f]]
                else:
                    mid = pick_levels(domain_values(domains.get(f)) or [], 1)
                    if mid:
                        per[f] = mid
                        notes.append(f"因子 {f} 未在策略中变化，固定为中位水平 {mid[0]}（假设）")
        order = sorted(per)
        pts = [{k: v for k, v in zip(order, combo)} for combo in product(*[per[k] for k in order])]
        return pts, reps, notes

    if typ == "orthogonal":
        # 循环拉丁方主效应计划：L 个条件，第 i 个因子在第 j 行取第 (j+i) mod L 个水平
        varied = st.get("factors") or all_factors
        L = levels_cap or 3
        per, ok = {}, True
        for f in varied:
            lv = picked(f)
            if not lv or len(lv) < L:
                notes.append(f"因子 {f} 可用水平不足 L={L}，orthogonal 策略无法构建")
                ok = False
            else:
                per[f] = lv[:L]
        if not ok or not per:
            return [], reps, notes
        order = sorted(per)
        pts = []
        for j in range(L):
            pts.append({f: per[f][(j + i) % L] for i, f in enumerate(order)})
        for f in all_factors:
            if f not in per:
                base = fixed.get(f, (pick_levels(domain_values(domains.get(f)) or [None], 1) or [None])[0])
                for p in pts:
                    p[f] = base
                notes.append(f"因子 {f} 固定为 {base}（假设）")
        return pts, reps, notes

    if typ == "ofat_scan":
        varied = st.get("factors") or all_factors
        baseline = {}
        for f in varied:
            if f in fixed:
                baseline[f] = fixed[f]
            else:
                lv = picked(f) or []
                baseline[f] = lv[len(lv) // 2] if lv else None
        pts, seen = [], set()
        for f in varied:
            for lv in (picked(f) or []):
                pt = dict(baseline)
                pt[f] = lv
                key = json.dumps(pt, sort_keys=True, default=str)
                if key not in seen:
                    seen.add(key)
                    pts.append(pt)
        for f in all_factors:
            if f not in varied:
                base = fixed.get(f, (pick_levels(domain_values(domains.get(f)) or [None], 1) or [None])[0])
                for p in pts:
                    p[f] = base
                notes.append(f"因子 {f} 固定为 {base}（假设）")
        notes.append(f"OFAT 基线: {baseline}")
        return pts, reps, notes

    notes.append(f"未知策略类型 {typ!r}，按空设计处理")
    return [], reps, notes


# ---------------------------------------------------------------- 核算核心

def info_components(points, replicates):
    """信息度组件：条件数、共变因子对数、覆盖水平总数、重复数(封顶)。"""
    if not points:
        return {"n_conditions": 0, "covarying_pairs": 0, "levels_sum": 0, "replicates_capped": 0}
    factors = sorted({k for p in points for k in p})
    distinct = {f: sorted({json.dumps(p.get(f)) for p in points}) for f in factors}
    levels_sum = sum(len(v) for v in distinct.values())
    pairs = 0
    for i, f1 in enumerate(factors):
        for f2 in factors[i + 1:]:
            d1, d2 = len(distinct[f1]), len(distinct[f2])
            if d1 < 2 or d2 < 2:
                continue
            combos = {(json.dumps(p.get(f1)), json.dumps(p.get(f2))) for p in points}
            if len(combos) > max(d1, d2):
                pairs += 1
    return {"n_conditions": len(points), "covarying_pairs": pairs,
            "levels_sum": levels_sum, "replicates_capped": min(replicates, REP_CAP)}


def info_score(comp, weights):
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    return (w["conditions"] * comp["n_conditions"] + w["pairs"] * comp["covarying_pairs"]
            + w["levels"] * comp["levels_sum"] + w["replicates"] * comp["replicates_capped"])


def score_one(design_id, source, points, replicates, ctx, min_replicates, weights,
              summary=None, declared=None, extra_notes=None):
    """对单个设计做完整核算。所有金额/机时用 Decimal。缺模型时对应字段为 None（unknown）。"""
    row = {"id": design_id, "source": source, "summary": summary or "",
           "replicates": replicates, "assumptions": list(extra_notes or []),
           "reject_reasons": [], "consistency_warnings": []}
    n_cond = len(points)
    n_samples = n_cond * replicates
    row["n_conditions"] = n_cond
    row["n_samples"] = n_samples
    row["points_preview"] = points[:POINTS_PREVIEW]
    row["points_truncated"] = n_cond > POINTS_PREVIEW

    # 1) 域合法性
    in_dom = True
    for p in points:
        for f, v in p.items():
            ok, msg = in_domain(ctx["domains"].get(f), v)
            if not ok:
                in_dom = False
                row["reject_reasons"].append(f"in_domain=False: {f}={v} {msg}")
            elif msg:
                row["assumptions"].append(f"{f}: {msg}")

    # 2) 机时与工期（各设备并行预约，关键设备决定 est_days）
    eq_rows, est_days, hours_known = {}, None, bool(ctx["eq_hours_per_sample"])
    if hours_known:
        max_weeks, n_counted = 0, 0
        for eid, hps in sorted(ctx["eq_hours_per_sample"].items()):
            eq = ctx["equipment"].get(eid)
            hours = hps * n_samples
            if eq is None:
                row["consistency_warnings"].append(f"per_sample 引用了未知设备 {eid}，其机时不计入工期")
                continue
            weekly = eq.get("_weekly_hours") or D(0)
            weeks = ceil_div_decimal(hours, weekly) if weekly > 0 else None
            max_weeks = max(max_weeks, weeks if weeks is not None else 10 ** 9)
            n_counted += 1
            eq_rows[eid] = {"hours": hours, "weekly_capacity_hours": weekly,
                            "weeks_needed": weeks, "name": eq.get("name"), "model": eq.get("model"),
                            "equipment_source": eq.get("_source")}
        est_days = max_weeks * 7 if n_counted else None
    else:
        for eid in ctx["equipment"]:
            eq_rows[eid] = {"hours": None, "weeks_needed": None, "note": "unknown(缺 per_sample 机时模型)"}
    row["equipment_usage"] = eq_rows
    row["est_days"] = est_days

    # 3) 成本（设备机时 + 试剂按 pack_size 向上取整）
    eq_cost, eq_cost_rows, cost_known = D(0), {}, hours_known
    if hours_known:
        for eid, hps in sorted(ctx["eq_hours_per_sample"].items()):
            eq = ctx["equipment"].get(eid)
            if eq is None:
                continue
            price = D(eq.get("price_per_hour"))
            if price is None:
                row["consistency_warnings"].append(f"设备 {eid} 缺 price_per_hour，成本按 0 计（partial）")
                price = D(0)
            hours = hps * n_samples
            cost = hours * price
            eq_cost += cost
            eq_cost_rows[eid] = {"hours": hours, "price_per_hour": price, "cost": cost}

    rg_cost, rg_rows = D(0), {}
    for rid, qps in sorted(ctx["reagent_per_sample"].items()):
        rg = ctx["reagents"].get(rid)
        if rg is None:
            row["consistency_warnings"].append(f"per_sample 引用了未知试剂 {rid}，未计价")
            continue
        qty = qps * n_samples
        pack = D(rg.get("pack_size")) or D(1)
        unit_price = D(rg.get("unit_price")) or D(0)
        packs = ceil_div_decimal(qty, pack)
        cost = D(packs) * pack * unit_price
        rg_cost += cost
        rg_rows[rid] = {"quantity_needed": qty, "unit": rg.get("unit"), "pack_size": pack,
                        "packs_purchased": packs, "unit_price": unit_price, "cost": cost,
                        "name": rg.get("name")}
    total = (eq_cost + rg_cost) if cost_known else None
    row["cost_breakdown"] = {"equipment": eq_cost_rows, "reagents": rg_rows,
                             "equipment_cost": eq_cost if cost_known else None,
                             "reagent_cost": rg_cost,
                             "total_cost": total, "currency": ctx["currency"]}

    # 4) 可行性三项布尔（+ 重复次数下限）
    cap, ddl = ctx["budget_cap"], ctx["deadline_days"]
    within_budget = None if (total is None or cap is None) else total <= cap
    within_deadline = None if (est_days is None or ddl is None) else D(est_days) <= ddl
    reps_ok = replicates >= min_replicates
    if not in_dom:
        pass  # reasons 已在上面追加
    if within_budget is False:
        row["reject_reasons"].append(
            f"within_budget=False: 核算总成本 {total} {ctx['currency']} > budget_cap {cap}")
    if within_deadline is False:
        row["reject_reasons"].append(
            f"within_deadline=False: 关键设备决定 est_days={est_days} > deadline_days {num(ddl)}")
    if not reps_ok:
        row["reject_reasons"].append(
            f"replicates_ok=False: replicates={replicates} < min_replicates={min_replicates}（无法估计实验误差）")
    if within_budget is None:
        row["assumptions"].append("within_budget=unknown（成本或预算缺失）")
    if within_deadline is None:
        row["assumptions"].append("within_deadline=unknown（工期或截止缺失）")
    overall = bool(in_dom and within_budget is not False and within_deadline is not False and reps_ok)
    row["feasible"] = {"in_domain": in_dom, "within_budget": within_budget,
                       "within_deadline": within_deadline, "replicates_ok": reps_ok,
                       "overall": overall}
    if not overall and not row["reject_reasons"]:
        row["reject_reasons"].append("可行性字段含 unknown，按不可推荐处理（honest partial）")

    # 5) 候选方案自报数对账
    if declared:
        items = declared.get("cost_items") or []
        try:
            items_sum = sum(D(i.get("subtotal")) or D(0) for i in items)
        except Exception:
            items_sum = None
        dt, dd = D(declared.get("total_cost")), D(declared.get("est_days"))
        row["declared"] = {"total_cost": dt, "est_days": dd, "cost_items_sum": items_sum}
        if dt is not None and items_sum is not None and dt != items_sum:
            row["consistency_warnings"].append(
                f"declared_total_mismatch: total_cost={dt} 与 cost_items 合计={items_sum} 不符")
        if dt is not None and total is not None and dt != total:
            row["consistency_warnings"].append(
                f"declared_vs_computed_cost: 自报 {dt}，脚本核算 {total}，差 {total - dt}")
        if dd is not None and est_days is not None and int(dd) != est_days:
            row["consistency_warnings"].append(
                f"declared_vs_computed_days: 自报 est_days={int(dd)}，脚本核算 {est_days}")

    # 6) 信息度
    comp = info_components(points, replicates)
    row["info_components"] = comp
    row["info_score"] = info_score(comp, weights)
    return row


# ---------------------------------------------------------------- 子命令

def cmd_enumerate(args):
    case = load_json(args.case)
    domains = case.get("parameter_domains") or {}
    factors = args.factors.split(",") if args.factors else sorted(domains)
    factors = [f.strip() for f in factors if f.strip()]
    levels_cap = args.levels
    per, notes = {}, []
    for f in factors:
        vals = domain_values(domains.get(f))
        if vals is None:
            notes.append(f"因子 {f} 无合法域定义，已跳过")
            continue
        per[f] = pick_levels(vals, levels_cap)
    total = 1
    for f in per:
        total *= len(per[f])
    if not per:
        total = 0
    combos = []
    order = sorted(per)
    if per:
        for i, combo in enumerate(product(*[per[k] for k in order])):
            if i >= MAX_ROWS:
                break
            combos.append({k: v for k, v in zip(order, combo)})
    out = {"status": "partial" if notes else "ok",
           "case_id": case.get("case_id"),
           "factors": {f: {"n_levels": len(per[f]), "levels": per[f],
                           "basis": (domains.get(f) or {}).get("basis"),
                           "source": (domains.get(f) or {}).get("source")} for f in order},
           "total_combinations": total,
           "combinations_returned": len(combos),
           "combinations_truncated": total > len(combos),
           "combinations": combos, "notes": notes}
    if args.notice:
        out["_notice"] = args.notice
    write_out(out, args.out)
    print(f"[enumerate] 因子 {len(per)} 个，合法组合 {total} 个"
          f"（输出 {len(combos)} 行）-> {args.out}")


def cmd_score(args):
    case = load_json(args.case)
    model_override = load_json(args.model) if args.model else None
    ctx = build_context(case, model_override)
    weights = json.loads(args.weights) if args.weights else None
    rows = []

    if not args.no_candidates:
        for cp in case.get("candidate_plans") or []:
            pts, reps, notes = candidate_to_points(cp.get("parameters") or {}, ctx["domains"])
            rows.append(score_one(f"candidate_{cp.get('version', '?')}", "candidate_plan",
                                  pts, reps, ctx, args.min_replicates, weights,
                                  summary=cp.get("summary"), declared=cp, extra_notes=notes))

    if args.strategies:
        for st in load_json(args.strategies):
            pts, reps, notes = expand_strategy(st, ctx["domains"])
            rows.append(score_one(f"strategy_{st.get('name', 'unnamed')}", "strategy",
                                  pts, reps, ctx, args.min_replicates, weights,
                                  summary=st.get("rationale"), extra_notes=notes))

    feasible_n = sum(1 for r in rows if r["feasible"]["overall"])
    out = {"status": "ok" if rows else "partial",
           "case_id": case.get("case_id"),
           "n_designs": len(rows), "n_feasible": feasible_n,
           "budget_cap": ctx["budget_cap"], "deadline_days": ctx["deadline_days"],
           "currency": ctx["currency"], "min_replicates": args.min_replicates,
           "info_weights": dict(DEFAULT_WEIGHTS, **(weights or {})),
           "context_assumptions": ctx["assumptions"], "context_warnings": ctx["warnings"],
           "equipment_register": {eid: {"name": e.get("name"), "model": e.get("model"),
                                        "price_per_hour": D(e.get("price_per_hour")),
                                        "weekly_capacity_hours": e.get("_weekly_hours"),
                                        "source": e.get("_source")}
                                  for eid, e in sorted(ctx["equipment"].items())},
           "designs": rows}
    if args.notice:
        out["_notice"] = args.notice
    write_out(out, args.out)
    print(f"[score] 核算 {len(rows)} 个设计，feasible {feasible_n} 个 -> {args.out}")
    for r in rows:
        tag = "FEASIBLE" if r["feasible"]["overall"] else "REJECTED"
        print(f"  {tag:9s} {r['id']:36s} cost={r['cost_breakdown']['total_cost']} "
              f"est_days={r['est_days']} info={r['info_score']}"
              + (f"  理由: {'; '.join(r['reject_reasons'])}" if r['reject_reasons'] else ""))


def cmd_select(args):
    table = load_json(args.table)
    weights = json.loads(args.weights) if args.weights else None
    designs = table.get("designs") or []
    for r in designs:
        if weights and r.get("info_components"):
            r["info_score"] = info_score(r["info_components"], weights)
    feasible = [r for r in designs if (r.get("feasible") or {}).get("overall")]
    rejected = [r for r in designs if not (r.get("feasible") or {}).get("overall")]

    def sort_key(r):
        c = r.get("cost_breakdown") or {}
        total = c.get("total_cost")
        total = D(total) if total is not None else Decimal("Infinity")
        est = r.get("est_days")
        return (-int(r.get("info_score") or 0), total, est if est is not None else 10 ** 9, r.get("id", ""))

    feasible.sort(key=sort_key)
    recommended = feasible[0] if feasible else None
    alternates = feasible[1:1 + args.alternates]
    out = {
        "status": "ok" if recommended else "partial",
        "case_id": table.get("case_id"),
        "ranking_rule": (
            "1) 仅 feasible.overall=True 可入选（域合法 ∧ 预算内 ∧ 截止内 ∧ replicates 达标）；"
            "2) info_score 降序（权重: {w}）；3) 核算总成本升序；4) est_days 升序；5) id 字典序"
        ).format(w=dict(DEFAULT_WEIGHTS, **(weights or {}))),
        "recommended": recommended,
        "alternates": alternates,
        "other_feasible_ids": [r["id"] for r in feasible[1 + args.alternates:]],
        "rejected": [{"id": r.get("id"), "source": r.get("source"),
                      "reject_reasons": r.get("reject_reasons") or ["未给出理由"],
                      "consistency_warnings": r.get("consistency_warnings") or []}
                     for r in rejected],
    }
    if not recommended:
        out["degraded_action"] = "无 feasible 设计：放宽 min_replicates / 缩减 levels_per_factor / 申请追加预算或延期，并在 result.json 标 partial"
    if args.notice:
        out["_notice"] = args.notice
    write_out(out, args.out)
    if recommended:
        print(f"[select] 推荐 {recommended['id']} "
              f"(info={recommended['info_score']}, cost={recommended['cost_breakdown']['total_cost']}, "
              f"est_days={recommended['est_days']})；备选 {[a['id'] for a in alternates]}；"
              f"否决 {len(rejected)} 个 -> {args.out}")
    else:
        print(f"[select] 无 feasible 设计（partial）-> {args.out}")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="design_space.py",
        description="有限域组合设计合成：enumerate 展开合法设计空间 / score 逐点核算成本工期 / select 按规则选优")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--out", default=None, help="输出 JSON 路径（缺省打印到 stdout）")
        p.add_argument("--notice", default=None, help="写入输出的顶部提示语（如合成示例声明）")

    pe = sub.add_parser("enumerate", help="展开 parameter_domains 合法参数网格")
    pe.add_argument("--case", required=True, help="case.json 路径")
    pe.add_argument("--factors", default=None, help="逗号分隔的因子子集（缺省全部）")
    pe.add_argument("--levels", type=int, default=None, help="每因子水平数上限（等距抽取，含两端）")
    common(pe)

    ps = sub.add_parser("score", help="对候选方案与策略逐点核算成本/工期/可行性")
    ps.add_argument("--case", required=True)
    ps.add_argument("--strategies", default=None, help="自定义策略 JSON 文件（列表）")
    ps.add_argument("--model", default=None, help="per_sample 消耗模型覆盖 JSON")
    ps.add_argument("--no-candidates", action="store_true", help="跳过 case.candidate_plans")
    ps.add_argument("--min-replicates", type=int, default=2, help="可行性的最小重复次数（默认 2）")
    ps.add_argument("--weights", default=None, help="信息度权重 JSON，如 '{\"conditions\":10}'")
    common(ps)

    pl = sub.add_parser("select", help="在 feasible 设计中按排序规则选推荐与备选")
    pl.add_argument("--table", required=True, help="score 输出的 design_table.json")
    pl.add_argument("--alternates", type=int, default=2, help="备选数量（默认 2）")
    pl.add_argument("--weights", default=None, help="重算信息度的权重 JSON（可选）")
    common(pl)
    return ap


def main():
    args = build_parser().parse_args()
    if not args.cmd:
        build_parser().print_help()
        sys.exit(0)
    try:
        {"enumerate": cmd_enumerate, "score": cmd_score, "select": cmd_select}[args.cmd](args)
    except Exception as e:  # 缺键/坏输入不崩：输出 partial 报告并 exit 0
        report = {"status": "error", "error": f"{type(e).__name__}: {e}",
                  "hint": "检查输入 JSON 结构；脚本对缺失字段应降级为 partial 而非崩溃"}
        text = write_out(report, getattr(args, "out", None))
        if not getattr(args, "out", None):
            print(text)
        print(f"[{args.cmd}] 异常降级为 error 报告: {e}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
