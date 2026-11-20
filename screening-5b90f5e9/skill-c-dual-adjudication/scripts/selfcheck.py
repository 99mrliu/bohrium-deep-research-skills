#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 终检 result.json：合同字段齐、kappa 已报告、分歧全仲裁、
人工确认门清单一致、计数闭合。

用法:
    python3 selfcheck.py [--work /app/work] [--output-dir /app/output]

检查项:
    1. result.json 存在且 output_contract 列出的每个字段非 null/非占位符；
    2. 合同中含 kappa 的字段与 agreement_report.json 数值一致（容差 1e-4）；
    3. disagreements.json 的每条 record_id 均在 arbitrations.json 中有仲裁；
    4. 合同中 human/复核 字段（若为列表）与 final_labels.jsonl 的
       human_confirmation_required 记录集合一致；
    5. 合同中 identified/duplicates/screened/included/excluded/needs_human
       等计数字段（若存在）与审计计数一致，且 PRISMA 闭合；
    6. 合同中 uncertainty/局限 字段（若存在）必须显式声明未经人工复核。

退出码: 0=全部通过, 2=用法或IO错误, 3=校验失败
"""
import argparse
import json
import math
import re
import sys
import traceback
from pathlib import Path


def eprint(*a):
    print(*a, file=sys.stderr)


def load_json(path, default=None):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def is_empty(v):
    return v is None or v == "" or v == "__PENDING__"


def ids_from(value):
    out = set()
    if isinstance(value, list):
        for it in value:
            if isinstance(it, dict):
                rid = it.get("record_id") or it.get("id")
                if rid:
                    out.add(str(rid))
            elif isinstance(it, str):
                for m in re.findall(r"R\d{2,}|[A-Za-z]+-?\d+", it):
                    out.add(m)
    return out


def main():
    ap = argparse.ArgumentParser(description="终检 result.json 与审计产物一致性")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()
    work = Path(args.work)

    result_path = Path(args.output_dir) / "result.json"
    if not result_path.exists():
        eprint(f"[selfcheck] 缺少 {result_path}")
        return 2
    result = json.loads(result_path.read_text(encoding="utf-8"))
    summary = load_json(work / "case_summary.json", {})
    agreement = load_json(work / "agreement_report.json", {})
    disagreements = load_json(work / "disagreements.json", [])
    arbitrations = load_json(work / "arbitrations.json", [])
    counts = load_json(work / "final_counts.json", {})
    audit = load_json(work / "audit_summary.json", {})
    finals = load_jsonl(work / "final_labels.jsonl") \
        if (work / "final_labels.jsonl").exists() else []

    failures = []

    # 1. 合同字段齐
    contract = summary.get("output_contract", [])
    if not contract:
        print("[selfcheck] 警告: 无 output_contract，仅做通用检查")
    for field in contract:
        if is_empty(result.get(field)):
            failures.append(f"合同字段未填充: {field}")

    # 2. kappa 数值一致
    k3 = (agreement.get("three_class") or {}).get("kappa")
    k2 = (agreement.get("binary_include_vs_rest") or {}).get("kappa")
    for field in contract:
        low = field.lower()
        if "kappa" not in low:
            continue
        val = result.get(field)
        if not isinstance(val, (int, float)):
            failures.append(f"kappa 字段非数值: {field}")
            continue
        if "binary" in low or "二" in field:
            ref = k2
        elif "three" in low or "三" in field:
            ref = k3
        else:
            ref = k3 if k3 is not None else k2
        if ref is None or not math.isclose(float(val), float(ref),
                                           abs_tol=1e-4):
            failures.append(f"kappa 字段与报告不一致: {field}={val} 报告={ref}")

    # 3. 分歧全仲裁
    arb_ids = {str(a.get("record_id")) for a in arbitrations}
    for d in disagreements:
        if d["record_id"] not in arb_ids:
            failures.append(f"分歧未仲裁: {d['record_id']}")

    # 4. 人工确认门清单一致
    human_ids = {r["record_id"] for r in finals
                 if r.get("human_confirmation_required")}
    for field in contract:
        low = field.lower()
        if "human" in low or "复核" in field:
            val = result.get(field)
            if isinstance(val, list):
                got = ids_from(val)
                if got and got != human_ids:
                    failures.append(
                        f"人工复核清单不一致: {field}={sorted(got)} "
                        f"final_labels={sorted(human_ids)}")
            elif isinstance(val, int) and val != len(human_ids):
                failures.append(f"人工复核计数不一致: {field}={val} "
                                f"实际={len(human_ids)}")

    # 5. 计数字段与闭合
    audit_counts = audit.get("counts", {})
    name_map = {
        "identified": audit_counts.get("identified"),
        "duplicate": audit_counts.get("duplicates_removed"),
        "screened": audit_counts.get("screened"),
        "included": counts.get("included"),
        "excluded": counts.get("excluded"),
        "needs_human": counts.get("needs_human"),
    }
    for field in contract:
        low = field.lower()
        for key, ref in name_map.items():
            if key in low and isinstance(result.get(field), int) and ref is not None:
                if result[field] != ref:
                    failures.append(f"计数字段不一致: {field}={result[field]} "
                                    f"审计={ref}")
    if audit and not audit.get("closed", False):
        failures.append("PRISMA 计数不闭合（见 audit_summary.json）")

    # 6. uncertainty 声明
    for field in contract:
        low = field.lower()
        if "uncertainty" in low or "局限" in field or "limitation" in low:
            val = str(result.get(field, ""))
            if not (("人工" in val and "复核" in val) or "human review" in low + val.lower()):
                failures.append(f"uncertainty 字段未显式声明未经人工复核: {field}")

    if failures:
        for f_ in failures:
            eprint(f"[selfcheck] FAIL: {f_}")
        return 3
    print(f"[selfcheck] 全部通过: 合同字段 {len(contract)} 个已填充、"
          f"kappa 一致、分歧 {len(disagreements)} 条全仲裁、"
          f"人工门 {len(human_ids)} 条一致、计数闭合")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[selfcheck] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
