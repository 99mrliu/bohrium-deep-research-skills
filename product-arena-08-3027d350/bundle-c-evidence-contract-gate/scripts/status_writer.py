#!/usr/bin/env python3
"""status_writer.py — 诚实状态写入器（证据与契约核验技能 C 的组件 4）。

为 result.json 生成/修订运行状态块，强制"未报告、无法判断、材料冲突"
三种情形分开说明（题面硬要求）。不覆盖已有 result 字段，只写状态区。

用法：
    python3 status_writer.py --result /app/output/result.json \
        --status partial \
        --not-reported "原文未报道熔点数据" \
        --cannot-judge "图 3 为图片型表格，无文字层" \
        --conflict "表 1 与正文对产率数值不一致（82 vs 84）" \
        --handoff "需要人工查看第 3 页图 3"
多个 --not-reported/--cannot-judge/--conflict 可重复。
还会把门禁/台账/契约报告（--gate/--coverage/--contract）的摘要对折进
uncertainty，保证报告链一致。退出码 0=写入成功。
"""
import argparse
import json
import os
import sys


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True)
    ap.add_argument("--status", required=True,
                    choices=("success", "partial", "failed"))
    ap.add_argument("--not-reported", action="append", default=[])
    ap.add_argument("--cannot-judge", action="append", default=[])
    ap.add_argument("--conflict", action="append", default=[])
    ap.add_argument("--handoff", action="append", default=[])
    ap.add_argument("--gate", help="gate_report.json（可选，摘要并入）")
    ap.add_argument("--coverage", help="coverage_ledger.json（可选）")
    ap.add_argument("--contract", help="contract_report.json（可选）")
    args = ap.parse_args()

    if not os.path.exists(args.result):
        print(json.dumps({"status": "failed", "reason": "result_missing"}))
        return 3
    result = load_json(args.result)

    boundaries = {}
    if args.not_reported:
        boundaries["not_reported"] = args.not_reported
    if args.cannot_judge:
        boundaries["cannot_judge"] = args.cannot_judge
    if args.conflict:
        boundaries["material_conflict"] = args.conflict

    uncertainty = list(result.get("uncertainty", []))
    for cat, items in boundaries.items():
        for it in items:
            uncertainty.append(f"[{cat}] {it}")
    if args.gate and os.path.exists(args.gate):
        g = load_json(args.gate)
        c = g.get("counts", {})
        if g.get("status") != "pass":
            uncertainty.append(
                f"[quote_gate] 引文门禁未过：{c.get('near_miss', 0)} 近似/"
                f"{c.get('missing', 0)} 缺失/{c.get('violations', 0)} 违规")
    if args.coverage and os.path.exists(args.coverage):
        cov = load_json(args.coverage)
        if cov.get("status") != "balanced":
            uncertainty.append(
                f"[coverage] {cov.get('unaccounted_pct')}% 字符未解释"
                f"（阈值 {cov.get('threshold_pct')}%）")
    if args.contract and os.path.exists(args.contract):
        cr = load_json(args.contract)
        if cr.get("verdict") != "PASS":
            uncertainty.append(
                f"[contract] 契约校验未过：{'；'.join(cr.get('fails', []))}")

    status = args.status
    # 一致性护栏：有任何边界说明或失败信号时，禁止写 success
    degraded = bool(boundaries) or any(
        u.startswith(("[quote_gate]", "[coverage]", "[contract]"))
        for u in uncertainty)
    if status == "success" and degraded:
        status = "partial"

    result["status"] = status
    if uncertainty:
        result["uncertainty"] = uncertainty
    if boundaries:
        # 若 result.result 里已声明 boundaries 契约字段，写入其中
        # （契约校验以 result 载荷为准）；否则写顶层。
        payload = result.get("result")
        if isinstance(payload, dict) and "boundaries" in payload:
            payload["boundaries"] = boundaries
        else:
            result["boundaries"] = boundaries
    if args.handoff:
        result["handoff"] = args.handoff
    result.setdefault("change_record", []).append(
        f"status_writer: status={status}, boundaries={len(boundaries)} 类")

    with open(args.result, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"written": args.result, "status": status,
                      "uncertainty_items": len(uncertainty)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
