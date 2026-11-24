#!/usr/bin/env python3
"""storyboard_gate.py — storyboard.json 对照 talk_spec.json 的确定性门控 S1–S6。

输入：
    --storyboard  storyboard.json：{"slides": [...]}；每页
        {id, role, message, notes, transition(可选),
         backup(可选, 默认 false), exhibits(可选, [{file,page,exhibit}])}
    --spec        talk_spec.json（workorder_compile.py 的产物）

检查项（违例逐条打印 "CODE: detail"，同码可多条）：
    S1  主故事线页数（backup:true 单独计数、排除在外）落在契约
        slide_count [min, max] 区间内。
    S2  每页恰好一个 message：非空；单句启发式——句末终止符 ≤ 2 个
        （!?。！？ 计数；小数点两侧为数字的 . 不计），且无行首列表标记
        （-、*、•、数字+./)、）。
    S3  时间模型：每页讲述秒数 = Latin 词数/wpm*60 + CJK 字数/cjk_cpm*60，
        求和时每页以 min_seconds_per_slide 为下限（floor）；非备用页合计
        须落在 [0.85, 1.15] × duration_seconds；且每个非备用页原始估计
        ≥ min_seconds_per_slide（备注过短视为无讲稿）。
    S4  叙事角色取自受控词表 {hook,problem,gap,approach,method,result,
        comparison,limitation,conclusion,outlook,backup}；主干顺序（首次
        出现，仅主故事线）problem < approach < result < conclusion；
        场合规则（来自 talk_spec.derived.conclusion_position）：
        review  ⇒ 首个 conclusion 页 0 基序号 ≤ ceil(n_main/3)；
        defense ⇒ 存在 limitation 页且其首次出现早于首个 conclusion 页。
    S5  背景页（角色 ∈ {hook, problem, gap}）占主故事线比例落在
        talk_spec.derived.audience_band 的听众带内。
    S6  每个 result / comparison 角色页至少绑定 1 个 exhibit locator：
        exhibits 列表中存在 file / page / exhibit 三键均非空的条目。

退出码：
    0  全部通过
    1  门控违例（stdout 逐项打印 S 编号清单）
    2  用法 / IO / JSON 解析 / schema 错误
"""
import argparse
import json
import math
import os
import re
import sys

ROLE_VOCAB = ("hook", "problem", "gap", "approach", "method", "result",
              "comparison", "limitation", "conclusion", "outlook", "backup")
BACKGROUND_ROLES = ("hook", "problem", "gap")
EXHIBIT_REQUIRED_ROLES = ("result", "comparison")
# 句末终止符：!?。！？ 一律计数；小数点（两侧均为数字的 .）不算句末。
SENT_TERMINATOR_RE = re.compile(r"[!?。！？]|(?<!\d)\.(?!\d)")
LIST_MARKER_RE = re.compile(r"(?m)^\s*(?:[-*•‣◦]|\d{1,2}\s*[.)、])")
LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[’'\-][A-Za-z0-9]+)*")
CJK_RE = re.compile(r"[㐀-䶿一-鿿]")


def load_json(path, what):
    if not os.path.isfile(path):
        print("[ERROR] %s 不存在：%s" % (what, path), file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print("[ERROR] %s 解析失败：%s" % (what, exc), file=sys.stderr)
        sys.exit(2)


def estimate_seconds(notes, wpm, cjk_cpm):
    """返回 (seconds, latin_words, cjk_chars)。"""
    words = len(LATIN_WORD_RE.findall(notes))
    cjk = len(CJK_RE.findall(notes))
    return words * 60.0 / wpm + cjk * 60.0 / cjk_cpm, words, cjk


def spec_number(spec, path, what):
    """从 talk_spec 取数值；结构缺失即 schema 错误（exit 2）。"""
    node = spec
    for key in path:
        if not isinstance(node, dict) or key not in node:
            print("[ERROR] %s 缺少字段 %s" % (what, ".".join(path)),
                  file=sys.stderr)
            sys.exit(2)
        node = node[key]
    if not isinstance(node, (int, float)):
        print("[ERROR] %s 字段 %s 非数值：%r" % (what, ".".join(path), node),
              file=sys.stderr)
        sys.exit(2)
    return float(node)


def main():
    ap = argparse.ArgumentParser(
        description="storyboard 对照 talk_spec 的门控校验（S1-S6）")
    ap.add_argument("--storyboard", default="/app/work/storyboard.json",
                    help="storyboard.json 路径")
    ap.add_argument("--spec", default="/app/work/talk_spec.json",
                    help="talk_spec.json 路径")
    args = ap.parse_args()

    spec = load_json(args.spec, "talk_spec.json")
    board = load_json(args.storyboard, "storyboard.json")

    # ---- schema 检查（错误 → exit 2） --------------------------------------
    if not isinstance(board, dict) or not isinstance(board.get("slides"), list):
        print("[ERROR] storyboard 结构非法：顶层须为含 slides 列表的对象",
              file=sys.stderr)
        return 2
    if not board["slides"]:
        print("[ERROR] storyboard.slides 为空", file=sys.stderr)
        return 2
    for i, sl in enumerate(board["slides"]):
        if not isinstance(sl, dict):
            print("[ERROR] slides[%d] 非对象" % i, file=sys.stderr)
            return 2
        for key in ("id", "role", "message", "notes"):
            if key not in sl:
                print("[ERROR] slides[%d] 缺少键 %s" % (i, key), file=sys.stderr)
                return 2
        if not isinstance(sl["message"], str) or not isinstance(sl["notes"], str):
            print("[ERROR] slides[%d] 的 message/notes 须为字符串" % i,
                  file=sys.stderr)
            return 2
        if "backup" in sl and not isinstance(sl["backup"], bool):
            print("[ERROR] slides[%d] 的 backup 须为布尔值" % i, file=sys.stderr)
            return 2

    derived = spec.get("derived")
    if not isinstance(derived, dict):
        print("[ERROR] talk_spec 缺少 derived 区块（请先运行 workorder_compile.py）",
              file=sys.stderr)
        return 2

    sc_min = spec_number(spec, ("work_order", "slide_count", "min"), "talk_spec")
    sc_max = spec_number(spec, ("work_order", "slide_count", "max"), "talk_spec")
    duration_s = spec_number(spec, ("derived", "duration_seconds"), "talk_spec")
    wpm = spec_number(spec, ("derived", "time_model", "wpm"), "talk_spec")
    cjk_cpm = spec_number(spec, ("derived", "time_model", "cjk_cpm"), "talk_spec")
    min_sec = spec_number(spec, ("derived", "time_model", "min_seconds_per_slide"),
                          "talk_spec")
    tb = derived.get("total_time_band_seconds")
    if (not isinstance(tb, list) or len(tb) != 2
            or not all(isinstance(x, (int, float)) for x in tb)):
        print("[ERROR] talk_spec derived.total_time_band_seconds 须为 [lo, hi]",
              file=sys.stderr)
        return 2
    band_lo, band_hi = float(tb[0]), float(tb[1])
    ab = derived.get("audience_band")
    if (not isinstance(ab, dict)
            or not isinstance(ab.get("background_ratio_min"), (int, float))
            or not isinstance(ab.get("background_ratio_max"), (int, float))):
        print("[ERROR] talk_spec derived.audience_band 缺少比例带", file=sys.stderr)
        return 2
    bg_lo, bg_hi = float(ab["background_ratio_min"]), float(ab["background_ratio_max"])
    cp = derived.get("conclusion_position") or {}
    venue = str(cp.get("venue", "generic"))
    rule = str(cp.get("rule", "standard_spine"))

    slides = board["slides"]
    main_slides = [s for s in slides if not s.get("backup", False)]
    n_main = len(main_slides)
    n_backup = len(slides) - n_main
    violations = []  # (scode, message)

    # ---- S1：页数契约 ------------------------------------------------------
    if n_main < sc_min or n_main > sc_max:
        violations.append((
            "S1", "主故事线页数 %d 超出契约区间 [%d, %d]（备用页 %d 张单独计数，"
                  "不计入主故事线）" % (n_main, sc_min, sc_max, n_backup)))

    # ---- S2：每页恰好一个 message ------------------------------------------
    for sl in slides:
        sid = sl.get("id")
        msg = sl["message"]
        if not msg.strip():
            violations.append(("S2", "页 %s 的 message 为空" % sid))
            continue
        terms = len(SENT_TERMINATOR_RE.findall(msg))
        if terms > 2:
            violations.append((
                "S2", "页 %s 的 message 含 %d 个句末终止符（>2），"
                      "疑似多个主张：%r" % (sid, terms, msg[:60])))
        m = LIST_MARKER_RE.search(msg)
        if m:
            violations.append((
                "S2", "页 %s 的 message 含列表标记 %r，应拆分为多页：%r"
                      % (sid, m.group(0).strip(), msg[:60])))

    # ---- S3：时间模型 ------------------------------------------------------
    total_s = 0.0
    per_slide = []  # (id, raw_seconds, floored_seconds, words, cjk)
    for sl in main_slides:
        raw, words, cjk = estimate_seconds(sl["notes"], wpm, cjk_cpm)
        floored = max(raw, min_sec)
        total_s += floored
        per_slide.append((sl.get("id"), raw, floored, words, cjk))
        if raw < min_sec:
            violations.append((
                "S3", "页 %s 备注过短：原始估计 %.1fs < 每页下限 %.0fs"
                      "（%d Latin 词 / %d CJK 字），视为无可用讲稿"
                      % (sl.get("id"), raw, min_sec, words, cjk)))
    if total_s < band_lo or total_s > band_hi:
        violations.append((
            "S3", "主故事线估计总时长 %.1fs（%.1f min）超出时长带 [%.0f, %.0f]s"
                  "（= [0.85, 1.15] × %ds；wpm=%d, cjk_cpm=%d）"
                  % (total_s, total_s / 60.0, band_lo, band_hi, duration_s,
                     wpm, cjk_cpm)))

    # ---- S4：叙事角色与顺序 -------------------------------------------------
    roles = []
    for sl in main_slides:
        r = str(sl.get("role"))
        if r not in ROLE_VOCAB:
            violations.append((
                "S4", "页 %s 的角色 %r 不在受控词表 %s 内"
                      % (sl.get("id"), r, "/".join(ROLE_VOCAB))))
        roles.append(r)
    first = {}
    for idx, r in enumerate(roles):
        if r not in first:
            first[r] = idx
    for a, b in (("problem", "approach"), ("approach", "result"),
                 ("result", "conclusion")):
        if a in first and b in first and first[a] >= first[b]:
            violations.append((
                "S4", "主干顺序违例：%s 首次出现于第 %d 页（0 基 %d），"
                      "不早于 %s（0 基 %d）"
                      % (a, first[a] + 1, first[a], b, first[b])))
    if rule == "conclusion_first":
        if "conclusion" not in first:
            violations.append((
                "S4", "venue=review 要求结论先行，但 storyboard 中没有 "
                      "conclusion 角色页"))
        else:
            limit = int(math.ceil(n_main / 3.0))
            if first["conclusion"] > limit:
                violations.append((
                    "S4", "venue=review 结论先行违例：首个 conclusion 页 0 基序号 "
                          "%d > ceil(n_main/3) = %d（n_main=%d），"
                          "结论未落在前约 1/3 内"
                          % (first["conclusion"], limit, n_main)))
    elif rule == "limitations_before_conclusion":
        if "limitation" not in first:
            violations.append((
                "S4", "venue=defense 要求 limitation 角色页先于 conclusion，"
                      "但 storyboard 中没有 limitation 页"))
        elif "conclusion" in first and first["limitation"] >= first["conclusion"]:
            violations.append((
                "S4", "venue=defense 顺序违例：limitation 首次出现（0 基 %d）"
                      "不早于 conclusion（0 基 %d）"
                      % (first["limitation"], first["conclusion"])))

    # ---- S5：背景比例带 -----------------------------------------------------
    n_bg = sum(1 for r in roles if r in BACKGROUND_ROLES)
    bg_ratio = (n_bg / float(n_main)) if n_main else 0.0
    if n_main and (bg_ratio < bg_lo - 1e-9 or bg_ratio > bg_hi + 1e-9):
        violations.append((
            "S5", "背景页（hook/problem/gap）比例 %.2f（%d/%d）超出听众带 "
                  "[%.2f, %.2f]（依据 talk_spec.derived.audience_band）"
                  % (bg_ratio, n_bg, n_main, bg_lo, bg_hi)))

    # ---- S6：result/comparison 页的 exhibit 绑定 -----------------------------
    for sl in main_slides:
        if str(sl.get("role")) not in EXHIBIT_REQUIRED_ROLES:
            continue
        exhibits = sl.get("exhibits")
        ok = False
        if isinstance(exhibits, list):
            for ex in exhibits:
                if (isinstance(ex, dict)
                        and str(ex.get("file", "")).strip()
                        and ex.get("page") is not None
                        and str(ex.get("exhibit", "")).strip()):
                    ok = True
                    break
        if not ok:
            violations.append((
                "S6", "页 %s（role=%s）未绑定任何 exhibit locator"
                      "（需要 ≥1 个 file/page/exhibit 均非空的条目）"
                      % (sl.get("id"), sl.get("role"))))

    # ---- 汇总 -------------------------------------------------------------
    print("STORYBOARD STATS: main=%d backup=%d | est_total=%.1fs (%.1f min) "
          "band=[%.0f, %.0f]s | background=%.2f in [%.2f, %.2f] | "
          "venue=%s rule=%s"
          % (n_main, n_backup, total_s, total_s / 60.0, band_lo, band_hi,
             bg_ratio, bg_lo, bg_hi, venue, rule))
    for sid, raw, floored, words, cjk in per_slide:
        print("  %-6s raw=%6.1fs floor=%6.1fs (words=%d cjk=%d)"
              % (sid, raw, floored, words, cjk))
    if violations:
        by_s = {}
        for scode, msg in violations:
            by_s.setdefault(scode, []).append(msg)
        print("GATE FAILED: %s" % " ".join(sorted(by_s)))
        for scode in sorted(by_s):
            for msg in by_s[scode]:
                print("%s: %s" % (scode, msg))
        return 1
    print("GATE PASSED: S1-S6 全部通过（main=%d, backup=%d, est=%.1f min）"
          % (n_main, n_backup, total_s / 60.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
