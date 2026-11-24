#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patent_numbers.py — 确定性专利号码解析与规范化（库 + CLI）。

覆盖 US / WO(含 PCT 申请) / EP / CN / JP / KR 的公开号、授权号、申请号、
优先权号；另含合成测试国别码 XX（仅用于 fixture，不对应任何真实国家）。

纪律（见 references/number_formats.md 与 references/ocr_boundary.md）：
  - 解析完全确定性：同一输入永远得到同一输出；
  - 歧义（如 7/8 位裸数字、无种类代码的 US 8 位号、无种类代码的 JP/KR 号）
    一律 ok=true + 主解读 + alternatives + 歧义 warning，绝不静默二选一；
  - 无法解析 → ok=false，不猜测、不构造号码；
  - split-glued 模式仅当存在"唯一"边界使两侧均为合法号码时才拆分，
    否则原文保留并给出 warning。

CLI：
  python3 patent_numbers.py normalize "US 10,293,847 B2" "WO2019/123456" ...
  python3 patent_numbers.py split "WO2019/123456US10293847B2" ...
退出码：0 正常；2 用法/输入错误（argparse 默认）。
"""
import argparse
import json
import re
import sys

SYNTHETIC_COUNTRIES = {"XX"}  # 合成测试国别码：仅用于 fixture，不对应真实国家

# ---------------------------------------------------------------- 基础工具

def _clean(text):
    """去逗号与全部空白、转大写；保留数字、字母、'/'、'.'、'-'。"""
    t = str(text).strip().upper()
    t = re.sub(r"[,，]", "", t)
    t = re.sub(r"\s+", "", t)
    return t


def _kind_category(country, kind_code):
    """种类代码 → grant / publication；未识别返回 None。"""
    if not kind_code:
        return None
    if country == "WO":
        return "publication"  # WO 无授权文本
    letter = kind_code[0]
    if letter == "A":
        return "publication"
    if letter in ("B", "C"):
        return "grant"
    if letter in ("U", "Y", "S"):  # CN 实用新型/外观设计等授权类
        return "grant"
    return None


def _mk(kind, country, number, kind_code=None, warnings=None, note=None,
        normalized=None):
    warnings = list(warnings or [])
    if kind_code:
        cat = _kind_category(country, kind_code)
        if cat is None:
            warnings.append("种类代码未识别：%s（保留原上下文类别，需人工核对）"
                            % kind_code)
        elif country not in ("WO",) and kind in ("publication", "grant") \
                and cat != kind:
            # 以种类代码为准修正类别，并显式记录（非静默）
            warnings.append("按种类代码 %s 将类别修正为 %s" % (kind_code, cat))
            kind = cat
        elif cat and kind not in ("publication", "grant"):
            kind = cat
    if normalized is None:
        normalized = country + number + (kind_code or "")
    return {
        "kind": kind,
        "country": country,
        "number": number,
        "kind_code": kind_code,
        "normalized": normalized,
        "warnings": warnings,
        "note": note,
    }

# ---------------------------------------------------------------- 候选生成

def _candidates(raw):
    """返回全部合法解读候选（确定性顺序）。空列表 = 无法解析。"""
    c = _clean(raw)
    out = []
    if not c:
        return out

    # ---- WO 公开号：WO2019/123456 A1 ----
    m = re.fullmatch(r"WO(\d{4})/?(\d{6})([A-Z]\d?)?", c)
    if m:
        warn = [] if m.group(3) else \
            ["缺少种类代码：按公开文本处理，需人工核对"]
        out.append(_mk("publication", "WO", m.group(1) + m.group(2),
                       m.group(3), warn))

    # ---- PCT 申请号：PCT/US2019/012345 ----
    m = re.fullmatch(r"PCT/([A-Z]{2})(\d{4})/?(\d{6})", c)
    if m:
        num = "%s%s/%s" % (m.group(1), m.group(2), m.group(3))
        out.append(_mk("application", "WO", m.group(1) + m.group(2) + m.group(3),
                       None, [], normalized="PCT/" + num))

    # ---- US ----
    m = re.fullmatch(r"US(\d{4})/?(\d{7})([A-Z]\d?)?", c)  # 申请公布 11 位
    if m:
        warn = [] if m.group(3) else \
            ["缺少种类代码：按申请公布（publication）处理，需人工核对"]
        out.append(_mk("publication", "US", m.group(1) + m.group(2),
                       m.group(3), warn))
    m = re.fullmatch(r"US(\d{2})/(\d{6})", c)  # 申请序列号 16/123,456
    if m:
        out.append(_mk("application", "US", m.group(1) + m.group(2)))
    m = re.fullmatch(r"US(\d{7,8})([A-Z]\d?)", c)  # 授权号 + 种类代码
    if m:
        out.append(_mk("grant", "US", m.group(1), m.group(2)))
    m = re.fullmatch(r"US(\d{8})", c)  # 8 位裸号：授权号 vs 申请序列号歧义
    if m:
        out.append(_mk("grant", "US", m.group(1), None,
                         ["缺少种类代码：8 位数字主解读为授权号，需人工核对"]))
        out.append(_mk("application", "US", m.group(1), None,
                       [], note="申请序列号（series/serial）解读"))
    m = re.fullmatch(r"US(\d{7})", c)  # 7 位：2001 年前授权号（无种类代码时代）
    if m:
        out.append(_mk("grant", "US", m.group(1), None,
                         ["缺少种类代码：按 2001 年以前 US 授权号处理，需人工核对"]))

    # ---- EP ----
    m = re.fullmatch(r"EP(\d{7})([A-Z]\d?)?", c)  # 公开/授权 7 位
    if m:
        kind = m.group(2)
        warn = [] if kind else \
            ["缺少种类代码：无法区分公开/授权，需人工核对"]
        cat = _kind_category("EP", kind) or "publication"
        out.append(_mk(cat, "EP", m.group(1), kind, warn))
    m = re.fullmatch(r"EP(\d{8})(?:\.(\d))?", c)  # 申请号 8 位(+校验位)
    if m:
        num = m.group(1)
        norm = "EP" + num + ("." + m.group(2) if m.group(2) else "")
        out.append(_mk("application", "EP", num, None, [], normalized=norm))

    # ---- CN ----
    m = re.fullmatch(r"CN([123]\d{8})([ABUS]\d?)?", c)  # 公开/授权 9 位
    if m:
        kind = m.group(2)
        warn = [] if kind else \
            ["缺少种类代码：无法区分公开/授权/实用新型，需人工核对"]
        cat = _kind_category("CN", kind) or "publication"
        out.append(_mk(cat, "CN", m.group(1), kind, warn))
    m = re.fullmatch(r"CN(\d{12})(?:\.([\dX]))?", c)  # 申请号 12 位(+校验位)
    if m:
        num = m.group(1)
        norm = "CN" + num + ("." + m.group(2) if m.group(2) else "")
        out.append(_mk("application", "CN", num, None, [], normalized=norm))

    # ---- JP ----
    m = re.fullmatch(r"JP([HSR])(\d{2})-?(\d{6})([A-Z]\d?)?", c)  # 年号格式
    if m:
        kind = m.group(4)
        warn = [] if kind else ["缺少种类代码，需人工核对"]
        out.append(_mk("publication", "JP",
                       m.group(1) + m.group(2) + m.group(3), kind, warn))
    m = re.fullmatch(r"JP(\d{4})-?(\d{6})([A-Z]\d?)?", c)  # 公历年+6 位
    if m:
        kind = m.group(3)
        num = m.group(1) + m.group(2)
        if kind:
            out.append(_mk("publication", "JP", num, kind))
        else:
            # 无种类代码：特开公布号 vs 特愿申请号 歧义
            out.append(_mk("publication", "JP", num, None,
                           ["缺少种类代码：主解读为公开号，需人工核对"]))
            out.append(_mk("application", "JP", num, None,
                           [], note="申请号（特願）解读"))
    m = re.fullmatch(r"JP(\d{7})([A-Z]\d?)", c)  # 特许公报 7 位
    if m:
        out.append(_mk("grant", "JP", m.group(1), m.group(2)))
    m = re.fullmatch(r"JP(\d{7})", c)
    if m:
        out.append(_mk("grant", "JP", m.group(1), None,
                       ["缺少种类代码：按授权（特许公报）处理，需人工核对"]))

    # ---- KR ----
    m = re.fullmatch(r"KR(10|20)-?(\d{4})-?(\d{7})([A-Z]\d?)?", c)
    if m:
        kind = m.group(4)
        num = m.group(1) + m.group(2) + m.group(3)
        if kind:
            cat = _kind_category("KR", kind) or "publication"
            out.append(_mk(cat, "KR", num, kind))
        else:
            # 无种类代码：公开号 vs 申请号 歧义
            out.append(_mk("publication", "KR", num, None,
                           ["缺少种类代码：主解读为公开号，需人工核对"]))
            out.append(_mk("application", "KR", num, None,
                           [], note="申请号解读"))
    m = re.fullmatch(r"KR(10|20)-?(\d{7})([A-Z]\d?)", c)  # 授权注册号
    if m:
        out.append(_mk("grant", "KR", m.group(1) + m.group(2), m.group(3)))
    m = re.fullmatch(r"KR(\d{4})-?(\d{7})([A-Z]\d?)?", c)  # 缺 10/20 前缀
    if m:
        kind = m.group(3)
        warn = ["缺少 10/20 前缀：无法区分发明/实用新型，需人工核对"]
        if not kind:
            warn.append("缺少种类代码，需人工核对")
        cat = _kind_category("KR", kind) or "publication"
        out.append(_mk(cat, "KR", m.group(1) + m.group(2), kind, warn))

    # ---- XX（合成测试国别码，不对应真实国家）----
    m = re.fullmatch(r"XX(\d{7})([A-Z]\d?)?", c)
    if m:
        kind = m.group(2)
        warn = ["XX 为合成测试国别码，不对应任何真实国家"]
        if not kind:
            warn.append("缺少种类代码，需人工核对")
        cat = _kind_category("XX", kind) or "publication"
        out.append(_mk(cat, "XX", m.group(1), kind, warn))
    m = re.fullmatch(r"XX(\d{4})/?(\d{6})", c)
    if m:
        num = m.group(1) + "/" + m.group(2)
        out.append(_mk("application", "XX", m.group(1) + m.group(2), None,
                       ["XX 为合成测试国别码，不对应任何真实国家"],
                       normalized="XX" + num))

    # ---- 裸数字（无国别码）----
    m = re.fullmatch(r"(\d{8})", c)
    if m:
        out.append(_mk("grant", "US", m.group(1), None,
                       ["缺少国别码：按 US 授权号主解读，需人工核对"]))
        out.append(_mk("application", "US", m.group(1), None,
                       ["缺少国别码"], note="US 申请序列号解读"))
    m = re.fullmatch(r"(\d{7})", c)
    if m:
        out.append(_mk("grant", "US", m.group(1), None,
                       ["缺少国别码与种类代码：按 2001 年以前 US 授权号处理，"
                        "需人工核对"]))
    return out

# ---------------------------------------------------------------- 对外接口

def normalize_token(raw):
    """规范化单个号码字符串，返回结果 dict（见模块 docstring 纪律）。"""
    cands = _candidates(raw)
    if not cands:
        return {
            "input": raw, "ok": False, "normalized": None, "kind": None,
            "country": None, "number": None, "kind_code": None,
            "warnings": ["无法解析：不猜测、不构造号码，原文保留并记入 uncertainty"],
            "alternatives": [],
        }
    primary = cands[0]
    warnings = list(primary["warnings"])
    if len(cands) > 1:
        warnings.append(
            "AMBIGUOUS 歧义：存在 %d 种合法解读，主解读为 %s（%s/%s）；"
            "未静默二选一，其余解读见 alternatives"
            % (len(cands), primary["normalized"], primary["kind"],
               primary["country"]))
    alternatives = [{
        "normalized": c["normalized"], "kind": c["kind"],
        "country": c["country"], "number": c["number"],
        "kind_code": c["kind_code"],
        "reason": c["note"] or "次优解读",
        "warnings": c["warnings"],
    } for c in cands[1:]]
    return {
        "input": raw, "ok": True,
        "normalized": primary["normalized"], "kind": primary["kind"],
        "country": primary["country"], "number": primary["number"],
        "kind_code": primary["kind_code"],
        "warnings": warnings, "alternatives": alternatives,
    }


def split_glued(raw):
    """OCR 粘连切分：仅当存在唯一边界使两侧均合法时拆分。

    0 个或多于 1 个合法边界 → 不拆分，原文保留 + warning。
    规则详见 references/ocr_boundary.md。
    """
    s = str(raw).strip()
    sols = []
    for i in range(1, len(s)):
        left, right = s[:i], s[i:]
        rl, rr = normalize_token(left), normalize_token(right)
        if rl["ok"] and rr["ok"]:
            sols.append({"boundary": i, "left": rl, "right": rr})
    if len(sols) == 1:
        s0 = sols[0]
        return {
            "input": raw, "ok": True, "boundary": s0["boundary"],
            "split": [s0["left"], s0["right"]], "kept": None,
            "warnings": ["唯一合法边界切分（boundary=%d）" % s0["boundary"]],
        }
    if not sols:
        return {
            "input": raw, "ok": False, "boundary": None, "split": None,
            "kept": raw,
            "warnings": ["切分失败：不存在使两侧均为合法号码的边界；"
                         "原文保留，不猜测"],
        }
    return {
        "input": raw, "ok": False, "boundary": None, "split": None,
        "kept": raw,
        "warnings": ["歧义切分：%d 个边界均合法（boundary=%s），按唯一边界规则"
                     "不拆分，原文保留"
                     % (len(sols),
                        ",".join(str(x["boundary"]) for x in sols))],
        "candidate_boundaries": [x["boundary"] for x in sols],
    }

# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="patent_numbers.py",
        description="确定性专利号码规范化 / OCR 粘连切分（stdlib only）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("normalize", help="规范化一个或多个号码")
    p1.add_argument("numbers", nargs="+")
    p2 = sub.add_parser("split", help="OCR 粘连串的唯一边界切分")
    p2.add_argument("tokens", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd == "normalize":
        result = [normalize_token(x) for x in args.numbers]
    else:
        result = [split_glued(x) for x in args.tokens]
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
