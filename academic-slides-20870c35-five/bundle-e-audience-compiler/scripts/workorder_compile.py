#!/usr/bin/env python3
"""workorder_compile.py — 把工作订单编译为 talk_spec.json（听众-时长-叙事契约）。

从 case.json 的结构化字段与 task.md 的自由文本中抽取六个工作订单字段：

    audience / duration_min / slide_count / venue / language / goal

并推导定量杠杆（levers）：

    - 背景比例带 background_ratio_band（按听众类型；依据见 references/audience-levers.md）
    - 结论位置规则 conclusion_position（按汇报场合；依据见 references/narrative-spines.md）
    - 语速模型 time_model（Latin 词/分钟 wpm 与 CJK 字/分钟 cjk_cpm，均可命令行覆盖）
    - 每页时间预算 per_slide_seconds = duration_seconds / slide_count_nominal
    - 总时长带 total_time_band_seconds = [0.85, 1.15] × duration_seconds

抽取策略：先在 case.json 中递归按字段别名做结构化抽取；抽不到再用 task.md
文本正则/关键词；仍抽不到则该字段写 "TO_FILL"，并在 assumptions 中记录本次
推导所使用的默认值与理由。绝不静默编造取值；结构化值与文本值冲突时以结构化
为准并记录冲突。

正则与关键词表（文本后备，忽略大小写）：

    时长      r"(\\d{1,3})\\s*(?:minutes?|mins?|分钟)"
    页数区间  r"(\\d{1,2})\\s*(?:-|–|—|~|to)\\s*(\\d{1,2})\\s*(?:slides?|页)"
    页数      r"(?:exactly\\s+)?(\\d{1,2})\\s*(?:slides?|页)"
    听众      AUDIENCE_RULES 顺序匹配（specialist → general → mixed）
    场合      VENUE_RULES 顺序匹配（defense → group_meeting → review，
              因为答辩/组会文本常同时含 review 字样）
    语言      LANGUAGE_RULES；关键词缺失时退化为 task.md 的 CJK 字符占比启发式
    目标      r"(?im)^\\s*(?:goal|objective|目标)[:：]\\s*(.+)$"

退出码：0 成功（含存在 TO_FILL 的情形，TO_FILL 是正常输出而非错误）；
        2 用法 / IO / JSON 解析错误。
"""
import argparse
import json
import os
import re
import sys

SCHEMA = "talk_spec/1.0"

# ---- 受控词表 -------------------------------------------------------------
AUDIENCE_TYPES = ("specialist", "mixed", "general")
VENUE_TYPES = ("review", "defense", "group_meeting", "generic")

# ---- 抽取正则（文本后备；文档见模块 docstring） -----------------------------
RE_DURATION = re.compile(r"(\d{1,3})\s*(?:minutes?|mins?|分钟)", re.IGNORECASE)
RE_SLIDES_RANGE = re.compile(
    r"(\d{1,2})\s*(?:-|–|—|~|\bto\b)\s*(\d{1,2})\s*(?:slides?|页)", re.IGNORECASE)
RE_SLIDES_EXACT = re.compile(
    r"(?:exactly\s+)?(\d{1,2})\s*(?:slides?|页)", re.IGNORECASE)
RE_GOAL_LINE = re.compile(r"(?im)^\s*(?:goal|objective|目标)\s*[:：]\s*(.+)$")
RE_CJK = re.compile(r"[㐀-䶿一-鿿]")

AUDIENCE_RULES = [
    ("specialist", [r"\bspecialists?\b", r"\bexpert audience\b",
                    r"同行专家", r"领域专家", r"专家评审组"]),
    ("general", [r"\bgeneral audience\b", r"\blay audience\b",
                 r"\bthe public\b", r"大众听众", r"公众", r"科普"]),
    ("mixed", [r"\bmixed\b", r"评审委员会", r"\breview committee\b",
               r"混合听众", r"交叉学科"]),
]

VENUE_RULES = [
    ("defense", [r"\bdefen[cs]e\b", r"答辩", r"毕业设计汇报"]),
    ("group_meeting", [r"\bgroup\s*meeting\b", r"\blab\s*meeting\b",
                       r"\bjournal\s*club\b", r"组会", r"例会", r"课题组会"]),
    ("review", [r"\breview\b", r"\bproposal\b", r"评审", r"基金申请", r"开题"]),
]

LANGUAGE_RULES = [
    ("zh", [r"\bchinese\b", r"\bmandarin\b", r"中文", r"汉语"]),
    ("en", [r"\benglish\b", r"英文", r"英语"]),
]

# case.json 结构化字段别名（小写匹配）
KEY_ALIASES = {
    "audience": ("audience", "audience_type", "listeners", "target_audience", "听众"),
    "duration_min": ("duration_min", "duration", "minutes", "talk_minutes",
                     "time_limit_min", "时长"),
    "slide_count": ("slide_count", "slides", "num_slides", "n_slides",
                    "max_slides", "页数"),
    "venue": ("venue", "occasion", "talk_type", "presentation_type", "场合"),
    "language": ("language", "lang", "talk_language", "语言"),
    "goal": ("goal", "objective", "talk_goal", "任务目标", "目标"),
}

# ---- 推导杠杆常数（依据见 references/audience-levers.md） -------------------
BACKGROUND_BANDS = {
    "specialist": (0.05, 0.15),
    "mixed": (0.15, 0.30),
    "general": (0.30, 0.45),
}
VENUE_RULE_SPECS = {
    "review": {
        "rule": "conclusion_first",
        "detail": ("结论先行：首个 conclusion 角色页的 0 基序号须 ≤ ceil(n_main/3)，"
                   "即结论头条落在前约 1/3 内（含一页容差）。"),
    },
    "defense": {
        "rule": "limitations_before_conclusion",
        "detail": "答辩：必须存在 limitation 角色页，且其首次出现早于首个 conclusion 页。",
    },
    "group_meeting": {
        "rule": "methods_progress_emphasis",
        "detail": "组会：方法与进度为主，结论位置不设硬约束（门控仅查主干顺序）。",
    },
    "generic": {
        "rule": "standard_spine",
        "detail": "场合未知：仅施加 problem<approach<result<conclusion 主干顺序约束。",
    },
}

DEFAULT_WPM = 130            # 学术英语讲演语速（references/audience-levers.md §3）
DEFAULT_CJK_CPM = 240        # 中文字/分钟
DEFAULT_MIN_SLIDE_SECONDS = 20
DEFAULT_DURATION_MIN = 10
DEFAULT_AUDIENCE = "mixed"
DEFAULT_VENUE = "generic"
DEFAULT_LANGUAGE = "en"
TIME_BAND = (0.85, 1.15)


def load_text(path, what):
    if not os.path.isfile(path):
        print("[ERROR] %s 不存在：%s" % (what, path), file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        print("[ERROR] %s 读取失败：%s" % (what, exc), file=sys.stderr)
        sys.exit(2)


def load_json(path, what):
    text = load_text(path, what)
    try:
        return json.loads(text)
    except ValueError as exc:
        print("[ERROR] %s JSON 解析失败：%s" % (what, exc), file=sys.stderr)
        sys.exit(2)


def deep_find(obj, aliases, path="$"):
    """递归在 case.json 中按字段别名找值；返回 (value, jsonpath) 或 (None, None)。"""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if str(key).lower() in aliases and not isinstance(val, list):
                return val, "%s.%s" % (path, key)
        for key, val in obj.items():
            if isinstance(val, (dict, list)):
                hit = deep_find(val, aliases, "%s.%s" % (path, key))
                if hit[0] is not None:
                    return hit
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            if isinstance(val, (dict, list)):
                hit = deep_find(val, aliases, "%s[%d]" % (path, i))
                if hit[0] is not None:
                    return hit
    return None, None


def match_rules(text, rules):
    for value, patterns in rules:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return value, "task.md:/%s/" % pat
    return None, None


def norm_audience(raw):
    s = str(raw).strip().lower()
    if s in AUDIENCE_TYPES:
        return s
    val, _ = match_rules(s, AUDIENCE_RULES)
    return val


def norm_venue(raw):
    s = str(raw).strip().lower()
    if s in VENUE_TYPES:
        return s
    val, _ = match_rules(s, VENUE_RULES)
    return val


def norm_language(raw):
    s = str(raw).strip().lower()
    if s in ("en", "zh"):
        return s
    val, _ = match_rules(s, LANGUAGE_RULES)
    return val


def parse_duration(raw):
    if isinstance(raw, (int, float)) and 1 <= raw <= 600:
        return int(raw)
    m = RE_DURATION.search(str(raw))
    return int(m.group(1)) if m else None


def parse_slide_count(raw):
    """返回 (min, max) 或 None。"""
    if isinstance(raw, int) and 1 <= raw <= 200:
        return (raw, raw)
    if isinstance(raw, dict):
        lo, hi = raw.get("min"), raw.get("max")
        if isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi <= 200:
            return (lo, hi)
        return None
    s = str(raw)
    m = RE_SLIDES_RANGE.search(s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return (lo, hi)
    m = RE_SLIDES_EXACT.search(s)
    if m:
        return (int(m.group(1)), int(m.group(1)))
    return None


def extract_field(name, case, task_text, normalizer, text_extractor):
    """结构化优先，文本后备；返回 (norm_value, status, source, text_value_or_None)。"""
    raw, jpath = deep_find(case, KEY_ALIASES[name])
    if raw is not None:
        val = normalizer(raw) if normalizer else str(raw).strip()
        if val:
            src = "case.json:%s" % jpath
            tval = text_extractor(task_text) if text_extractor else None
            return val, "extracted", src, tval
    tval = text_extractor(task_text) if text_extractor else None
    if tval:
        return tval, "extracted", "task.md:text", None
    return None, "missing", None, None


def main():
    ap = argparse.ArgumentParser(
        description="编译工作订单为 talk_spec.json（听众-时长-叙事契约）")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--task", default="/input/task.md", help="task.md 路径")
    ap.add_argument("--output", default="/app/work/talk_spec.json",
                    help="talk_spec.json 输出路径")
    ap.add_argument("--wpm", type=int, default=DEFAULT_WPM,
                    help="Latin 语速（词/分钟，默认 %d）" % DEFAULT_WPM)
    ap.add_argument("--cjk-cpm", type=int, default=DEFAULT_CJK_CPM,
                    help="CJK 语速（字/分钟，默认 %d）" % DEFAULT_CJK_CPM)
    ap.add_argument("--min-slide-seconds", type=int,
                    default=DEFAULT_MIN_SLIDE_SECONDS,
                    help="每页最小讲述秒数下限（默认 %d）"
                    % DEFAULT_MIN_SLIDE_SECONDS)
    args = ap.parse_args()

    case = load_json(args.case, "case.json")
    task_text = load_text(args.task, "task.md")
    synthetic = bool(isinstance(case, dict) and case.get("synthetic"))

    assumptions = []

    # ---- audience ---------------------------------------------------------
    aud, aud_status, aud_src, aud_text = extract_field(
        "audience", case, task_text, norm_audience,
        lambda t: match_rules(t, AUDIENCE_RULES)[0])
    if aud is None:
        aud = DEFAULT_AUDIENCE
        aud_status = "TO_FILL"
        assumptions.append({
            "field": "audience", "assumed": DEFAULT_AUDIENCE,
            "reason": "未能从 case.json/task.md 抽取听众类型；按 mixed（混合听众）"
                      "推导背景比例带，请人工确认。"})
    elif aud_text and norm_audience(aud_text) and norm_audience(aud_text) != aud:
        assumptions.append({
            "field": "audience", "assumed": aud,
            "reason": "结构化值 %r 与文本值 %r 冲突，以结构化为准。"
                      % (aud, norm_audience(aud_text))})

    # ---- duration_min -----------------------------------------------------
    dur, dur_status, dur_src, dur_text = extract_field(
        "duration_min", case, task_text, parse_duration,
        lambda t: (int(RE_DURATION.search(t).group(1))
                   if RE_DURATION.search(t) else None))
    if dur is None:
        dur = DEFAULT_DURATION_MIN
        dur_status = "TO_FILL"
        assumptions.append({
            "field": "duration_min", "assumed": DEFAULT_DURATION_MIN,
            "reason": "未抽取到时长；按默认 %d 分钟推导时间预算，请人工确认。"
                      % DEFAULT_DURATION_MIN})

    # ---- slide_count ------------------------------------------------------
    sc, sc_status, sc_src, _ = extract_field(
        "slide_count", case, task_text, parse_slide_count,
        lambda t: parse_slide_count(t))
    if sc is None:
        guess = max(1, int(round(dur)))
        sc = (guess, guess)
        sc_status = "TO_FILL"
        assumptions.append({
            "field": "slide_count", "assumed": guess,
            "reason": "未抽取到页数；按“约 1 页/分钟”启发式取 %d 页，请人工确认。"
                      % guess})

    # ---- venue ------------------------------------------------------------
    ven, ven_status, ven_src, _ = extract_field(
        "venue", case, task_text, norm_venue,
        lambda t: match_rules(t, VENUE_RULES)[0])
    if ven is None:
        ven = DEFAULT_VENUE
        ven_status = "TO_FILL"
        assumptions.append({
            "field": "venue", "assumed": DEFAULT_VENUE,
            "reason": "未抽取到汇报场合；按 generic（无场合特化规则）推导，"
                      "门控仅施加主干顺序约束，请人工确认。"})

    # ---- language ---------------------------------------------------------
    lang, lang_status, lang_src, _ = extract_field(
        "language", case, task_text, norm_language,
        lambda t: match_rules(t, LANGUAGE_RULES)[0])
    if lang is None:
        cjk = len(RE_CJK.findall(task_text))
        latin = max(1, len(re.findall(r"[A-Za-z]+", task_text)))
        lang = "zh" if cjk > 0.15 * latin else DEFAULT_LANGUAGE
        lang_status = "TO_FILL"
        assumptions.append({
            "field": "language", "assumed": lang,
            "reason": "未抽取到语言；按 task.md 的 CJK 字符占比启发式判为 %s，"
                      "请人工确认。" % lang})

    # ---- goal -------------------------------------------------------------
    goal, goal_status, goal_src, _ = extract_field(
        "goal", case, task_text, None,
        lambda t: (RE_GOAL_LINE.search(t).group(1).strip()
                   if RE_GOAL_LINE.search(t) else None))
    if goal is None or not str(goal).strip():
        goal = "TO_FILL"
        goal_status = "TO_FILL"
        assumptions.append({
            "field": "goal", "assumed": "TO_FILL",
            "reason": "未抽取到汇报目标；goal 不参与定量推导，但 storyboard 的"
                      "每页 message 必须服务于该目标，请人工补齐。"})

    # ---- 推导杠杆 -----------------------------------------------------------
    band = BACKGROUND_BANDS.get(aud, BACKGROUND_BANDS[DEFAULT_AUDIENCE])
    venue_spec = VENUE_RULE_SPECS.get(ven, VENUE_RULE_SPECS[DEFAULT_VENUE])
    duration_seconds = dur * 60
    nominal = int(round((sc[0] + sc[1]) / 2.0))
    per_slide = duration_seconds / float(nominal)
    spec = {
        "schema": SCHEMA,
        "synthetic_example": synthetic,
        "inputs": {"case_json": os.path.abspath(args.case),
                   "task_md": os.path.abspath(args.task)},
        "work_order": {
            "audience": {"value": aud, "status": aud_status, "source": aud_src},
            "duration_min": {"value": dur, "status": dur_status, "source": dur_src},
            "slide_count": {"min": sc[0], "max": sc[1],
                            "status": sc_status, "source": sc_src},
            "venue": {"value": ven, "status": ven_status, "source": ven_src},
            "language": {"value": lang, "status": lang_status, "source": lang_src},
            "goal": {"value": goal, "status": goal_status, "source": goal_src},
        },
        "to_fill": [f for f, st in (
            ("audience", aud_status), ("duration_min", dur_status),
            ("slide_count", sc_status), ("venue", ven_status),
            ("language", lang_status), ("goal", goal_status)) if st == "TO_FILL"],
        "assumptions": assumptions,
        "derived": {
            "audience_band": {
                "background_ratio_min": band[0],
                "background_ratio_max": band[1],
                "basis": "audience=%s（带值依据 references/audience-levers.md §2）" % aud,
            },
            "conclusion_position": {
                "venue": ven,
                "rule": venue_spec["rule"],
                "detail": venue_spec["detail"],
                "first_conclusion_index_max_formula": "ceil(n_main/3)",
            },
            "time_model": {
                "wpm": args.wpm,
                "cjk_cpm": args.cjk_cpm,
                "min_seconds_per_slide": args.min_slide_seconds,
                "basis": ("语速默认值 wpm=%d / cjk_cpm=%d（--wpm/--cjk-cpm 可覆盖）；"
                          "依据 references/audience-levers.md §3"
                          % (args.wpm, args.cjk_cpm)),
            },
            "duration_seconds": duration_seconds,
            "slide_count_nominal": nominal,
            "per_slide_seconds": round(per_slide, 1),
            "total_time_band_seconds": [round(TIME_BAND[0] * duration_seconds, 1),
                                        round(TIME_BAND[1] * duration_seconds, 1)],
        },
    }

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            print("[ERROR] 输出目录创建失败：%s" % exc, file=sys.stderr)
            return 2
    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        print("[ERROR] 输出写入失败：%s" % exc, file=sys.stderr)
        return 2

    print("TALK SPEC COMPILED -> %s" % args.output)
    print("  audience=%s (%s)  venue=%s (%s)  language=%s (%s)"
          % (aud, aud_status, ven, ven_status, lang, lang_status))
    print("  duration=%d min (%s)  slides=%d-%d (%s)  per_slide=%.1fs  band=[%.0f, %.0f]s"
          % (dur, dur_status, sc[0], sc[1], sc_status, per_slide,
             TIME_BAND[0] * duration_seconds, TIME_BAND[1] * duration_seconds))
    print("  background_ratio_band=[%.2f, %.2f]  conclusion_rule=%s"
          % (band[0], band[1], venue_spec["rule"]))
    if spec["to_fill"]:
        print("[ACTION REQUIRED] 以下字段为 TO_FILL（已记录默认假设，"
              "请人工确认后回填 storyboard 设计依据）：%s"
              % ", ".join(spec["to_fill"]))
    for a in assumptions:
        print("[ASSUMPTION] %s: %s" % (a["field"], a["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
