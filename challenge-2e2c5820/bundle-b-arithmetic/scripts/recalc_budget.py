#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recalc_budget.py — 预算确定性复算（全部 Decimal 实算，模型结论概不采信）

用法:
    python3 recalc_budget.py <extraction.json> <case.json> <out.md>
                             [--cap AMOUNT] [--json-out OUT.json]
                             [--drift-tol 0.005]

对每一行预算:
    复算  unit_price × quantity = computed_subtotal
    若有 stated_subtotal: 计算 |stated - computed| / computed，
    漂移 > 容差(默认 0.5%) 即标记 unverified（申报值不采信，以复算值为准）。
合计后与预算上限比较:
    上限来源优先级: --cap > case.json 中键名匹配 cap/上限/budget/预算 的数值。
    找不到上限 → verdict = "unverified_cap_not_found"（如实报告，不编造）。
verdict: "超支" (total > cap) / "结余" (total <= cap)，delta = total - cap。
所有金额显示按 ROUND_HALF_UP 量化到 0.01。

退出码:
    0  成功（超支/结余是结论，不是错误）
    2  用法错误 / 文件不可读 / 数据无法实算
"""
import argparse
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

CENT = Decimal("0.01")
CAP_KEY = re.compile(r"cap|上限|budget|预算", re.IGNORECASE)


def dec(x):
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def money(d):
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def find_cap(case):
    """在 case.json 中启发式寻找预算上限。返回 (Decimal, path) 或 (None, None)。"""
    hits = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                p = "%s.%s" % (path, k) if path else str(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and CAP_KEY.search(str(k)):
                    d = dec(v)
                    if d is not None and d > 0:
                        hits.append((p, d))
                walk(v, p)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))

    walk(case, "")
    if not hits:
        return None, None
    # 键名直接含 cap/上限 的优先
    hits.sort(key=lambda t: 0 if re.search(r"cap|上限", t[0], re.IGNORECASE) else 1)
    return hits[0][1], hits[0][0]


def main(argv):
    ap = argparse.ArgumentParser(description="预算确定性复算")
    ap.add_argument("extraction")
    ap.add_argument("case")
    ap.add_argument("out")
    ap.add_argument("--cap", default=None, help="显式预算上限（跳过 case.json 启发式查找）")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--drift-tol", type=float, default=0.005, help="stated vs 复算 漂移容差, 默认 0.005 (0.5%%)")
    args = ap.parse_args(argv[1:])

    try:
        ext = json.loads(Path(args.extraction).read_text(encoding="utf-8"), parse_float=Decimal)
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("错误(exit 2): 读取输入失败: %s\n" % exc)
        return 2

    plan_id = ext.get("plan_id", "<unknown>")
    items = ext.get("budget_items", [])
    if not items:
        sys.stderr.write("错误(exit 2): extraction 中没有 budget_items\n")
        return 2

    tol = Decimal(str(args.drift_tol))
    lines, unverified = [], []
    currencies = set()
    total = Decimal(0)

    for it in items:
        name = it.get("name", "?")
        price, qty = dec(it.get("unit_price")), dec(it.get("quantity"))
        cur = str(it.get("currency", "?"))
        currencies.add(cur)
        if price is None or qty is None:
            unverified.append("%s: 单价/数量不是可实算数值 (%r, %r)" % (name, it.get("unit_price"), it.get("quantity")))
            lines.append({"name": name, "formula": "%s: 无法实算" % name, "unverified": True})
            continue
        computed = price * qty
        total += computed
        qty_s = str(int(qty)) if qty == qty.to_integral_value() else str(qty.normalize())
        formula = "%s %s × %s = %s %s" % (name, money(price), qty_s, money(computed), cur)
        entry = {"name": name, "unit_price": money(price), "quantity": qty,
                 "computed_subtotal": money(computed), "currency": cur,
                 "formula": formula, "locator": it.get("locator", ""), "flagged": False}
        if "stated_subtotal" in it:
            stated = dec(it.get("stated_subtotal"))
            if stated is None:
                entry["stated_subtotal"] = str(it.get("stated_subtotal"))
                entry["flagged"] = True
                unverified.append("%s: stated_subtotal 非数值 %r" % (name, it.get("stated_subtotal")))
            else:
                entry["stated_subtotal"] = money(stated)
                if computed != 0:
                    drift = abs(stated - computed) / abs(computed)
                else:
                    drift = Decimal(0) if stated == 0 else Decimal(1)
                entry["drift_pct"] = (drift * 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                if drift > tol:
                    entry["flagged"] = True
                    entry["formula"] += "（申报 %s，漂移 %s%% > %s%%，申报值标记 unverified，以复算值为准）" % (
                        money(stated), entry["drift_pct"], (tol * 100).normalize())
                    unverified.append("%s: stated_subtotal=%s 与复算 %s 漂移 %s%%（locator: %s）" % (
                        name, money(stated), money(computed), entry["drift_pct"], it.get("locator", "")))
        lines.append(entry)

    mixed = len(currencies) > 1
    cap, cap_source = (dec(args.cap), "--cap") if args.cap is not None else find_cap(case)

    if mixed:
        verdict, delta = "unverified_mixed_currency", None
    elif cap is None:
        verdict, delta = "unverified_cap_not_found", None
        unverified.append("case.json 中未找到预算上限（cap/上限/budget/预算），无法判定超支/结余")
    else:
        delta = total - cap
        verdict = "超支" if total > cap else "结余"

    total_q = money(total)
    md = []
    md.append("# 预算复算报告 — %s" % plan_id)
    md.append("")
    md.append("> 本报告全部由脚本以 Decimal 实算生成；每行给出公式与操作数，可重跑复现。")
    md.append("")
    md.append("## 逐行复算")
    md.append("")
    for e in lines:
        mark = " ⚠️" if e.get("flagged") else ""
        md.append("- `%s`%s" % (e["formula"], mark))
    md.append("")
    md.append("## 合计与上限")
    md.append("")
    md.append("- 复算合计: **%s %s**" % (total_q, "/".join(sorted(currencies))))
    if cap is not None:
        md.append("- 预算上限: **%s**（来源: `%s`）" % (money(cap), cap_source))
        md.append("- delta = 合计 - 上限 = %s - %s = **%s**" % (total_q, money(cap), money(delta)))
        md.append("- 结论: **%s %s %s**" % (verdict, money(abs(delta)), "/".join(sorted(currencies))))
    else:
        md.append("- 预算上限: 未找到 → 结论 **unverified_cap_not_found**（不编造上限）")
    if unverified:
        md.append("")
        md.append("## unverified 项（如实列出，未采信）")
        for u in unverified:
            md.append("- %s" % u)
    md.append("")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(md), encoding="utf-8")

    class Enc(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return str(o)
            return super().default(o)

    if args.json_out:
        payload = {"kind": "budget", "plan_id": plan_id, "lines": lines,
                   "total": total_q, "currencies": sorted(currencies),
                   "cap": money(cap) if cap is not None else None,
                   "cap_source": cap_source, "verdict": verdict,
                   "delta": money(delta) if delta is not None else None,
                   "unverified": unverified}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2, cls=Enc), encoding="utf-8")

    print("预算复算 [%s]: 合计 %s %s; 上限 %s; 结论 %s%s" % (
        plan_id, total_q, "/".join(sorted(currencies)),
        money(cap) if cap is not None else "未找到",
        verdict, (" delta=%s" % money(delta)) if delta is not None else ""))
    for u in unverified:
        print("  unverified: %s" % u)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
