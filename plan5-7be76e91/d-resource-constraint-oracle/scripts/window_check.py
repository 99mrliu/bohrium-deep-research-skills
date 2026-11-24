#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""window_check.py — 参数窗口三方对照（方案要求窗口 × 设备能力窗口 × 契约/文献域窗口）。

对每份方案的每个参数窗口计算：
  allowed = 设备极限 ∩ 契约域（缺失一方则以另一方为准，双方均缺则记 unbounded）；
  status:
    ok                 —— 方案要求 ⊆ allowed；
    partial_overlap    —— 与 allowed 有交但未被完全覆盖（冲突区间写清）；
    empty_intersection —— 方案要求 ∩ allowed = ∅（质量门拦截，退出码 3）。
输出 window_report.json / window_report.md（交集矩阵）。

退出码：0 = 无空交集；2 = 输入/用法错误；3 = 存在空交集（产物仍写出）。
仅标准库；确定性（无 wall-clock / 随机数），双跑字节一致。
"""
import argparse
import json
import sys


def fmt_num(x):
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def fmt_win(w):
    if w is None:
        return "(-∞, +∞)"
    lo = "-∞" if w.get("min") is None else fmt_num(w["min"])
    hi = "+∞" if w.get("max") is None else fmt_num(w["max"])
    return "[%s, %s]" % (lo, hi)


def win_intersect(a, b):
    los = [w.get("min") for w in (a, b) if w is not None and w.get("min") is not None]
    his = [w.get("max") for w in (a, b) if w is not None and w.get("max") is not None]
    lo = max(los) if los else None
    hi = min(his) if his else None
    if lo is not None and hi is not None and lo > hi:
        return None
    return {"min": lo, "max": hi}


def win_contains(outer, inner):
    if outer is None:
        return False
    if outer.get("min") is not None:
        if inner.get("min") is None or inner["min"] < outer["min"]:
            return False
    if outer.get("max") is not None:
        if inner.get("max") is None or inner["max"] > outer["max"]:
            return False
    return True


def check_windows(facts, case):
    resources = facts.get("resources_available", {})
    equip_by_id = {e["id"]: e for e in resources.get("equipment", [])}
    domain = case.get("contract_domain", {}) or {}
    rows = []
    for plan in facts.get("plan_requirements", []):
        pid = plan["plan_id"]
        for pw in plan.get("parameter_windows", []):
            param = pw.get("parameter")
            req = pw.get("required")
            if req is None:
                continue
            dev_win = None
            dev_src = []
            for need in plan.get("equipment_needs", []):
                eq = equip_by_id.get(need.get("equipment_id"))
                if eq and param in (eq.get("capabilities") or {}):
                    dev_src.append(need.get("equipment_id"))
                    dev_win = eq["capabilities"][param] if dev_win is None \
                        else win_intersect(dev_win, eq["capabilities"][param])
            dom_win = domain.get(param)
            if dev_win is not None and dom_win is not None:
                allowed = win_intersect(dev_win, dom_win)
            else:
                allowed = dev_win if dev_win is not None else dom_win
            if allowed is None:
                status = "unbounded"
                inter = req
            else:
                inter = win_intersect(allowed, req)
                if inter is None:
                    status = "empty_intersection"
                elif win_contains(allowed, req):
                    status = "ok"
                else:
                    status = "partial_overlap"
            rows.append({
                "plan_id": pid,
                "parameter": param,
                "required": req,
                "device_window": dev_win,
                "device_sources": dev_src,
                "domain_window": dom_win,
                "allowed": allowed,
                "intersection_with_required": inter,
                "status": status,
            })
    return rows


def write_reports(case_id, rows, out_dir, note=None):
    import os
    report = {
        "case_id": case_id,
        "matrix": rows,
        "empty_intersections": [
            {"plan_id": r["plan_id"], "parameter": r["parameter"]}
            for r in rows if r["status"] == "empty_intersection"
        ],
    }
    if note:
        report["note"] = note
    jpath = os.path.join(out_dir, "window_report.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    lines = []
    if note:
        lines.append("> %s" % note)
        lines.append("")
    lines.append("# 参数窗口三方对照矩阵（window_report）")
    lines.append("")
    lines.append("- case_id: %s" % case_id)
    lines.append("- 列含义：方案要求窗口 / 设备极限窗口 / 契约域窗口 / 允许区间（设备∩契约域）/ 与方案要求的交集 / 判定")
    lines.append("")
    lines.append("| 方案 | 参数 | 方案要求 | 设备极限 | 契约域 | 允许区间 | 交集 | 判定 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["plan_id"], r["parameter"],
            fmt_win(r["required"]), fmt_win(r["device_window"]),
            fmt_win(r["domain_window"]), fmt_win(r["allowed"]),
            fmt_win(r["intersection_with_required"]) if r["intersection_with_required"] is not None else "∅",
            r["status"]))
    lines.append("")
    empties = [r for r in rows if r["status"] == "empty_intersection"]
    if empties:
        lines.append("## 空交集清单（质量门拦截）")
        lines.append("")
        for r in empties:
            lines.append("- %s / %s：方案要求 %s 与允许区间 %s 无交集。"
                         % (r["plan_id"], r["parameter"], fmt_win(r["required"]), fmt_win(r["allowed"])))
        lines.append("")
    mpath = os.path.join(out_dir, "window_report.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    return jpath, mpath


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="参数窗口三方对照：方案要求窗口 × 设备能力窗口 × 契约/文献域窗口，输出交集矩阵；"
                    "空交集以退出码 3 拦截。")
    ap.add_argument("--facts", required=True, help="facts JSON（resources_available + plan_requirements）")
    ap.add_argument("--case", required=True, help="case JSON（含 contract_domain）")
    ap.add_argument("--out-dir", required=True, help="输出目录（window_report.json/.md）")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/Markdown 报告顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args(argv)

    import os
    try:
        with open(args.facts, "r", encoding="utf-8") as f:
            facts = json.load(f)
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("输入错误：%s" % e, file=sys.stderr)
        return 2

    rows = check_windows(facts, case)
    os.makedirs(args.out_dir, exist_ok=True)
    jpath, mpath = write_reports(case.get("case_id", "UNKNOWN"), rows, args.out_dir,
                                 note=args.note)
    print("已写出: %s" % jpath)
    print("已写出: %s" % mpath)
    empties = [r for r in rows if r["status"] == "empty_intersection"]
    if empties:
        print("质量门拦截：存在空交集参数窗口：")
        for r in empties:
            print("  %s / %s：要求 %s，允许 %s"
                  % (r["plan_id"], r["parameter"], fmt_win(r["required"]), fmt_win(r["allowed"])))
        return 3
    print("全部参数窗口与允许区间有交集。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
