#!/usr/bin/env python3
"""ledger_check.py — 六面覆盖台账会计校验(仅标准库)。

校验 references/coverage_matrix.md 第四节定义的全部完备性规则:
  1. 五数对账:counts 五态计数与 cells 实算一致,且总和等于单元数;
  2. 每个声明的 facet 至少一个单元;
  3. 同一清单项 ID 不得重复裁决;
  4. "问题"单元必须引用 findings 表中已存在的 finding id;
  5. "待复核"/"未检查"单元 reason 非空;
  6. "不适用"单元 reason 非空且单行;
  7. 每条 finding 的 location 非空;
  8. 状态/审查面/检查面/类别/严重度取值合法。

用法:
    python3 ledger_check.py path/to/ledger.json
打印会计摘要;存在任何违规时向 stderr 逐条报告并以非零码退出。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

STATES = ["通过", "问题", "待复核", "不适用", "未检查"]
SURFACES = ["事实核验", "引用支持", "方法设计", "统计报告", "论证链", "学术规范"]
ALL_FACETS = ["design", "variables", "statistics", "sample_size", "reporting"]
CATEGORIES = ["事实错误", "证据不足", "规范问题", "建议"]
SEVERITIES = ["高", "中", "低", "提示"]
CELL_REQUIRED = ["cell_id", "item_id", "facet", "surface", "status", "reason"]
FINDING_REQUIRED = ["id", "category", "severity", "location", "evidence", "suggestion"]


def validate(led: dict) -> tuple[list[str], list[str], Counter, Counter, Counter]:
    errors: list[str] = []
    warnings: list[str] = []
    state_counts: Counter = Counter()
    facet_counts: Counter = Counter()
    surface_counts: Counter = Counter()

    cells = led.get("cells")
    if not isinstance(cells, list) or not cells:
        errors.append("cells 缺失、不是数组或为空数组")
        cells = []
    findings = led.get("findings", [])
    if not isinstance(findings, list):
        errors.append("findings 不是数组")
        findings = []

    finding_ids: list[str] = []
    for f in findings:
        if isinstance(f, dict) and isinstance(f.get("id"), str):
            if f["id"] in finding_ids:
                errors.append(f"finding id 重复: {f['id']}")
            finding_ids.append(f["id"])

    seen_items: dict[str, str] = {}
    for i, c in enumerate(cells):
        where = c.get("cell_id", f"cells[{i}]") if isinstance(c, dict) else f"cells[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{where}: 单元不是对象")
            continue
        for k in CELL_REQUIRED:
            if k not in c:
                errors.append(f"{where}: 缺少必填字段 {k}")
        status = c.get("status")
        if status not in STATES:
            errors.append(f"{where}: 非法状态 {status!r},必须属于 {STATES}")
        else:
            state_counts[status] += 1
        facet = c.get("facet")
        if facet not in ALL_FACETS:
            errors.append(f"{where}: 非法检查面 {facet!r}")
        else:
            facet_counts[facet] += 1
        surface = c.get("surface")
        if surface not in SURFACES:
            errors.append(f"{where}: 非法审查面 {surface!r}")
        else:
            surface_counts[surface] += 1

        item = c.get("item_id")
        if isinstance(item, str):
            if item in seen_items:
                errors.append(
                    f"{where}: 清单项 {item} 重复裁决(首次出现于 {seen_items[item]})"
                )
            else:
                seen_items[item] = where

        reason = c.get("reason")
        reason_ok = isinstance(reason, str) and reason.strip() != ""
        if status in ("待复核", "未检查") and not reason_ok:
            errors.append(f"{where}: 状态为{status},reason 必须非空并说明原因")
        if status == "不适用":
            if not reason_ok:
                errors.append(f"{where}: 状态为不适用,必须给出一句理由")
            elif "\n" in reason:
                errors.append(f"{where}: 不适用的理由必须为单行")
        if status == "通过" and not reason_ok:
            warnings.append(f"{where}: 通过但未写依据,建议补充原文位置")
        if status == "问题":
            fids = c.get("finding_ids")
            if not isinstance(fids, list) or not fids:
                errors.append(f"{where}: 状态为问题,finding_ids 必须非空")
            else:
                for fid in fids:
                    if fid not in finding_ids:
                        errors.append(f"{where}: 引用了不存在的 finding id: {fid!r}")

    declared_facets = led.get("facets", ALL_FACETS)
    if not isinstance(declared_facets, list) or not declared_facets:
        errors.append("facets 声明缺失或为空")
        declared_facets = []
    for fct in declared_facets:
        if facet_counts.get(fct, 0) == 0:
            errors.append(f"声明的检查面 {fct!r} 没有任何台账单元")

    declared = led.get("counts")
    if not isinstance(declared, dict):
        errors.append("counts 五数声明缺失或不是对象")
    else:
        for key in declared:
            if key not in STATES:
                errors.append(f"counts 含非法状态键: {key!r}")
        for s in STATES:
            dv = declared.get(s)
            if dv is None:
                errors.append(f"counts 缺少状态 {s!r} 的计数")
            elif not isinstance(dv, int) or dv < 0:
                errors.append(f"counts[{s!r}] 不是非负整数: {dv!r}")
            elif dv != state_counts.get(s, 0):
                errors.append(
                    f"五数对账失败: counts[{s!r}]={dv},cells 实算={state_counts.get(s, 0)}"
                )
        total_declared = sum(v for k, v in declared.items() if k in STATES and isinstance(v, int))
        if total_declared != len(cells):
            errors.append(
                f"五数之和({total_declared})与台账单元总数({len(cells)})不一致"
            )

    referenced = {fid for c in cells if isinstance(c, dict) for fid in c.get("finding_ids", []) or []}
    for f in findings:
        if not isinstance(f, dict):
            errors.append("findings 含非对象条目")
            continue
        fid = f.get("id", "<无id>")
        for k in FINDING_REQUIRED:
            if k not in f:
                errors.append(f"finding {fid}: 缺少必填字段 {k}")
        loc = f.get("location")
        if not isinstance(loc, str) or loc.strip() == "":
            errors.append(f"finding {fid}: 原文位置 location 必须非空")
        if f.get("category") not in CATEGORIES:
            errors.append(f"finding {fid}: 非法缺陷类别 {f.get('category')!r}")
        if f.get("severity") not in SEVERITIES:
            errors.append(f"finding {fid}: 非法严重度 {f.get('severity')!r}")
        if f.get("category") == "建议" and f.get("severity") in ("高", "中"):
            errors.append(f"finding {fid}: “建议”类缺陷严重度只允许 低/提示")
        if fid not in referenced:
            warnings.append(f"finding {fid}: 未被任何“问题”单元引用(孤儿 finding)")

    return errors, warnings, state_counts, facet_counts, surface_counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description="六面覆盖台账会计校验:五数对账、分面覆盖、状态-理由约束、finding 引用完整性。"
    )
    ap.add_argument("ledger", help="待校验的 ledger.json 路径")
    args = ap.parse_args()

    try:
        with open(args.ledger, "r", encoding="utf-8") as fh:
            led = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"FATAL: 无法读取/解析 {args.ledger}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(led, dict):
        print("FATAL: 台账顶层必须是 JSON 对象", file=sys.stderr)
        return 2

    errors, warnings, state_counts, facet_counts, surface_counts = validate(led)

    total = sum(state_counts.values())
    print("== 台账会计摘要 ==")
    print(f"case_id: {led.get('case_id', '<未声明>')}  设计类型: {led.get('design_type', '<未声明>')}")
    print(f"台账单元总数: {total}")
    print("五态计数(实算): " + "  ".join(f"{s}={state_counts.get(s, 0)}" for s in STATES))
    print("检查面覆盖:    " + "  ".join(f"{f}={facet_counts.get(f, 0)}" for f in ALL_FACETS))
    print("审查面覆盖:    " + "  ".join(f"{s}={surface_counts.get(s, 0)}" for s in SURFACES))
    uncovered = [s for s in SURFACES if surface_counts.get(s, 0) == 0]
    if uncovered:
        warnings.append("以下审查面无任何单元覆盖: " + ", ".join(uncovered))
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"VIOLATION: {e}", file=sys.stderr)
        print(f"LEDGER CHECK FAIL ({len(errors)} 处违规)", file=sys.stderr)
        return 1
    print("LEDGER CHECK PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
