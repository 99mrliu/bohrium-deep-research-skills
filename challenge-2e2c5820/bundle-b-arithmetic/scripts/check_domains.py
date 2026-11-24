#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_domains.py — 参数域成员判定（有限域/区间域 + 单位归一化）

用法:
    python3 check_domains.py <extraction.json> <case.json> <out.md>
                             [--domains PATH] [--units PATH] [--json-out OUT.json]

域来源:
    --domains PATH  显式 JSON（list，元素含 name + values 或 min/max + unit）。
    否则在 case.json 中查找键名匹配 domain/参数域/parameter 且值为
    "dict list（每个 dict 含 name）" 的节点。

名称匹配（模糊，规则见 references/arithmetic_rules.md）:
    1. 规范化（去空白/下划线/括号/连字符，小写）后精确相等；
    2. 一方包含另一方；
    3. 都不满足 → no_domain_found（如实报告，绝不静默放过）。

单位归一化（references/units.json）:
    参数单位与域单位不同但属于同一可换算维度 → 先换算再比较；
    单位相同 → 直接比较；
    维度标记 convertible=false（如 rpm↔g）或跨维度 → unit_unconvertible，
    标记并请专家复核，绝不猜换算。

verdict: in_domain / out_of_domain / no_domain_found / unit_unconvertible

退出码:
    0  成功（out_of_domain 是结论，不是错误）
    2  用法错误 / 文件不可读 / 数据无法判定
"""
import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

DOMAIN_KEY = re.compile(r"domain|参数域|参数范围|parameter", re.IGNORECASE)
DEFAULT_UNITS = Path(__file__).resolve().parent.parent / "references" / "units.json"


def dec(x):
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def norm_name(s):
    return re.sub(r"[\s_\-—()（）/·]+", "", str(s)).lower()


def load_units(path):
    table = {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("错误(exit 2): 无法读取单位表 %s: %s\n" % (path, exc))
        sys.exit(2)
    for dim in data.get("dimensions", []):
        for unit, factor in dim.get("units", {}).items():
            table[unit] = {"dimension": dim.get("name"), "factor": dec(factor),
                           "convertible": bool(dim.get("convertible", True))}
    return table


def find_domains_in_case(case):
    best = []

    def walk(node, path):
        nonlocal best
        if isinstance(node, dict):
            for k, v in node.items():
                p = "%s.%s" % (path, k) if path else str(k)
                if (DOMAIN_KEY.search(str(k)) and isinstance(v, list) and v
                        and all(isinstance(e, dict) and "name" in e for e in v)):
                    if len(v) > len(best):
                        best = v
                        best_path[0] = p
                walk(v, p)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))

    best_path = [None]
    walk(case, "")
    return best, best_path[0]


def match_domain(pname, domains):
    np = norm_name(pname)
    for d in domains:
        if norm_name(d.get("name", "")) == np:
            return d, "exact"
    for d in domains:
        nd = norm_name(d.get("name", ""))
        if nd and (np in nd or nd in np):
            return d, "containment"
    return None, None


def convert(value, from_unit, to_unit, units):
    """返回 (Decimal 已换算到 to_unit 的值, status)。status: ok / unit_unconvertible"""
    if str(from_unit) == str(to_unit):
        v = dec(value)
        return (v, "ok") if v is not None else (None, "unit_unconvertible")
    fu, tu = units.get(str(from_unit)), units.get(str(to_unit))
    if not fu or not tu or fu["dimension"] != tu["dimension"] or fu["dimension"] is None:
        return None, "unit_unconvertible"
    if not (fu["convertible"] and tu["convertible"]) or not fu["factor"] or not tu["factor"]:
        return None, "unit_unconvertible"
    v = dec(value)
    if v is None:
        return None, "unit_unconvertible"
    return v * fu["factor"] / tu["factor"], "ok"


def main(argv):
    ap = argparse.ArgumentParser(description="参数域成员判定")
    ap.add_argument("extraction")
    ap.add_argument("case")
    ap.add_argument("out")
    ap.add_argument("--domains", default=None)
    ap.add_argument("--units", default=str(DEFAULT_UNITS))
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv[1:])

    try:
        ext = json.loads(Path(args.extraction).read_text(encoding="utf-8"), parse_float=Decimal)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("错误(exit 2): 读取 extraction 失败: %s\n" % exc)
        return 2
    plan_id = ext.get("plan_id", "<unknown>")
    units = load_units(args.units)

    if args.domains:
        try:
            domains = json.loads(Path(args.domains).read_text(encoding="utf-8"))
            dom_source = args.domains
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("错误(exit 2): 读取 --domains 失败: %s\n" % exc)
            return 2
    else:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("错误(exit 2): 读取 case.json 失败: %s\n" % exc)
            return 2
        domains, dom_path = find_domains_in_case(case)
        dom_source = dom_path or "<未找到>"

    results, unverified = [], []
    counts = {"in_domain": 0, "out_of_domain": 0, "no_domain_found": 0, "unit_unconvertible": 0}
    for p in ext.get("parameters", []) or []:
        pname, pval, punit = p.get("name", "?"), p.get("value"), str(p.get("unit", ""))
        entry = {"name": pname, "value": pval, "unit": punit, "locator": p.get("locator", "")}
        d, how = match_domain(pname, domains)
        if d is None:
            entry.update(verdict="no_domain_found")
            unverified.append("%s: 未找到对应参数域（locator: %s）" % (pname, p.get("locator", "")))
        else:
            entry["domain"] = {"name": d.get("name"), "unit": d.get("unit"),
                               "values": d.get("values"), "min": d.get("min"), "max": d.get("max"),
                               "match": how}
            dunit = str(d.get("unit", ""))
            conv, status = convert(pval, punit, dunit, units)
            if status != "ok":
                entry.update(verdict="unit_unconvertible",
                             note="单位 %s ↔ %s 不可自动换算，请专家复核（rpm↔g 依赖转子半径，绝不猜测）" % (punit, dunit))
                unverified.append("%s: 单位 %s↔%s 不可自动换算（locator: %s）" % (pname, punit, dunit, p.get("locator", "")))
            else:
                entry["value_in_domain_unit"] = conv
                if isinstance(d.get("values"), list) and d["values"]:
                    allowed = [dec(v) for v in d["values"]]
                    ok = conv in [a for a in allowed if a is not None]
                    entry.update(verdict="in_domain" if ok else "out_of_domain",
                                 detail="%s ∈ %s ? %s" % (conv, d["values"], "是" if ok else "否"))
                elif d.get("min") is not None or d.get("max") is not None:
                    lo, hi = dec(d.get("min")), dec(d.get("max"))
                    ok = (lo is None or conv >= lo) and (hi is None or conv <= hi)
                    entry.update(verdict="in_domain" if ok else "out_of_domain",
                                 detail="%s ≤ %s ≤ %s ? %s" % (lo, conv, hi, "是" if ok else "否"))
                else:
                    entry.update(verdict="no_domain_found", note="域条目既无 values 也无 min/max")
                    unverified.append("%s: 域条目 %s 无可判定的 values/min/max" % (pname, d.get("name")))
        counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
        results.append(entry)

    md = []
    md.append("# 参数域判定报告 — %s" % plan_id)
    md.append("")
    md.append("> 域来源: `%s`；单位归一化表: `%s`；全部判定由脚本实算。" % (dom_source, args.units))
    md.append("")
    md.append("| 参数 | 取值 | 单位 | 域 | 换算后 | 判定 | 说明 |")
    md.append("|---|---|---|---|---|---|---|")
    for e in results:
        dom = e.get("domain") or {}
        dom_s = dom.get("name", "—")
        if dom.get("values"):
            dom_s += " ∈ %s" % dom["values"]
        elif dom.get("min") is not None or dom.get("max") is not None:
            dom_s += " ∈ [%s, %s] %s" % (dom.get("min"), dom.get("max"), dom.get("unit", ""))
        md.append("| %s | %s | %s | %s | %s | **%s** | %s |" % (
            e["name"], e["value"], e["unit"], dom_s,
            e.get("value_in_domain_unit", "—"), e["verdict"], e.get("detail") or e.get("note", "")))
    md.append("")
    md.append("## 汇总")
    md.append("")
    for k in ("in_domain", "out_of_domain", "no_domain_found", "unit_unconvertible"):
        md.append("- %s: %d" % (k, counts.get(k, 0)))
    if unverified:
        md.append("")
        md.append("## unverified 项（如实列出）")
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
        payload = {"kind": "domains", "plan_id": plan_id, "domain_source": dom_source,
                   "parameters": results, "counts": counts, "unverified": unverified}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2, cls=Enc), encoding="utf-8")

    print("参数域判定 [%s]: " % plan_id + ", ".join("%s=%d" % (k, counts.get(k, 0)) for k in
          ("in_domain", "out_of_domain", "no_domain_found", "unit_unconvertible")))
    for e in results:
        if e["verdict"] != "in_domain":
            print("  %s: %s %s %s → %s %s" % (e["name"], e["value"], e["unit"],
                  (e.get("domain") or {}).get("name", ""), e["verdict"], e.get("detail") or e.get("note", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
