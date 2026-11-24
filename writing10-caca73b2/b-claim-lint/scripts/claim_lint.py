#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_lint.py — 结果与讨论章节语言校准静态审计器（确定性、仅标准库）。

逐句扫描中/英文 Results & Discussion 草稿，依据显式规则包报告违规：
  R01 因果越界 (error)   R02 无检验显著 (error)   R03 结果段混入解释 (warn)
  R04 讨论段新数据 (error) R05 幅度夸大 (warn)      R06 趋势无支撑 (warn)
  R07 局限缺失 (warn)      R08 流水账 (info)

退出码：存在未豁免的 error 级违规时为 1，否则为 0；参数/文件错误为 2。
"""
import argparse
import json
import re
import sys

VERSION = "1.0.0"

# ---------------------------------------------------------------- 句子切分
ABBR = {"fig", "figure", "vs", "dr", "etc", "e.g", "i.e", "ca", "prof", "al"}
SENT_END_ZH = "。！？；"


def split_sentences(line):
    """把一行文本切为句子列表。句号在缩写词后或小数点处不切分。"""
    parts, buf = [], []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        buf.append(ch)
        end = False
        if ch in SENT_END_ZH:
            end = True
        elif ch in ".!?" :
            nxt = line[i + 1] if i + 1 < n else ""
            if ch == "." and nxt and (nxt.isdigit() or nxt == "."):
                end = False  # 小数点或省略号
            elif nxt and not nxt.isspace():
                end = False  # 句号后无空白（如 p<0.05.abc 之类）
            else:
                word = re.search(r"([A-Za-z][A-Za-z.]*)\.$", "".join(buf))
                if word and word.group(1).lower().rstrip(".") in ABBR:
                    end = False
                else:
                    end = True
        if end:
            s = "".join(buf).strip()
            if s:
                parts.append(s)
            buf = []
        i += 1
    rest = "".join(buf).strip()
    if rest:
        parts.append(rest)
    return parts


# ---------------------------------------------------------------- 规则包
CAUSAL_VERBS = re.compile(
    r"导致|促使|引起|证明了?|证实了?|决定了?|"
    r"\bdemonstrates?\b|\bproves?\b|\bproved\b|\bcauses?\b|\bcaused\b|\bdrives?\b|\bdrove\b",
    re.IGNORECASE,
)
HEDGE = re.compile(
    r"提示|推测|可能|或许|有望|似乎|\bsuggests?\b|\bsuggested\b|\bimply\b|\bimplied\b|"
    r"\bindicates?\b|\bmay\b|\bmight\b|\blikely\b|\bprobably\b",
    re.IGNORECASE,
)
DESIGN_MARKERS = re.compile(
    r"随机分组|随机对照|随机区组|随机化|随机试验|\bRCT\b|干预实验|双盲",
    re.IGNORECASE,
)
DESIGN_NEG = re.compile(r"(未|未经|无|没有|并未|\bnot\b|\bno\b|\bnon[- ]?)\s*$")

SIGNIFICANT = re.compile(r"显著|significant(?:ly)?", re.IGNORECASE)
SIGNIFICANT_NEG = re.compile(
    r"不显著|无显著|未达到?显著|未达显著|均无显著|"
    r"non[- ]?significant|not\s+significant|no\s+significant",
    re.IGNORECASE,
)
STAT_EVIDENCE = re.compile(
    r"[pP]\s*[<=>≤≥]\s*0?\.\d+|置信区间|\bCI\b|95\s*%\s*CI|"
    r"[tFz]\s*[(=]|χ²|卡方|\bchi[- ]?square",
    re.IGNORECASE,
)

R03_MARKERS = re.compile(
    r"表明.{0,15}机制|可能是由于|其原因|与既往研究一致|这提示我们|"
    r"consistent with (?:previous|prior)|this suggests that|may be due to",
    re.IGNORECASE,
)

UNIT_TOKEN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|mg|g|kg|μg|ug|mL|ml|L|mM|μM|uM|nM|mol|mmol|μmol|umol|"
    r"h|min|s|℃|°C|mm|cm|m|kPa|MPa|Pa|mV|V|A|Ω|"
    r"天|小时|分钟|周|个月|倍|个|例|只|株|盆|组)"
    r"(?![A-Za-z])",
)

R05_MARKERS = re.compile(
    r"大幅|显著改善|急剧|骤升|骤降|\bdramatic(?:ally)?\b|\bsubstantial(?:ly)?\b|\bdrastic(?:ally)?\b",
    re.IGNORECASE,
)
R05_NEG = re.compile(r"无显著改善|未显著改善|not\s+significant(?:ly)?\s+improv", re.IGNORECASE)
EFFECT_SIZE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|个百分点)|\bfold\b|\d+(?:\.\d+)?[- ]fold", re.IGNORECASE)

R06_MARKERS = re.compile(
    r"趋势|随.{0,10}(升高|增加|上升|降低|下降)|剂量依赖|"
    r"dose[- ]dependent|trend(?:ed|ing)?",
    re.IGNORECASE,
)
R06_TEST = re.compile(
    r"趋势检验|相关分析|相关(?!性).{0,4}r\s*=|(?<![A-Za-z])r\s*=\s*0?\.\d+|"
    r"Spearman|Pearson|Kendall|线性趋势|回归",
    re.IGNORECASE,
)
R06_HEDGE = re.compile(r"未达显著|未达到显著|未经趋势检验|未进行趋势检验|趋势.{0,6}未.{0,4}显著")

R07_MARKERS = re.compile(r"局限|不足|限制|limitation|shortcoming|caveat", re.IGNORECASE)

CALLOUT = re.compile(r"图\s*\d+|表\s*\d+|Fig(?:ure)?\.?\s*\d+|Table\s*\d+", re.IGNORECASE)

RULES = {
    "R01": {"severity": "error", "name": "因果越界"},
    "R02": {"severity": "error", "name": "无检验显著"},
    "R03": {"severity": "warn", "name": "结果段混入解释"},
    "R04": {"severity": "error", "name": "讨论段新数据"},
    "R05": {"severity": "warn", "name": "幅度夸大"},
    "R06": {"severity": "warn", "name": "趋势无支撑"},
    "R07": {"severity": "warn", "name": "局限缺失"},
    "R08": {"severity": "info", "name": "流水账"},
}

MESSAGES = {
    "R01": "疑似因果越界：全文无有效随机/干预设计标记，且本句无对冲语，却使用因果动词「{detail}」。",
    "R02": "「显著」表述缺少统计支撑：同句及同段均未发现 p 值、置信区间或检验统计量。",
    "R03": "结果段出现解释性表述「{detail}」，结果段应只陈述观察事实。",
    "R04": "讨论段出现结果段未报告的数据「{detail}」，新数据须先在结果段报告。",
    "R05": "幅度表述「{detail}」未在同句给出效应量数字。",
    "R06": "趋势/剂量依赖表述缺少趋势检验或相关系数支撑，且未加边界对冲。",
    "R07": "存在讨论段，但全文未发现局限性表述（局限/不足/limitation）。",
    "R08": "结果段单段图表引用 {detail} 处（>4）且段首缺少分组主题句。",
}

SUGGESTIONS = {
    "R01": "改写为相关/提示性表述，如「X 与 Y 相关」「结果提示 X 可能影响 Y」；若确有随机干预设计，请在方法或草稿中明示。",
    "R02": "补入同句检验结果（如「t 检验 p=0.032」或 95% CI）；若无检验，将「显著」改为「较高/较低」等描述性表述。",
    "R03": "将该句移至讨论段；结果段仅保留可观测数值与图表引用。",
    "R04": "先在结果段报告该数据及其来源，再在讨论段引用。",
    "R05": "在同句补充效应量（如「升高约 49%」「提高 1.8 倍」），或改用中性表述。",
    "R06": "补趋势检验或相关系数 r；或改写为「呈现…趋势，但未达显著/未进行趋势检验」。",
    "R07": "在讨论段末尾增设局限段落（样本量、设计缺陷、外推边界）。",
    "R08": "段首补一句分组主题句概括该段数据主线，再分述各图表。",
}


# ---------------------------------------------------------------- 草稿解析
def parse_draft(text, results_re, discussion_re):
    """返回 (sentences, paragraphs, flags)。

    sentences: list of dict(text, line, para, section)
    paragraphs: dict para_id -> {"section":..., "sentences":[...]}
    flags: {"results_present":bool, "discussion_present":bool, "results_text":str}
    """
    sentences = []
    paragraphs = {}
    section = "preamble"
    para_id = 0
    prev_blank = True
    in_fence = False
    results_chunks = []
    results_present = False
    discussion_present = False

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\n")
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            prev_blank = True
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", line.strip())
        if heading:
            title = heading.group(1)
            is_r = bool(results_re.search(title))
            is_d = bool(discussion_re.search(title))
            if is_r and is_d:
                section = "combined"
            elif is_r:
                section = "results"
            elif is_d:
                section = "discussion"
            else:
                section = "other"
            if section in ("results", "combined"):
                results_present = True
            if section in ("discussion", "combined"):
                discussion_present = True
            prev_blank = True
            continue
        if prev_blank:
            para_id += 1
            paragraphs[para_id] = {"section": section, "sentences": [], "line": lineno}
            prev_blank = False
        for sent in split_sentences(line):
            item = {"text": sent, "line": lineno, "para": para_id, "section": section}
            sentences.append(item)
            paragraphs[para_id]["sentences"].append(item)
            if section in ("results", "combined"):
                results_chunks.append(sent)
    flags = {
        "results_present": results_present,
        "discussion_present": discussion_present,
        "results_text": "\n".join(results_chunks),
    }
    return sentences, paragraphs, flags


def has_design_marker(text):
    """存在随机/干预设计标记且未被否定（如『未随机化』不算）。"""
    for m in DESIGN_MARKERS.finditer(text):
        prefix = text[max(0, m.start() - 8):m.start()]
        if not DESIGN_NEG.search(prefix):
            return True
    return False


# ---------------------------------------------------------------- 规则检测
def lint(text, results_re, discussion_re):
    sentences, paragraphs, flags = parse_draft(text, results_re, discussion_re)
    violations = []

    def add(rule, sent=None, detail="", line=None):
        v = {
            "rule": rule,
            "severity": RULES[rule]["severity"],
            "name": RULES[rule]["name"],
            "line": line if line is not None else (sent["line"] if sent else 0),
            "paragraph": sent["para"] if sent else 0,
            "section": sent["section"] if sent else "",
            "excerpt": (sent["text"][:80] + ("…" if len(sent["text"]) > 80 else "")) if sent else "",
            "message": MESSAGES[rule].format(detail=detail),
            "suggestion": SUGGESTIONS[rule],
        }
        violations.append(v)

    design_ok = has_design_marker(text)

    for s in sentences:
        t = s["text"]
        para_sents = paragraphs[s["para"]]["sentences"]
        para_text = " ".join(x["text"] for x in para_sents)

        # R01 因果越界
        m = CAUSAL_VERBS.search(t)
        if m and not design_ok and not HEDGE.search(t):
            add("R01", s, detail=m.group(0))

        # R02 无检验显著
        if (SIGNIFICANT.search(t) and not SIGNIFICANT_NEG.search(t)
                and not STAT_EVIDENCE.search(t) and not STAT_EVIDENCE.search(para_text)):
            add("R02", s)

        # R03 结果段混入解释
        if s["section"] == "results":
            m3 = R03_MARKERS.search(t)
            if m3:
                add("R03", s, detail=m3.group(0))

        # R04 讨论段新数据
        if s["section"] == "discussion":
            for m4 in UNIT_TOKEN.finditer(t):
                token = re.sub(r"\s+", "", m4.group(0))
                haystack = re.sub(r"\s+", "", flags["results_text"])
                if token not in haystack:
                    add("R04", s, detail=m4.group(0).strip())
                    break  # 每句至多报一次

        # R05 幅度夸大
        m5 = R05_MARKERS.search(t)
        if m5 and not R05_NEG.search(t) and not EFFECT_SIZE.search(t):
            add("R05", s, detail=m5.group(0))

        # R06 趋势无支撑
        if R06_MARKERS.search(t):
            if not (R06_TEST.search(t) or R06_TEST.search(para_text) or R06_HEDGE.search(t)):
                add("R06", s)

    # R07 局限缺失
    if flags["discussion_present"]:
        if not any(R07_MARKERS.search(s["text"]) for s in sentences):
            first_disc = next((s for s in sentences if s["section"] in ("discussion", "combined")), None)
            add("R07", first_disc)

    # R08 流水账
    for pid, para in paragraphs.items():
        if para["section"] != "results":
            continue
        ptext = " ".join(x["text"] for x in para["sentences"])
        callouts = CALLOUT.findall(ptext)
        if len(callouts) > 4:
            first = para["sentences"][0]["text"] if para["sentences"] else ""
            has_topic = (not CALLOUT.search(first)) and len(first) >= 8
            if not has_topic:
                add("R08", para["sentences"][0] if para["sentences"] else None,
                    detail=str(len(callouts)), line=para["line"])

    degraded = not (flags["results_present"] or flags["discussion_present"])
    return violations, flags, degraded


# ---------------------------------------------------------------- 报告输出
def build_report(violations, waivers, draft_path, degraded):
    waiver_map = {}
    for w in waivers:
        waiver_map.setdefault(w["rule"], []).append(w["reason"])
    for v in violations:
        reasons = waiver_map.get(v["rule"])
        v["waived"] = bool(reasons)
        v["waiver_reason"] = reasons[0] if reasons else ""

    unwaived = [v for v in violations if not v["waived"]]
    waived = [v for v in violations if v["waived"]]
    n_err = sum(1 for v in unwaived if v["severity"] == "error")
    n_warn = sum(1 for v in unwaived if v["severity"] == "warn")
    n_info = sum(1 for v in unwaived if v["severity"] == "info")
    verdict = "FAIL" if n_err > 0 else "PASS"

    per_rule = {}
    for rid in RULES:
        vs = [v for v in violations if v["rule"] == rid]
        per_rule[rid] = {"total": len(vs), "waived": sum(1 for v in vs if v["waived"])}

    report = {
        "tool": "claim_lint",
        "version": VERSION,
        "draft": draft_path,
        "verdict": verdict,
        "exit_code": 1 if verdict == "FAIL" else 0,
        "degraded_no_sections": degraded,
        "counts": {"error": n_err, "warn": n_warn, "info": n_info,
                    "waived": len(waived), "total": len(violations)},
        "per_rule": per_rule,
        "waivers": waivers,
        "violations": violations,
    }
    return report


def render_markdown(report):
    L = []
    L.append("# claim_lint 审计报告")
    L.append("")
    L.append("- 工具版本：claim_lint %s" % report["version"])
    L.append("- 草稿：`%s`" % report["draft"])
    L.append("- 结论：**%s**（退出码 %d）" % (report["verdict"], report["exit_code"]))
    c = report["counts"]
    L.append("- 未豁免违规：error %d / warn %d / info %d；已豁免 %d；共 %d 条"
             % (c["error"], c["warn"], c["info"], c["waived"], c["total"]))
    if report["degraded_no_sections"]:
        L.append("- ⚠ 未检测到结果/讨论分节标题：R03/R04/R07/R08 已跳过，"
                 "建议先用 section_split.py 预分节或补充分节标题。")
    L.append("")
    L.append("## 各规则命中统计")
    L.append("")
    L.append("| 规则 | 名称 | 严重级 | 命中 | 已豁免 |")
    L.append("| --- | --- | --- | --- | --- |")
    for rid, meta in RULES.items():
        pr = report["per_rule"][rid]
        L.append("| %s | %s | %s | %d | %d |" % (rid, meta["name"], meta["severity"],
                                                  pr["total"], pr["waived"]))
    L.append("")
    unwaived = [v for v in report["violations"] if not v["waived"]]
    L.append("## 未豁免违规明细")
    L.append("")
    if not unwaived:
        L.append("（无）")
    else:
        L.append("| 规则 | 严重级 | 行号 | 句子摘录 | 问题 | 修改建议 |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for v in unwaived:
            ex = v["excerpt"].replace("|", "\\|")
            L.append("| %s | %s | %d | %s | %s | %s |" % (
                v["rule"], v["severity"], v["line"], ex, v["message"], v["suggestion"]))
    L.append("")
    L.append("## 已豁免条目")
    L.append("")
    waived = [v for v in report["violations"] if v["waived"]]
    if not waived:
        L.append("（无）")
    else:
        L.append("| 规则 | 行号 | 句子摘录 | 豁免理由 |")
        L.append("| --- | --- | --- | --- |")
        for v in waived:
            ex = v["excerpt"].replace("|", "\\|")
            L.append("| %s | %d | %s | %s |" % (v["rule"], v["line"], ex, v["waiver_reason"]))
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- CLI
def parse_waiver(s):
    if ":" not in s:
        raise argparse.ArgumentTypeError("豁免格式应为 \"规则号:理由\"，例如 \"R03:该句为承接句\"")
    rid, reason = s.split(":", 1)
    rid = rid.strip().upper()
    if rid not in RULES:
        raise argparse.ArgumentTypeError("未知规则号 %r（可选：%s）" % (rid, ", ".join(RULES)))
    if not reason.strip():
        raise argparse.ArgumentTypeError("豁免理由不能为空")
    return {"rule": rid, "reason": reason.strip()}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="结果与讨论章节语言校准静态审计（因果边界/语气强度/分节越界）。",
        epilog="退出码：1=存在未豁免 error；0=通过（可含 warn/info 或已豁免项）；2=参数或文件错误。")
    ap.add_argument("--draft", required=True, help="待审计的 Markdown 草稿路径")
    ap.add_argument("--section-results-regex", default=r"结果|Results?",
                    help="识别结果节标题的正则（默认：结果|Results?）")
    ap.add_argument("--section-discussion-regex", default=r"讨论|Discussion",
                    help="识别讨论节标题的正则（默认：讨论|Discussion）")
    ap.add_argument("--waive", action="append", type=parse_waiver, default=[],
                    metavar='"R03:理由"',
                    help='豁免某条规则的全部命中，必须给理由；可多次使用，如 --waive "R05:效应量见结果段"')
    ap.add_argument("--out", default=None,
                    help="报告输出路径：.md 写 Markdown，.json 写 JSON；无扩展名则两者都写；缺省仅打印到 stdout")
    args = ap.parse_args(argv)

    try:
        with open(args.draft, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("错误：无法读取草稿 %s：%s" % (args.draft, e), file=sys.stderr)
        return 2

    try:
        results_re = re.compile(args.section_results_regex, re.IGNORECASE)
        discussion_re = re.compile(args.section_discussion_regex, re.IGNORECASE)
    except re.error as e:
        print("错误：分节正则非法：%s" % e, file=sys.stderr)
        return 2

    violations, flags, degraded = lint(text, results_re, discussion_re)
    report = build_report(violations, args.waive, args.draft, degraded)
    md = render_markdown(report)

    wrote = []
    if args.out:
        out = args.out
        if out.endswith(".md"):
            targets = [(out, md)]
        elif out.endswith(".json"):
            targets = [(out, json.dumps(report, ensure_ascii=False, indent=2))]
        else:
            targets = [(out + ".md", md),
                       (out + ".json", json.dumps(report, ensure_ascii=False, indent=2))]
        for path, content in targets:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content + "\n")
                wrote.append(path)
            except OSError as e:
                print("错误：无法写入报告 %s：%s" % (path, e), file=sys.stderr)
                return 2

    print(md)
    if wrote:
        print("报告已写入：%s" % ", ".join(wrote))
    print("结论：%s（退出码 %d）" % (report["verdict"], report["exit_code"]))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
