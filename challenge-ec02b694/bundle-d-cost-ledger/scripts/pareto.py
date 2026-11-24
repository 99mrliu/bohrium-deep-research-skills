#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pareto.py — 成本-响应 Pareto 前沿与预算约束下的推荐。

输入：cost_sheet.json（plan_costing.py 产物，每版本带 total_cost、total_days、
predicted_response{value,direction,unit}）。
目标：最小化成本、最大化响应（direction=minimize 时按 -value 归一化比较）。

输出 pareto.json：Pareto 前沿、被支配方案标注、预算/截止约束下的推荐版本，
以及明确的取舍陈述（相对最便宜可行版多花 X 元换 Y 单位响应；相对最高响应版
牺牲 Z% 响应省 W 元）。

Decimal 语义，百分比保留两位小数。任何输入不得 traceback。
退出码：0 ok/partial；3 输入非法；1 内部错误（尽量落盘）。
"""

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

SCHEMA_VERSION = "pareto/1.0"
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


def main():
    ap = argparse.ArgumentParser(description="成本-响应 Pareto 前沿与推荐")
    ap.add_argument("--cost-sheet", required=True, help="cost_sheet.json 路径")
    ap.add_argument("--out", required=True, help="输出 pareto.json 路径")
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
        sheet, err = load_json(args.cost_sheet)
        if err:
            return emit({"schema_version": SCHEMA_VERSION, "status": "error",
                         "error": err, "uncertainty": [err]}, 3)
        if not isinstance(sheet, dict) or sheet.get("status") in ("refused", "error"):
            reason = (sheet or {}).get("reason") or (sheet or {}).get("error") or "上游 cost_sheet 不可用"
            return emit({"schema_version": SCHEMA_VERSION, "status": "refused",
                         "reason": "上游 cost_sheet 不可用：%s" % reason,
                         "uncertainty": [reason]}, 3)
        if sheet.get("status") == "partial":
            uncertainty.append("上游 cost_sheet 为 partial：%s"
                               % "; ".join(sheet.get("uncertainty", [])))

        raw_plans = sheet.get("plans") or []
        candidates = []
        for p in raw_plans:
            if not isinstance(p, dict) or p.get("status") != "ok":
                uncertainty.append("版本 %s 未通过成本核算，不参与 Pareto 比较。"
                                   % (p.get("version") if isinstance(p, dict) else p))
                continue
            cost = D(p.get("total_cost"))
            resp_entry = p.get("predicted_response")
            resp = D(resp_entry.get("value") if isinstance(resp_entry, dict) else resp_entry)
            if cost is None or resp is None:
                uncertainty.append("版本 %s 缺 total_cost 或 predicted_response，不参与 Pareto 比较。"
                                   % p.get("version"))
                continue
            direction = (resp_entry.get("direction") if isinstance(resp_entry, dict) else None) or "maximize"
            resp_unit = (resp_entry.get("unit") if isinstance(resp_entry, dict) else None) or "unit"
            cmp_resp = resp if direction == "maximize" else -resp  # 归一化为"越大越好"
            candidates.append({
                "version": p.get("version"),
                "total_cost": cost,
                "total_days": p.get("total_days"),
                "response": resp,
                "response_cmp": cmp_resp,
                "response_direction": direction,
                "response_unit": resp_unit,
                "within_budget": bool(p.get("within_budget")),
                "within_deadline": bool(p.get("within_deadline")),
            })

        if not candidates:
            uncertainty.append("无同时具有成本与预测响应的可用版本，无法计算 Pareto 前沿。")
            return emit({"schema_version": SCHEMA_VERSION, "status": "partial",
                         "frontier": [], "dominated": [], "recommendation": None,
                         "uncertainty": uncertainty}, 0)

        # --- 支配关系：j 支配 i 当且仅当 cost_j<=cost_i 且 resp_j>=resp_i 且至少一个严格 ---
        for c in candidates:
            c["dominated"] = False
            c["dominated_by"] = []
        for i, a in enumerate(candidates):
            for j, b in enumerate(candidates):
                if i == j:
                    continue
                if (b["total_cost"] <= a["total_cost"] and b["response_cmp"] >= a["response_cmp"]
                        and (b["total_cost"] < a["total_cost"] or b["response_cmp"] > a["response_cmp"])):
                    a["dominated"] = True
                    a["dominated_by"].append(b["version"])

        frontier = sorted([c for c in candidates if not c["dominated"]],
                          key=lambda c: (c["total_cost"], -c["response_cmp"]))
        dominated = sorted([c for c in candidates if c["dominated"]],
                           key=lambda c: c["total_cost"])

        # --- 推荐：预算+截止双约束可行集内，响应最大者优先，同响应取成本最低 ---
        feasible = [c for c in candidates if c["within_budget"] and c["within_deadline"]]
        recommendation = None
        tradeoffs = []
        if not feasible:
            uncertainty.append("预算与截止约束下无可行版本；无法给出推荐，status 应如实报 partial。")
        else:
            rec = max(feasible, key=lambda c: (c["response_cmp"], -c["total_cost"]))
            cheapest = min(feasible, key=lambda c: c["total_cost"])
            best_resp_overall = max(candidates, key=lambda c: c["response_cmp"])

            extra_cost = rec["total_cost"] - cheapest["total_cost"]
            extra_resp = rec["response_cmp"] - cheapest["response_cmp"]
            if rec["version"] != cheapest["version"]:
                tradeoffs.append(
                    "推荐版 %s 相对最便宜可行版 %s 多花 %s 元，换取 %s %s 响应提升。"
                    % (rec["version"], cheapest["version"], s2(extra_cost),
                       s2(abs(extra_resp)), rec["response_unit"]))
            else:
                tradeoffs.append("推荐版 %s 即最便宜可行版，无额外花费。" % rec["version"])

            if best_resp_overall["version"] != rec["version"]:
                sacrifice = best_resp_overall["response_cmp"] - rec["response_cmp"]
                base = best_resp_overall["response_cmp"]
                sacrifice_pct = (sacrifice / base * Decimal(100)) if base != 0 else Decimal(0)
                saved = best_resp_overall["total_cost"] - rec["total_cost"]
                feasibility_note = "" if (best_resp_overall["within_budget"]
                                          and best_resp_overall["within_deadline"]) \
                    else "（该版本超出预算或截止约束，本不可行）"
                tradeoffs.append(
                    "推荐版 %s 相对最高响应版 %s 牺牲 %s%% 响应（%s -> %s %s），"
                    "节省 %s 元%s。"
                    % (rec["version"], best_resp_overall["version"], s2(sacrifice_pct),
                       fmt(best_resp_overall["response"]), fmt(rec["response"]),
                       rec["response_unit"], s2(saved), feasibility_note))
            else:
                tradeoffs.append("推荐版 %s 即最高响应版，无响应牺牲。" % rec["version"])

            recommendation = {
                "version": rec["version"],
                "total_cost": s2(rec["total_cost"]),
                "total_days": rec["total_days"],
                "predicted_response": fmt(rec["response"]),
                "response_unit": rec["response_unit"],
                "on_pareto_frontier": not rec["dominated"],
                "tradeoffs": tradeoffs,
            }

        def view(c):
            return {
                "version": c["version"],
                "total_cost": s2(c["total_cost"]),
                "total_days": c["total_days"],
                "predicted_response": fmt(c["response"]),
                "response_direction": c["response_direction"],
                "response_unit": c["response_unit"],
                "within_budget": c["within_budget"],
                "within_deadline": c["within_deadline"],
                "dominated": c["dominated"],
                "dominated_by": c["dominated_by"],
            }

        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if feasible else "partial",
            "objective": "minimize(total_cost), maximize(response)",
            "frontier": [view(c) for c in frontier],
            "dominated": [view(c) for c in dominated],
            "recommendation": recommendation,
            "uncertainty": uncertainty,
        }
        return emit(payload, 0)
    except Exception as e:  # noqa: BLE001
        return emit({"schema_version": SCHEMA_VERSION, "status": "error",
                     "error": "内部错误：%s: %s" % (type(e).__name__, e),
                     "uncertainty": uncertainty}, 1)


if __name__ == "__main__":
    sys.exit(main())
