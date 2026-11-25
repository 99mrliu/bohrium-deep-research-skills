#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
date_norm.py — 确定性多格式日期解析与归一化（仅 Python 标准库；正则文法表）。

用法:
  python3 date_norm.py "2018-06-05"
  python3 date_norm.py "Jun. 5, 2018"
  python3 date_norm.py "03/04/2018"                    # 歧义数字日期：两种解释 + 警告
  python3 date_norm.py "2O18-06-05"                    # 默认 keep-raw：保留原文 + 警告
  python3 date_norm.py "2O18-06-05" --ocr-policy fix-digit-confusion

输出 JSON:
  {"raw","iso","precision","format_tag","interpretations","warnings"}

退出码:
  0 解析成功（含歧义情形，歧义绝不静默取舍）
  1 无法解析（保留原文并给出警告，绝不猜测）
  2 用法错误
"""
import argparse
import datetime
import json
import re
import sys

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
MONTH_NAME = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

YEAR_MIN, YEAR_MAX = 1800, 2199

# OCR 数字混淆映射（仅在用户显式声明 fix-digit-confusion 策略时启用）
_CONF = "OoQlIZsSBbGgq|"
_CLS = "0-9" + _CONF
OCR_DIGIT_TRANSLATION = str.maketrans({
    "O": "0", "o": "0", "Q": "0",
    "l": "1", "I": "1", "|": "1",
    "Z": "2", "S": "5", "s": "5",
    "G": "6", "b": "6", "B": "8", "g": "9", "q": "9",
})


def _interp(iso, precision, tag):
    return {"iso": iso, "precision": precision, "format_tag": tag}


def _validate_day(y, m, d):
    if not (YEAR_MIN <= y <= YEAR_MAX):
        return None
    try:
        return datetime.date(y, m, d).isoformat()
    except ValueError:
        return None


def _validate_month(y, m):
    if YEAR_MIN <= y <= YEAR_MAX and 1 <= m <= 12:
        return "%04d-%02d" % (y, m)
    return None


# ---------------------------------------------------------------- 文法构建器
def _b_zh_ymd(m):
    iso = _validate_day(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ([_interp(iso, "day", "zh_ymd")], []) if iso else None


def _b_zh_ym(m):
    iso = _validate_month(int(m.group(1)), int(m.group(2)))
    return ([_interp(iso, "month", "zh_ym")], []) if iso else None


def _b_iso_day(m):
    iso = _validate_day(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ([_interp(iso, "day", "iso8601")], []) if iso else None


def _b_iso_month(m):
    iso = _validate_month(int(m.group(1)), int(m.group(2)))
    return ([_interp(iso, "month", "iso8601_month")], []) if iso else None


def _b_year(m):
    y = int(m.group(1))
    if YEAR_MIN <= y <= YEAR_MAX:
        return ([_interp("%04d" % y, "year", "year_only")], [])
    return None


def _b_us_long(m):
    iso = _validate_day(int(m.group(3)), MONTHS[m.group(1).rstrip(".").lower()],
                        int(m.group(2)))
    return ([_interp(iso, "day", "us_long")], []) if iso else None


def _b_eu_long(m):
    iso = _validate_day(int(m.group(3)), MONTHS[m.group(2).rstrip(".").lower()],
                        int(m.group(1)))
    return ([_interp(iso, "day", "eu_long")], []) if iso else None


def _ambiguous_numeric(raw, first, second, y, sep, primary_order):
    """first/second 为两个数字段。primary_order: 'mdy' 或 'dmy'，决定解释列表的排列先后。"""
    mdy = _validate_day(y, first, second)   # 美式 M/D/Y
    dmy = _validate_day(y, second, first)   # 欧式 D/M/Y
    tag_us = "numeric_%s_us_mdy" % sep
    tag_eu = "numeric_%s_eu_dmy" % sep
    if mdy and dmy:
        warn = ("AMBIGUOUS_NUMERIC_DATE: '%s' 既可按美式 M/D/Y(%s) 也可按欧式 D/M/Y(%s) 解读；"
                "已同时给出两种解释，未做静默取舍，需人工依据来源语境判定。"
                % (raw, mdy, dmy))
        pair = [_interp(mdy, "day", tag_us), _interp(dmy, "day", tag_eu)]
        if primary_order == "dmy":
            pair.reverse()
        return (pair, [warn])
    if mdy:
        warn = ("NUMERIC_DATE_DISAMBIGUATED: '%s' 仅能按美式 M/D/Y 成立"
                "（第二段 %d>12，不可能是月份），仍建议人工复核。" % (raw, second))
        return ([_interp(mdy, "day", tag_us)], [warn])
    if dmy:
        warn = ("NUMERIC_DATE_DISAMBIGUATED: '%s' 仅能按欧式 D/M/Y 成立"
                "（第一段 %d>12，不可能是月份），仍建议人工复核。" % (raw, first))
        return ([_interp(dmy, "day", tag_eu)], [warn])
    return None


def _b_numeric_slash(m):
    return _ambiguous_numeric(m.group(0), int(m.group(1)), int(m.group(2)),
                              int(m.group(3)), "slash", "mdy")


def _b_numeric_dot(m):
    return _ambiguous_numeric(m.group(0), int(m.group(1)), int(m.group(2)),
                              int(m.group(3)), "dot", "dmy")


def _b_compact(m):
    iso = _validate_day(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ([_interp(iso, "day", "compact_yyyymmdd")], []) if iso else None


# 锚定全串解析文法表（顺序即优先级）
GRAMMAR_TABLE = [
    ("zh_ymd", re.compile(r"^(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日$"), _b_zh_ymd),
    ("zh_ym", re.compile(r"^(\d{4})\s*年\s*(\d{1,2})\s*月$"), _b_zh_ym),
    ("iso_day", re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), _b_iso_day),
    ("iso_month", re.compile(r"^(\d{4})-(\d{2})$"), _b_iso_month),
    ("us_long", re.compile(r"^(" + MONTH_NAME + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})$", re.I), _b_us_long),
    ("eu_long", re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+(" + MONTH_NAME + r")\.?\s*,?\s*(\d{4})$", re.I), _b_eu_long),
    ("numeric_slash", re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), _b_numeric_slash),
    ("numeric_dot", re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"), _b_numeric_dot),
    ("compact", re.compile(r"^(\d{4})(\d{2})(\d{2})$"), _b_compact),
    ("year", re.compile(r"^(\d{4})$"), _b_year),
]

# 文本扫描用正则（不锚定；供 event_extract 定位日期子串）
SCAN_GRAMMARS = [
    ("zh_ymd", re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")),
    ("zh_ym", re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月(?!\s*\d+\s*日)")),
    ("iso_day", re.compile(r"\d{4}-\d{2}-\d{2}")),
    ("iso_month", re.compile(r"(?<![\d-])\d{4}-\d{2}(?![\d-])")),
    ("us_long", re.compile(r"(?:" + MONTH_NAME + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{4}", re.I)),
    ("eu_long", re.compile(r"(?<![\w])\d{1,2}(?:st|nd|rd|th)?\s+(?:" + MONTH_NAME + r")\.?\s*,?\s*\d{4}", re.I)),
    ("numeric_slash", re.compile(r"(?<![\d/])\d{1,2}/\d{1,2}/\d{4}(?![\d/])")),
    ("numeric_dot", re.compile(r"(?<![\d.])\d{1,2}\.\d{1,2}\.\d{4}(?![\d.])")),
    ("compact", re.compile(r"(?<!\d)\d{8}(?!\d)")),
    ("year", re.compile(r"(?<![\w])\d{4}(?![\w])")),
    # 疑似 OCR 数字混淆的日期形（至少含一个易混淆字符），兜底保留原文
    ("ocr_suspect", re.compile(
        r"(?<![\w./-])"
        r"(?=[" + _CLS + r"./-]*[" + _CONF + r"])"
        r"[" + _CLS + r"]{3,4}[-/.][" + _CLS + r"]{1,2}[-/.][" + _CLS + r"]{1,4}"
        r"(?![\w])")),
]


def _try_grammars(text):
    for _name, rx, builder in GRAMMAR_TABLE:
        m = rx.match(text.strip())
        if m:
            out = builder(m)
            if out is not None:
                return out
    return None


def _ocr_candidate(text):
    return (bool(re.fullmatch(r"[" + _CLS + r"\s\-/.,年月日]+", text))
            and bool(re.search(r"[" + _CONF + r"]", text)))


def parse_date(raw, ocr_policy="keep-raw"):
    """解析单个日期字符串，返回标准化字典。无法解析时保留原文并告警，绝不猜测。"""
    result = {"raw": raw, "iso": None, "precision": None, "format_tag": "unparsed",
              "interpretations": [], "warnings": []}
    text = raw.strip()
    parsed = _try_grammars(text)
    if parsed is None and ocr_policy == "fix-digit-confusion" and _ocr_candidate(text):
        fixed = text.translate(OCR_DIGIT_TRANSLATION)
        parsed = _try_grammars(fixed)
        if parsed is not None:
            interps, warns = parsed
            for it in interps:
                it["format_tag"] = "ocr_fixed:" + it["format_tag"]
            warns.insert(0, "OCR_DIGIT_CONFUSION_FIXED: 按用户声明的数字混淆策略将 '%s' 视为 '%s' "
                            "后解析成功；该修复仅为工作假设，须人工核对原件。" % (text, fixed))
    if parsed is None:
        result["warnings"].append(
            "UNPARSEABLE_DATE_KEPT_RAW: 无法解析 '%s'，已保留原文，未做任何猜测。" % raw)
        if _ocr_candidate(text):
            result["warnings"].append(
                "SUSPECTED_OCR_DIGIT_CONFUSION: 字符串疑似存在 OCR 数字混淆（如 O/0、l/1、S/5）；"
                "如确认来源为 OCR 扫描件，可显式使用 --ocr-policy fix-digit-confusion。")
        return result
    interps, warns = parsed
    result["interpretations"] = interps
    result["warnings"] = warns
    primary = interps[0]
    result["iso"] = primary["iso"]
    result["precision"] = primary["precision"]
    result["format_tag"] = primary["format_tag"]
    if len(interps) > 1:
        result["format_tag"] = "ambiguous:" + "+".join(sorted({i["format_tag"] for i in interps}))
    return result


def iter_date_candidates(text, ocr_policy="keep-raw"):
    """在自由文本中扫描日期候选，返回 [{raw, span, ...parse_date 字段}]，按出现顺序。

    重叠匹配按“起点优先、同起点长者优先、文法表顺序优先”去重。
    仅保留：解析成功的候选；或来自 ocr_suspect 文法的候选（保留原文 + 告警）。
    """
    scan_text = text.translate(OCR_DIGIT_TRANSLATION) if ocr_policy == "fix-digit-confusion" else text
    found = []
    for order, (name, rx) in enumerate(SCAN_GRAMMARS):
        for m in rx.finditer(scan_text):
            found.append((m.start(), m.end(), order, name))
    found.sort(key=lambda t: (t[0], -(t[1] - t[0]), t[2]))
    chosen, last_end = [], -1
    for s, e, order, name in found:
        if s >= last_end:
            chosen.append((s, e, name))
            last_end = e
    out = []
    for s, e, name in chosen:
        raw = text[s:e]  # 逐字原文（OCR 修复只做解析假设，不改写原文）
        parsed = parse_date(raw, ocr_policy)
        if parsed["iso"] is None and name != "ocr_suspect":
            continue  # 例如 "SYN-PUB-0001" 中的 0001：非日期，直接跳过
        parsed["span"] = [s, e]
        out.append(parsed)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="确定性多格式日期解析与归一化（仅标准库）。")
    ap.add_argument("date_string", help="待解析的日期字符串（逐字原文）")
    ap.add_argument("--ocr-policy", choices=["keep-raw", "fix-digit-confusion"],
                    default="keep-raw",
                    help="OCR 数字混淆策略；默认 keep-raw（保留原文并告警）。")
    args = ap.parse_args(argv)
    res = parse_date(args.date_string, args.ocr_policy)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["iso"] else 1


if __name__ == "__main__":
    sys.exit(main())
