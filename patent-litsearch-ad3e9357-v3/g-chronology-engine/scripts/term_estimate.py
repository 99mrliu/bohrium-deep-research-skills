#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
term_estimate.py — 法定参考日期“估算”器（带硬性护栏，仅标准库）。

计算内容（全部为估算参考，绝不构成法律状态结论）:
  * 自最早申请日起算的 20 年保护期参考届满日（美国实用新型口径的常见简化推算）；
  * 美国维持费缴费窗口：授权日后 3–3.5 / 7–7.5 / 11–11.5 年（未建模宽限期）。

硬性护栏:
  * 输出 JSON 必含 is_estimate=true、not_legal_status=true、assumptions[]、as_of；
  * 未声明 as_of 一律拒绝运行（退出码 1）；
  * 输出中严禁出现法律状态结论性措辞（如“已失效”“仍受保护”“expired/lapsed/in force”），
    生成后自检，命中即拒绝输出（退出码 1）；
  * --self-test 对上述措辞护栏做显式验证。

用法:
  python3 term_estimate.py --request estimate_request.json [-o OUT.json]
  python3 term_estimate.py --earliest-filing 2019-06-03 --grant-date 2022-04-12 \
      --as-of 2026-11-25 --case-id X
  python3 term_estimate.py --self-test

退出码: 0 正常（估算已生成，且通过措辞自检） / 1 护栏触发或无法计算 / 2 用法错误
"""
import argparse
import calendar
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import date_norm  # noqa: E402

# 法律状态结论性措辞（生成文本中严禁出现；命中即拒绝输出）
FORBIDDEN_WORDING = [
    "已失效", "已经失效", "失效", "已到期", "到期未续", "届满失效",
    "仍然有效", "专利权有效", "处于有效状态", "维持有效", "有效专利",
    "expired", "lapsed", "in force", "enforceable", "no longer valid",
    "still valid", "remains valid",
]

BASE_ASSUMPTIONS = [
    "保护期参考届满日以所给最早申请日为起算点按 20 年简单推算；未考虑优先权链、"
    "分案/继续申请、PTA/PTE（专利期调整/延长）、终端放弃声明（terminal disclaimer）等因素。",
    "维持费窗口按授权日后 3–3.5、7–7.5、11–11.5 年推算；未建模 6 个月宽限期与附加费。",
    "官方登记与法律状态未知；本输出仅为日期推算参考，不构成、也不暗示任何法律状态结论。",
    "默认按美国（US）口径推算；其他法域规则不同，本估算不适用于其他法域。",
    "缴费窗口与届满日均可能因官方行为、缴费事实或程序事件而改变，本脚本不获取、"
    "也不断言任何此类事实。",
]

NOTES = ("All dates below are estimate-only reference dates computed from declared inputs. "
         "Official register status is unknown and is not asserted here. "
         "本输出仅为日期估算参考；官方法律状态未知，须如实说明，不得据此得出任何状态结论。")


def add_years_months(d, years=0, months=0):
    y = d.year + years + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return datetime.date(y, m, day)


def _parse_iso(raw, label, errors):
    if raw is None:
        return None
    res = date_norm.parse_date(str(raw))
    if not res["iso"] or res["precision"] != "day":
        errors.append("无法将 %s=%r 解析为日级精度日期（iso=%r）；拒绝估算。"
                      % (label, raw, res["iso"]))
        return None
    if len(res["interpretations"]) > 1:
        errors.append("%s=%r 存在歧义解释，须先人工判定唯一日期后再估算。" % (label, raw))
        return None
    return datetime.date.fromisoformat(res["iso"])


def scan_forbidden(obj, path="$"):
    """递归扫描输出对象中的所有字符串（含键名），返回 [(path, wording)]。"""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(scan_forbidden(str(k), path + "." + str(k)))
            hits.extend(scan_forbidden(v, path + "." + str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(scan_forbidden(v, "%s[%d]" % (path, i)))
    elif isinstance(obj, str):
        low = obj.lower()
        for w in FORBIDDEN_WORDING:
            if w.lower() in low:
                hits.append((path, w))
    return hits


def build_estimates(case_id, earliest_filing_raw, grant_date_raw, as_of_raw,
                    jurisdiction="US", extra_assumptions=None):
    errors = []
    ef = _parse_iso(earliest_filing_raw, "earliest_filing", errors)
    gd = _parse_iso(grant_date_raw, "grant_date", errors) if grant_date_raw else None
    ao = _parse_iso(as_of_raw, "as_of", errors)
    if errors:
        return None, errors

    estimates = {
        "estimated_20y_term_end": {
            "value": add_years_months(ef, 20).isoformat(),
            "basis": "earliest_filing + 20 years（简化推算）",
            "is_estimate": True,
            "not_legal_status": True,
        },
    }
    if gd:
        windows = []
        for years, label in ((3, "3.5y"), (7, "7.5y"), (11, "11.5y")):
            windows.append({
                "stage": label,
                "window_open": add_years_months(gd, years).isoformat(),
                "window_close": add_years_months(gd, years, 6).isoformat(),
                "basis": "grant_date + %dy / + %dy6m（未建模宽限期）" % (years, years),
                "is_estimate": True,
                "not_legal_status": True,
            })
        estimates["us_maintenance_windows"] = windows
    else:
        estimates["us_maintenance_windows"] = None

    assumptions = list(BASE_ASSUMPTIONS)
    if extra_assumptions:
        assumptions.extend(extra_assumptions)

    return {
        "case_id": case_id,
        "as_of": ao.isoformat(),
        "jurisdiction": jurisdiction,
        "is_estimate": True,
        "not_legal_status": True,
        "assumptions": assumptions,
        "inputs": {
            "earliest_filing": {"raw": earliest_filing_raw, "iso": ef.isoformat()},
            "grant_date": ({"raw": grant_date_raw, "iso": gd.isoformat()}
                           if gd else None),
        },
        "estimates": estimates,
        "notes": NOTES,
        "warnings": ["official legal status unknown — 官方法律状态未知，本输出不断言任何状态。"],
    }, None


def guard_and_emit(result, output_path):
    """措辞护栏：扫描输出，命中禁用措辞则拒绝（返回 1）。"""
    hits = scan_forbidden(result)
    if hits:
        for path, w in hits:
            print("GUARDRAIL: 输出 %s 命中禁用措辞 %r，已拒绝输出。" % (path, w),
                  file=sys.stderr)
        return 1
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    else:
        print(payload)
    return 0


def self_test():
    """显式验证护栏：1) 正常估算通过措辞扫描；2) 注入禁用措辞必被拒绝。"""
    ok = True
    result, errors = build_estimates("SELFTEST-SYN", "2019-06-03", "2022-04-12",
                                     "2026-11-25")
    if errors or result is None:
        print("SELF-TEST FAIL: 正常估算失败: %s" % errors, file=sys.stderr)
        ok = False
    else:
        hits = scan_forbidden(result)
        if hits:
            print("SELF-TEST FAIL: 正常估算输出命中禁用措辞: %s" % hits, file=sys.stderr)
            ok = False
        for key in ("is_estimate", "not_legal_status", "assumptions", "as_of"):
            if key not in result:
                print("SELF-TEST FAIL: 输出缺少护栏字段 %s" % key, file=sys.stderr)
                ok = False
        if not (result.get("is_estimate") is True and result.get("not_legal_status") is True
                and result.get("assumptions")):
            print("SELF-TEST FAIL: 护栏字段取值不正确。", file=sys.stderr)
            ok = False
    poisoned = {"notes": "该专利已失效。"}
    if not scan_forbidden(poisoned):
        print("SELF-TEST FAIL: 注入的禁用措辞未被检出。", file=sys.stderr)
        ok = False
    poisoned2 = {"notes": "The patent has expired."}
    if not scan_forbidden(poisoned2):
        print("SELF-TEST FAIL: 英文禁用措辞未被检出。", file=sys.stderr)
        ok = False
    print("SELF-TEST %s: estimate guardrails verified "
          "(is_estimate / not_legal_status / assumptions / as_of present; "
          "forbidden wording rejected)." % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="法定参考日期估算器（仅估算，非法律状态结论；护栏强制）。")
    ap.add_argument("--request", help="估算请求 JSON：{case_id, earliest_filing, "
                                      "grant_date?, jurisdiction?, as_of, assumptions_extra?}")
    ap.add_argument("--case-id")
    ap.add_argument("--earliest-filing")
    ap.add_argument("--grant-date")
    ap.add_argument("--jurisdiction", default="US")
    ap.add_argument("--as-of", dest="as_of")
    ap.add_argument("-o", "--output")
    ap.add_argument("--self-test", action="store_true", help="验证措辞护栏后退出")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    req = {}
    if args.request:
        try:
            with open(args.request, "r", encoding="utf-8") as f:
                req = json.load(f)
        except (OSError, ValueError) as exc:
            print("ERROR: 无法读取请求文件: %s" % exc, file=sys.stderr)
            return 2

    case_id = args.case_id or req.get("case_id")
    earliest_filing = args.earliest_filing or req.get("earliest_filing")
    grant_date = args.grant_date or req.get("grant_date")
    jurisdiction = args.jurisdiction or req.get("jurisdiction", "US")
    as_of = args.as_of or req.get("as_of")
    extra = req.get("assumptions_extra")

    if not as_of:
        print("ERROR: 必须显式声明 as_of（估算基准日）。未声明一律拒绝运行。", file=sys.stderr)
        return 1
    if not earliest_filing:
        print("ERROR: 缺少 earliest_filing（最早申请日）。", file=sys.stderr)
        return 2

    result, errors = build_estimates(case_id, earliest_filing, grant_date,
                                     as_of, jurisdiction, extra)
    if errors:
        for e in errors:
            print("ERROR: %s" % e, file=sys.stderr)
        return 1
    return guard_and_emit(result, args.output)


if __name__ == "__main__":
    sys.exit(main())
