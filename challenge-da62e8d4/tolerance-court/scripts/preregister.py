#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preregister.py — 事前容差注册（tolerance pre-registration）

在任何候选方法运行【之前】执行，把每个待核对指标的容差机械地推导出来并落盘。
看到结果之后再写/改容差属于事后篡改（见 references/tolerance.md 常见作弊模式）。

用法：
    python3 preregister.py --targets targets.json --out tolerances.json [--k 1.0] \
        [--rationale "理由"] [--force [--force-reason "原因"]]

targets.json：JSON 数组，每个元素：
    name           指标名（字符串）
    paper_value    论文报告值原文（字符串，如 "0.152" / "72.1" / "1.2e3" / "1200"）；论文未报告则为 null
    unit           单位（字符串，可空）
    case_tolerance 案例给定容差（数值或 null）；非 null 时逐字优先采用
    aggregation    "mean" | "median" | "single"
    kind           "deterministic" | "stochastic"

输出 tolerances.json：
    created_at       UTC ISO 时间戳
    targets_sha256   输入 targets 的规范化 JSON 的 SHA-256（防事后调换输入）
    k                随机指标容差放大倍数
    change_records   --force 覆盖旧文件时的变更记录（含旧文件 sha256）
    items[]          每项：name / paper_value / unit / aggregation / kind /
                     tolerance_abs（绝对容差）/ tolerance_rel（相对容差）/
                     derivation（case_given | half_ulp | none）/ reason（推导理由原文）/
                     k_applied / rationale（k>1 时必须有）

容差推导规则：
  1. case_tolerance 非空 → 逐字照抄，derivation=case_given。
  2. 否则按 paper_value 的书写有效数字推“四舍五入半单位”（half ulp）：
       - 含小数点：小数位 d 位 → 半单位 = 0.5 × 10^(-d)，如 "0.152"→±0.0005，"72.1"→±0.05
       - 科学计数法 "m×10^e"：按尾数小位数与指数合成，如 "1.2e3"→±50
       - 无小数点整数：按书写最后一位（个位）为有效位，如 "1200"→±0.5
       （整数末尾零是否有效存在歧义；本工具按书写位数规则取最保守口径，
         若论文另说明有效位数，应改用 case_tolerance 显式登记。）
  3. paper_value 为 null → 无法推容差，derivation=none，裁决时判 not_comparable。
  4. kind=stochastic 且 --k>1 → 容差 ×= k，必须经 --rationale 写下放大理由。

退出码：0 成功；2 参数/结构错误（含拒绝覆盖）。
仅使用 Python3 标准库。
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal

_NUM_RE = re.compile(r"^[+-]?(\d+(?:\.\d+)?)(?:[eE]([+-]?\d+))?$")

AGGREGATIONS = {"mean", "median", "single"}
KINDS = {"deterministic", "stochastic"}


def fail(msg):
    print(f"[preregister] ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def half_ulp(value_str):
    """按书写有效数字推导四舍五入半单位容差（返回 (Decimal, 说明字符串)）。"""
    s = str(value_str).strip()
    m = _NUM_RE.match(s)
    if not m:
        fail(f"paper_value {value_str!r} 不是可解析的数值字符串")
    mantissa, exp_s = m.group(1), m.group(2)
    exp = int(exp_s) if exp_s else 0
    decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
    # ulp = 10^(exp - decimals)；半单位 = 5 × 10^(exp - decimals - 1)
    half = Decimal(5) * (Decimal(10) ** (exp - decimals - 1))
    if exp_s is not None:
        how = f"科学计数法：尾数 {mantissa}（{decimals} 位小数）×10^{exp}，半单位=5×10^{exp - decimals - 1}"
    elif decimals > 0:
        how = f"小数 {decimals} 位，半单位=0.5×10^-{decimals}"
    else:
        how = "无小数点整数：按书写最后一位（个位）为有效位，半单位=0.5"
    return half, how


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser(description="事前容差注册：先写容差，再跑方法。")
    ap.add_argument("--targets", required=True, help="targets.json 路径")
    ap.add_argument("--out", required=True, help="输出 tolerances.json 路径")
    ap.add_argument("--k", type=float, default=1.0,
                    help="stochastic 指标容差放大倍数（默认 1，即不放大）")
    ap.add_argument("--rationale", default="",
                    help="k>1 时必须填写的放大理由")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已存在的容差文件（会记录旧文件 sha256）")
    ap.add_argument("--force-reason", default="", help="--force 覆盖的原因说明")
    args = ap.parse_args()

    try:
        with open(args.targets, "r", encoding="utf-8") as f:
            targets = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail(f"无法读取 targets：{e}")
    if not isinstance(targets, list) or not targets:
        fail("targets.json 必须是非空 JSON 数组")

    if args.k <= 0:
        fail("--k 必须为正数")
    if args.k != 1.0 and not args.rationale.strip():
        fail("k≠1 时必须用 --rationale 写下放大理由（防事后篡改）")

    items = []
    for i, t in enumerate(targets):
        if not isinstance(t, dict):
            fail(f"targets[{i}] 不是对象")
        name = t.get("name")
        if not name or not isinstance(name, str):
            fail(f"targets[{i}].name 缺失或非字符串")
        agg = t.get("aggregation", "median")
        kind = t.get("kind", "deterministic")
        if agg not in AGGREGATIONS:
            fail(f"targets[{i}] ({name}) aggregation 非法：{agg!r}")
        if kind not in KINDS:
            fail(f"targets[{i}] ({name}) kind 非法：{kind!r}")

        paper_raw = t.get("paper_value", None)
        case_tol = t.get("case_tolerance", None)
        paper_num = None
        if paper_raw is not None:
            m = _NUM_RE.match(str(paper_raw).strip())
            if not m:
                fail(f"targets[{i}] ({name}) paper_value {paper_raw!r} 不可解析")
            paper_num = float(str(paper_raw).strip())

        entry = {
            "name": name,
            "paper_value": paper_raw,
            "paper_value_num": paper_num,
            "unit": t.get("unit", ""),
            "aggregation": agg,
            "kind": kind,
            "k_applied": 1.0,
            "rationale": "",
        }

        if case_tol is not None:
            try:
                tol = float(case_tol)
            except (TypeError, ValueError):
                fail(f"targets[{i}] ({name}) case_tolerance {case_tol!r} 不是数值")
            if tol < 0:
                fail(f"targets[{i}] ({name}) case_tolerance 不能为负")
            entry["derivation"] = "case_given"
            entry["reason"] = f"案例给定容差，逐字照抄：±{case_tol}"
            tol_dec = Decimal(repr(tol))
        elif paper_num is None:
            entry["derivation"] = "none"
            entry["reason"] = "论文未报告数值（或仅给图）：无法推容差，裁决判 not_comparable，不得编造"
            tol_dec = None
        else:
            half, how = half_ulp(paper_raw)
            entry["derivation"] = "half_ulp"
            entry["reason"] = f"四舍五入半单位推导（{how}）：±{half}"
            tol_dec = half

        if tol_dec is not None and kind == "stochastic" and args.k != 1.0:
            tol_dec = tol_dec * Decimal(repr(args.k))
            entry["k_applied"] = args.k
            entry["rationale"] = args.rationale.strip()
            entry["reason"] += f"；stochastic 指标按 k={args.k} 放大，理由：{args.rationale.strip()}"

        if tol_dec is None:
            entry["tolerance_abs"] = None
            entry["tolerance_rel"] = None
        else:
            tol_f = float(tol_dec)
            entry["tolerance_abs"] = tol_f
            entry["tolerance_rel"] = (abs(tol_f / paper_num)
                                      if paper_num not in (None, 0) else None)
        items.append(entry)

    targets_sha = hashlib.sha256(
        json.dumps(targets, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    doc = {
        "_schema": "tolerance-court/tolerances/v1",
        "created_at": utc_now(),
        "targets_sha256": targets_sha,
        "k": args.k,
        "change_records": [],
        "items": items,
    }

    import os
    if os.path.exists(args.out):
        if not args.force:
            fail(f"{args.out} 已存在：拒绝覆盖（容差先写后跑，确需重建请显式 --force 并留痕）")
        with open(args.out, "rb") as f:
            old_sha = hashlib.sha256(f.read()).hexdigest()
        doc["change_records"].append({
            "action": "overwrite",
            "old_file_sha256": old_sha,
            "at": utc_now(),
            "reason": args.force_reason or "（未填写原因）",
        })

    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        fail(f"无法写出 {args.out}：{e}")

    print(f"[preregister] 已注册 {len(items)} 项容差 → {args.out}")
    for it in items:
        tol = "N/A" if it["tolerance_abs"] is None else f"±{it['tolerance_abs']}"
        print(f"  - {it['name']}: paper={it['paper_value']} {tol} [{it['derivation']}]")
    sys.exit(0)


if __name__ == "__main__":
    main()
