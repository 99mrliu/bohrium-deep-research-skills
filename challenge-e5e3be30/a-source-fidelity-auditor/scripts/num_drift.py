#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""num_drift.py — 数值漂移机检

抽取论断文本与证据 quote 中的全部数值，比对"论断里的每个数字是否被
所引原文支持"。覆盖：百分数、小数、科学计数法、中文数字（百分之三十）。

等价归一（canonicalization）
---------------------------
- 30% ≡ 0.30 ≡ 30 percent ≡ 百分之三十（统一折算为小数比值）
- 3e5 ≡ 300000
- 普通数值按浮点比较（相对容差 REL_TOL=1e-9）

判定
----
- 论断数值在证据 quote 中存在等价值 → ok
- 不存在 → missing_in_quote（ERROR：可能为 unsupported extrapolation 或编造）
- 存在近似但不相等的值（如论断 78.2% vs 原文 78%）→ value_mismatch（ERROR：四舍五入改写）

退出码：0 无漂移；1 有漂移或输入损坏；2 用法错误。
"""

import argparse
import json
import os
import re
import sys

REL_TOL = 1e-9
NEAR_TOL = 0.05  # value_mismatch 判定的相对距离上限（超过即视为无关数字）

CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000}

# (?<![\w.])         排除紧跟在字母/数字/下划线/小数点后的数字（如 CO2、SO2）
# (?<![A-Za-z0-9]-)  排除连字符标识符的尾部数字（如 NFO-700、EXMP-2024 中的 700/2024）
LATIN_NUM_RE = re.compile(
    r"(?<![\w.])(?<![A-Za-z0-9]-)(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"\s*(%|percent|per\s*cent|个百分点|‰)?")
CN_PCT_RE = re.compile(r"百分之([零一二两三四五六七八九十百千万]+(?:点[零一二两三四五六七八九]+)?)")


def parse_cn_int(s):
    """解析 '三十'/'一百二' 形式的中文整数。"""
    total, section, num = 0, 0, 0
    for ch in s:
        if ch in CN_DIGIT:
            num = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            u = CN_UNIT[ch]
            if u == 10000:
                section = (section + num) * u
                total += section
                section, num = 0, 0
            else:
                section += (num if num else 1) * u
                num = 0
    return total + section + num


def parse_cn_pct(body):
    if "点" in body:
        intp, frac = body.split("点", 1)
        val = parse_cn_int(intp)
        frac_val = sum(CN_DIGIT[c] * 10 ** -(i + 1) for i, c in enumerate(frac))
        return (val + frac_val) / 100.0
    return parse_cn_int(body) / 100.0


def extract_numbers(text):
    """返回 [(raw, canonical_value)]。canonical 把百分数折算为小数。"""
    out = []
    if not text:
        return out
    spans = []
    for m in LATIN_NUM_RE.finditer(text):
        raw = m.group(1)
        unit = m.group(2)
        try:
            v = float(raw)
        except ValueError:
            continue
        if unit:
            if unit == "‰":
                v /= 1000.0
            else:
                v /= 100.0  # % / percent / 个百分点 均归一为比值
        out.append((m.group(0).strip(), v))
        spans.append(m.span())
    for m in CN_PCT_RE.finditer(text):
        try:
            v = parse_cn_pct(m.group(1))
        except KeyError:
            continue
        out.append((m.group(0), v))
    return out


def is_equiv(a, b):
    return abs(a - b) <= REL_TOL * max(1.0, abs(a), abs(b))


def iter_claims(obj):
    """递归产出 (claim_id, claim_text)。约定字段 claim_id + text/claim/claim_text。"""
    if isinstance(obj, dict):
        cid = obj.get("claim_id")
        for key in ("claim_text", "text", "claim"):
            if cid and isinstance(obj.get(key), str) and obj[key].strip():
                yield cid, obj[key]
                break
        for v in obj.values():
            yield from iter_claims(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_claims(v)


def iter_quotes(obj, claim_id=None):
    """递归产出 (claim_id, quote)。与 quote_audit.py 的证据约定一致。"""
    if isinstance(obj, dict):
        cid = obj.get("claim_id", claim_id)
        if isinstance(obj.get("quote"), str) and obj["quote"].strip():
            yield cid, obj["quote"]
        for k, v in obj.items():
            if k != "quote":
                yield from iter_quotes(v, cid)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_quotes(v, claim_id)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="数值漂移机检：论断中的数值是否被所引原文 quote 支持",
        epilog="退出码：0 无漂移；1 有漂移或输入损坏；2 用法错误。",
    )
    ap.add_argument("--claims", "-c", required=True,
                    help="论断 JSON（含 claim_id 与 text/claim/claim_text 的对象列表）")
    ap.add_argument("--result", "-r", default=None,
                    help="result.json（从其 evidence quote 中按 claim_id 取证据）")
    ap.add_argument("--quotes", "-q", default=None,
                    help="或直接给 quote 清单 JSON：[{claim_id, quote}, ...]")
    ap.add_argument("--output", "-o", default="num-drift.json",
                    help="漂移报告输出路径（默认 ./num-drift.json）")
    args = ap.parse_args(argv)

    if (args.result is None) == (args.quotes is None):
        print("错误：--result 与 --quotes 必须且只能给一个。", file=sys.stderr)
        return 2
    for pth in [args.claims, args.result or args.quotes]:
        if not os.path.isfile(pth):
            print(f"错误：文件不存在：{pth}", file=sys.stderr)
            return 1
    try:
        claims_doc = load_json(args.claims)
        quotes_doc = load_json(args.result or args.quotes)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"错误：JSON 解析失败：{e}", file=sys.stderr)
        return 1

    claims = list(iter_claims(claims_doc))
    quotes_by_claim = {}
    for cid, q in iter_quotes(quotes_doc):
        if cid is not None:
            quotes_by_claim.setdefault(str(cid), []).append(q)

    drift, checked, no_evidence = [], 0, []
    for cid, text in claims:
        cid = str(cid)
        claim_nums = extract_numbers(text)
        qs = quotes_by_claim.get(cid, [])
        if not qs:
            if claim_nums:
                no_evidence.append({"claim_id": cid,
                                    "reason": "该论断无任何 evidence quote，数值无法机检"})
            continue
        quote_nums = []
        for q in qs:
            quote_nums.extend(extract_numbers(q))
        checked += 1
        for raw, v in claim_nums:
            if any(is_equiv(v, qv) for _, qv in quote_nums):
                continue
            # 找最近的 quote 数值，判断是否属于"改写漂移"
            nearest = None
            for qraw, qv in quote_nums:
                d = abs(v - qv) / max(1e-12, abs(qv))
                if nearest is None or d < nearest[2]:
                    nearest = (qraw, qv, d)
            if nearest and nearest[2] <= NEAR_TOL:
                drift.append({
                    "claim_id": cid, "kind": "value_mismatch",
                    "claim_number": raw, "claim_value": v,
                    "quote_number": nearest[0], "quote_value": nearest[1],
                    "relative_diff": round(nearest[2], 6),
                    "message": "论断数值与原文接近但不相等：疑似四舍五入改写/誊抄漂移",
                })
            else:
                drift.append({
                    "claim_id": cid, "kind": "missing_in_quote",
                    "claim_number": raw, "claim_value": v,
                    "message": "论断数值未出现在所引 quote 中：疑似外推或来源不明",
                })

    report = {
        "generator": "num_drift.py",
        "inputs": {"claims": os.path.abspath(args.claims),
                   "quotes_source": os.path.abspath(args.result or args.quotes)},
        "summary": {"claims": len(claims), "claims_with_evidence": checked,
                    "claims_without_evidence": len(no_evidence),
                    "drift_items": len(drift)},
        "drift": drift,
        "no_evidence": no_evidence,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[num_drift] 论断={len(claims)} 有证据={checked} 漂移项={len(drift)} → {args.output}")
    for d in drift:
        print(f"  [DRIFT:{d['kind']}] claim={d['claim_id']} "
              f"论断数值={d['claim_number']} → {d['message']}"
              + (f"（原文最近值：{d.get('quote_number')}）" if d["kind"] == "value_mismatch" else ""))
    for ne in no_evidence:
        print(f"  [NO-EVIDENCE] claim={ne['claim_id']} {ne['reason']}")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
