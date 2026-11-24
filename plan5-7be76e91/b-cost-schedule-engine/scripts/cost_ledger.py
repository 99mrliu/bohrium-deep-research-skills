#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cost_ledger.py — 全口径成本台账（确定性算术核心，仅标准库）。

分工：模型只负责从真实材料抽取 cost_items 并挂来源；本脚本完成全部算术。
所有金额运算使用 decimal.Decimal（JSON 解析即 parse_float=Decimal），禁止 float 尾差。

每个 cost_item 字段：
  name       条目名（字符串）
  category   equipment_time | consumable | labor | outsourcing | other
  basis      one_time | per_run        （一次性投入 vs 按次消耗）
  quantity   数量（非负数字，必填）
  unit       计量单位（字符串，如 小时/工日/套）
  unit_price 单价（非负数字，必填；缺失进缺陷清单，绝不静默当 0）
  runs       重复次数（正整数，缺省 1；仅 per_run 参与折算）
  source     来源文件（可选，台账留痕）
  locator    来源定位（可选，如页码/段落）

line_total = quantity * unit_price * (runs 当 basis=per_run，否则 1)

退出码：0=成功；2=输入/用法错误；3=质量门/校验拦截（缺陷清单写 stdout，产物仍尽量写出）。
"""
import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

CATEGORIES = ["equipment_time", "consumable", "labor", "outsourcing", "other"]
CATEGORY_LABELS = {
    "equipment_time": "机时费",
    "consumable": "耗材",
    "labor": "人力",
    "outsourcing": "外送",
    "other": "其他",
}
BASES = ["one_time", "per_run"]
BASIS_LABELS = {"one_time": "一次性投入", "per_run": "按次消耗"}
SCHEMA_VERSION = "plan_record/1.0"


def dstr(d):
    """Decimal -> 紧凑十进制字符串（无科学计数法、无尾随零），保证确定性。"""
    if not isinstance(d, Decimal):
        d = Decimal(d)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def to_decimal(value):
    """把 JSON 值安全转为 Decimal。返回 (Decimal|None, error|None)。"""
    if isinstance(value, bool):
        return None, "布尔值不是数字"
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, float):
        return None, "值以 float 进入（本工具要求 parse_float=Decimal，属内部错误）"
    elif isinstance(value, str):
        try:
            d = Decimal(value.strip())
        except InvalidOperation:
            return None, "无法解析为数字: %r" % value
    else:
        return None, "非数字类型: %s" % type(value).__name__
    if not d.is_finite():
        return None, "非有限数字"
    return d, None


def load_json(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise SystemExit(2) from e
    try:
        return json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as e:
        sys.stdout.write("INPUT_ERROR: %s 不是合法 JSON: %s\n" % (path, e))
        raise SystemExit(2)


def build_ledger(plan):
    defects = []
    plan_id = plan.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        defects.append("plan_id 缺失或不是非空字符串")
        plan_id = "UNKNOWN"

    raw_items = plan.get("cost_items")
    if raw_items is None:
        raw_items = []
        defects.append("cost_items 字段缺失，按空列表处理")
    if not isinstance(raw_items, list):
        defects.append("cost_items 不是列表，按空列表处理")
        raw_items = []

    items = []
    subtotals = {c: Decimal(0) for c in CATEGORIES}
    one_time_total = Decimal(0)
    per_run_total = Decimal(0)

    for i, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            defects.append("cost_items[%d] 不是对象，已跳过" % i)
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            name = "item_%d" % i
            defects.append("cost_items[%d] 缺 name，记为 %s" % (i, name))

        category = raw.get("category")
        if category not in CATEGORIES:
            defects.append("条目[%s] category 非法: %r（允许值: %s）"
                           % (name, category, "/".join(CATEGORIES)))
            category = None

        basis = raw.get("basis")
        if basis not in BASES:
            defects.append("条目[%s] basis 非法: %r（允许值: one_time/per_run）" % (name, basis))
            basis = None

        qty, qty_err = (None, "缺 quantity（必填，不允许静默当 0）") if "quantity" not in raw \
            else to_decimal(raw["quantity"])
        if qty_err is None and qty < 0:
            qty_err = "quantity 为负数: %s" % dstr(qty)
        if qty_err:
            defects.append("条目[%s] %s" % (name, qty_err))

        price, price_err = (None, "缺 unit_price（必填，不允许静默当 0）") if "unit_price" not in raw \
            else to_decimal(raw["unit_price"])
        if price_err is None and price < 0:
            price_err = "unit_price 为负数: %s" % dstr(price)
        if price_err:
            defects.append("条目[%s] %s" % (name, price_err))

        runs_raw = raw.get("runs", 1)
        runs, runs_err = to_decimal(runs_raw)
        if runs_err is None and (runs != runs.to_integral_value() or runs < 1):
            runs_err = "runs 必须是 >=1 的整数: %s" % dstr(runs)
        if runs_err:
            defects.append("条目[%s] %s" % (name, runs_err))
            runs = None

        unit = raw.get("unit")
        if not isinstance(unit, str) or not unit.strip():
            defects.append("条目[%s] 缺 unit（计量单位字符串）" % name)
            unit = ""

        line_total = None
        if qty is not None and qty_err is None and price is not None and price_err is None \
                and runs is not None and basis in BASES and category in CATEGORIES:
            line_total = qty * price * (runs if basis == "per_run" else Decimal(1))
            subtotals[category] += line_total
            if basis == "per_run":
                per_run_total += line_total
            else:
                one_time_total += line_total

        items.append({
            "index": i,
            "name": name,
            "category": category,
            "category_label": CATEGORY_LABELS.get(category, "未知"),
            "basis": basis,
            "basis_label": BASIS_LABELS.get(basis, "未知"),
            "quantity": dstr(qty) if qty is not None and qty_err is None else None,
            "unit": unit,
            "unit_price": dstr(price) if price is not None and price_err is None else None,
            "runs": int(runs) if runs is not None and runs_err is None else None,
            "line_total": dstr(line_total) if line_total is not None else None,
            "source": raw.get("source"),
            "locator": raw.get("locator"),
        })

    grand_total = one_time_total + per_run_total
    ledger = {
        "artifact": "cost_ledger",
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "currency_note": "按输入数值原样求和；不做币种换算，币种一致性由模型在抽取阶段核实。",
        "arithmetic_note": "全部金额运算使用 decimal.Decimal，无 float 尾差。",
        "items": items,
        "subtotals_by_category": {CATEGORY_LABELS[c]: dstr(subtotals[c]) for c in CATEGORIES},
        "one_time_total": dstr(one_time_total),
        "per_run_total": dstr(per_run_total),
        "grand_total": dstr(grand_total),
        "defects": defects,
        "status": "defects" if defects else "ok",
    }
    notice = plan.get("_notice")
    if isinstance(notice, str) and notice.strip():
        ledger["notice"] = notice
    return ledger


def render_md(ledger):
    lines = []
    if ledger.get("notice"):
        lines.append("> " + ledger["notice"])
        lines.append("")
    lines.append("# 成本台账 ledger — 方案 %s" % ledger["plan_id"])
    lines.append("")
    lines.append("- 状态: %s" % ledger["status"])
    lines.append("- 算术: %s" % ledger["arithmetic_note"])
    lines.append("- 币种: %s" % ledger["currency_note"])
    lines.append("")
    lines.append("| # | 条目 | 口径 | 一次性/按次 | 数量 | 单位 | 单价 | runs | 小计 | 来源 |")
    lines.append("|---|------|------|------------|------|------|------|------|------|------|")
    for it in ledger["items"]:
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            it["index"], it["name"], it["category_label"], it["basis_label"],
            it["quantity"] if it["quantity"] is not None else "缺失",
            it["unit"] or "缺失",
            it["unit_price"] if it["unit_price"] is not None else "缺失",
            it["runs"] if it["runs"] is not None else "非法",
            it["line_total"] if it["line_total"] is not None else "无法计算",
            (it["source"] or "-") + (" / " + it["locator"] if it.get("locator") else ""),
        ))
    lines.append("")
    lines.append("## 分口径小计")
    lines.append("")
    for label, v in ledger["subtotals_by_category"].items():
        lines.append("- %s: %s" % (label, v))
    lines.append("")
    lines.append("## 一次性 vs 按次")
    lines.append("")
    lines.append("- 一次性投入合计: %s" % ledger["one_time_total"])
    lines.append("- 按次消耗合计（已按 runs 折算）: %s" % ledger["per_run_total"])
    lines.append("- **总计 grand_total: %s**" % ledger["grand_total"])
    lines.append("")
    if ledger["defects"]:
        lines.append("## 缺陷清单（exit 3）")
        lines.append("")
        for d in ledger["defects"]:
            lines.append("- %s" % d)
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="全口径成本台账：plan_record.json -> ledger.json + ledger.md（Decimal 确定性算术）")
    ap.add_argument("--plan", required=True, help="plan_record.json 路径（含 cost_items）")
    ap.add_argument("--out-dir", required=True, help="输出目录")
    args = ap.parse_args(argv)

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        sys.stdout.write("INPUT_ERROR: 找不到 plan 文件: %s\n" % plan_path)
        return 2
    plan = load_json(plan_path)
    if not isinstance(plan, dict):
        sys.stdout.write("INPUT_ERROR: plan_record 顶层必须是 JSON 对象\n")
        return 2

    ledger = build_ledger(plan)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "ledger_%s" % ledger["plan_id"]
    (out_dir / (stem + ".json")).write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / (stem + ".md")).write_text(render_md(ledger), encoding="utf-8")

    if ledger["defects"]:
        sys.stdout.write("DEFECTS (exit 3):\n")
        for d in ledger["defects"]:
            sys.stdout.write("- %s\n" % d)
        return 3
    sys.stdout.write("OK: plan=%s grand_total=%s -> %s\n"
                     % (ledger["plan_id"], ledger["grand_total"], out_dir / (stem + ".json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
