#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jargon_scan.py — 行话与缩写扫描器。

扫描稿件：
  1) 识别全大写缩写（>=2 个字母/数字，如 CCUS、LCA；白名单如 DNA 豁免）；
  2) 检查每个非白名单缩写在【首次出现处】是否已展开
     （中文「全称（ABBR）」或英文「full name (ABBR)」模式，
     判定依据：缩写首次出现时紧邻的前一个字符是 （ 或 ( ）；
  3) 用内置小型通用科研行话表（可用 --glossary 注入术语）统计每百字行话密度，
     对照受众画像 term_density_ceiling；
  4) 输出 jargon_report.json / .md，逐条带行号定位与修复建议。

密度口径：命中的行话（含非白名单缩写）不重叠地计次，
分母为去除空白字符后的全文长度，密度 = 命中数 / 字符数 * 100。

退出码：
  0  达标（密度 <= 上限且所有非白名单缩写首次出现均已展开）
  6  超标 / 存在未展开缩写
  1  用法错误 / IO 错误 / 画像文件缺失或损坏
"""
import argparse
import json
import os
import re
import sys

# 内置小型通用科研行话表（刻意保持小规模，领域词请用 --glossary 注入）
BUILTIN_JARGON = [
    # 中文
    "光合作用", "卡尔文循环", "光系统", "类囊体", "生物量", "生物质",
    "碳汇", "碳足迹", "固碳", "碳捕集", "代谢通路", "过表达", "敲除",
    "全生命周期", "光生物反应器", "生物反应器", "高通量", "原位",
    # 英文
    "RuBisCO", "photosynthesis", "Calvin cycle", "thylakoid", "biomass",
    "carbon fixation", "carbon footprint", "metabolic pathway", "knockout",
    "overexpression", "life cycle assessment", "photobioreactor",
]

DEFAULT_WHITELIST = ["DNA", "RNA", "ATP", "CO2"]
ABBR_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,})(?![A-Za-z0-9])")


def is_cjk(s):
    return any("一" <= c <= "鿿" for c in s)  # CJK 统一表意文字区间


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def load_glossary_terms(path):
    """从 glossary.tsv 注入行话词：approved_rendering 与 forbidden_synonyms 均计为行话。"""
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if parts[0].strip() == "source_term":
                continue
            while len(parts) < 4:
                parts.append("")
            for cand in [parts[0].strip(), parts[1].strip()]:
                if cand:
                    terms.append(cand)
            terms.extend(s.strip() for s in parts[3].split(",") if s.strip())
    return terms


def term_spans(text, term):
    spans = []
    if is_cjk(term):
        start = 0
        while True:
            i = text.find(term, start)
            if i < 0:
                break
            spans.append((i, i + len(term)))
            start = i + len(term)
    else:
        pat = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        for m in re.finditer(pat, text, re.IGNORECASE):
            spans.append((m.start(), m.end()))
    return spans


def select_nonoverlap(spans):
    """spans: [(start, end, term)]；按起点排序、同起点长者优先，贪心去除重叠。"""
    accepted = []
    last_end = -1
    for s, e, t in sorted(spans, key=lambda x: (x[0], -(x[1] - x[0]))):
        if s >= last_end:
            accepted.append((s, e, t))
            last_end = e
    return accepted


def scan_abbreviations(text, whitelist):
    abbrs = {}
    for m in ABBR_RE.finditer(text):
        ab = m.group(1)
        if ab in whitelist:
            continue
        if ab not in abbrs:
            prev = text[m.start() - 1] if m.start() > 0 else ""
            abbrs[ab] = {
                "abbr": ab,
                "count": 0,
                "first_line": line_of(text, m.start()),
                "expanded_at_first_occurrence": prev in "（(",
                "paren_form_exists_later": ("（" + ab + "）") in text or ("(" + ab + ")") in text,
            }
        abbrs[ab]["count"] += 1
    return abbrs


def main():
    default_profiles = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "references", "audience_profiles.json"
    )
    ap = argparse.ArgumentParser(description="行话密度与缩写展开检查")
    ap.add_argument("--text", required=True, help="待扫描稿件路径（UTF-8）")
    ap.add_argument("--audience", default=None, help="受众标签，用于读取术语密度上限与白名单")
    ap.add_argument("--ceiling", type=float, default=None, help="直接指定每百字行话上限（优先于画像）")
    ap.add_argument("--glossary", default=None, help="可选 glossary.tsv，注入领域行话词")
    ap.add_argument("--profiles", default=default_profiles, help="受众画像 JSON 路径")
    ap.add_argument("--out-json", default=None, help="输出 JSON 报告路径（缺省打印到 stdout）")
    ap.add_argument("--out-md", default=None, help="输出 Markdown 报告路径")
    args = ap.parse_args()

    try:
        with open(args.text, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"[ERROR] 无法读取稿件 {args.text}: {e}", file=sys.stderr)
        return 1

    ceiling = args.ceiling
    whitelist = set(DEFAULT_WHITELIST)
    audience_label = None
    if args.audience:
        try:
            with open(args.profiles, encoding="utf-8") as f:
                profiles = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[ERROR] 无法加载受众画像文件 {args.profiles}: {e}", file=sys.stderr)
            return 1
        prof = profiles.get("audiences", {}).get(args.audience)
        if prof is None:
            prof = profiles.get("fallback_profile", {})
            audience_label = f"{args.audience}（未命中，使用保守画像）"
        else:
            audience_label = f"{args.audience}（{prof.get('label', '')}）"
        if ceiling is None:
            ceiling = prof.get("term_density_ceiling", 1.0)
        whitelist.update(prof.get("abbreviation_policy", {}).get("whitelist", []))
    if ceiling is None:
        ceiling = 1.0  # 未给受众也未给上限时的保守默认
        audience_label = "未指定（保守默认上限 1.0）"

    jargon_terms = list(BUILTIN_JARGON)
    if args.glossary:
        try:
            jargon_terms.extend(load_glossary_terms(args.glossary))
        except OSError as e:
            print(f"[ERROR] 无法加载术语表 {args.glossary}: {e}", file=sys.stderr)
            return 1
    # 去重，长者优先（配合去重叠策略）
    jargon_terms = sorted(set(jargon_terms), key=lambda t: (-len(t), t))

    abbrs = scan_abbreviations(text, whitelist)

    # 行话命中：行话词 + 非白名单缩写（缩写本身也是行话）
    raw_spans = []
    for term in jargon_terms:
        for s, e in term_spans(text, term):
            raw_spans.append((s, e, term))
    for ab, info in abbrs.items():
        for m in re.finditer(r"(?<![A-Za-z0-9])" + re.escape(ab) + r"(?![A-Za-z0-9])", text):
            raw_spans.append((m.start(), m.end(), ab))
    hits = select_nonoverlap(raw_spans)

    char_count = len(re.sub(r"\s+", "", text))
    hit_count = len(hits)
    density = round(hit_count / char_count * 100, 3) if char_count else 0.0

    issues = []
    abbr_report = []
    for ab in sorted(abbrs, key=lambda a: abbrs[a]["first_line"]):
        info = abbrs[ab]
        entry = dict(info)
        if not info["expanded_at_first_occurrence"]:
            if info["paren_form_exists_later"]:
                suggestion = (
                    f"「{ab}」在第 {info['first_line']} 行首次出现时未展开"
                    "（后文才出现括号全称）。请把「全称（" + ab + "）」移到首次出现处。"
                )
            else:
                suggestion = (
                    f"「{ab}」在第 {info['first_line']} 行首次出现时未展开。"
                    "请写为「全称（" + ab + "）」，或确认其属于白名单通用缩写。"
                )
            entry["suggestion"] = suggestion
            issues.append({
                "type": "unexpanded_abbreviation",
                "abbr": ab,
                "line": info["first_line"],
                "message": suggestion,
            })
        abbr_report.append(entry)

    term_report = {}
    for s, e, t in hits:
        term_report.setdefault(t, {"term": t, "count": 0, "lines": []})
        term_report[t]["count"] += 1
        term_report[t]["lines"].append(line_of(text, s))
    term_report = sorted(term_report.values(), key=lambda x: (-x["count"], x["term"]))

    density_ok = density <= ceiling
    if not density_ok:
        top = "、".join(t["term"] for t in term_report[:5])
        issues.append({
            "type": "jargon_density_exceeded",
            "line": None,
            "message": (
                f"行话密度 {density} 次/百字，超过受众上限 {ceiling}。"
                f"高频行话：{top}。建议替换为日常表达或删减术语堆叠。"
            ),
        })

    report = {
        "tool": "jargon_scan.py",
        "file": args.text,
        "audience": audience_label,
        "term_density_ceiling": ceiling,
        "whitelist": sorted(whitelist),
        "char_count": char_count,
        "jargon_hit_count": hit_count,
        "jargon_density_per_100_chars": density,
        "density_ok": density_ok,
        "abbreviations": abbr_report,
        "jargon_terms": term_report,
        "issues": issues,
        "exit_code": 0 if not issues else 6,
    }

    md_lines = [
        f"# jargon_report — {os.path.basename(args.text)}",
        "",
        f"- 受众画像：{audience_label}",
        f"- 行话密度：{density} 次/百字（上限 {ceiling}）→ {'达标' if density_ok else '超标'}",
        f"- 非白名单缩写数：{len(abbr_report)}；未展开：{sum(1 for a in abbr_report if not a['expanded_at_first_occurrence'])}",
        "",
        "## 问题清单",
    ]
    if issues:
        for it in issues:
            loc = f"第 {it['line']} 行" if it["line"] else "全文"
            md_lines.append(f"- [{it['type']}] {loc}：{it['message']}")
    else:
        md_lines.append("- 无")
    md_lines += ["", "## 行话命中明细", "| 术语 | 次数 | 行号 |", "| --- | --- | --- |"]
    for t in term_report:
        md_lines.append(f"| {t['term']} | {t['count']} | {', '.join(map(str, t['lines']))} |")
    md_text = "\n".join(md_lines) + "\n"

    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out_json:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.out_json)), exist_ok=True)
            with open(args.out_json, "w", encoding="utf-8") as f:
                f.write(json_text)
        except OSError as e:
            print(f"[ERROR] 无法写出 {args.out_json}: {e}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(json_text)
    if args.out_md:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.out_md)), exist_ok=True)
            with open(args.out_md, "w", encoding="utf-8") as f:
                f.write(md_text)
        except OSError as e:
            print(f"[ERROR] 无法写出 {args.out_md}: {e}", file=sys.stderr)
            return 1

    print(
        f"[{'OK' if not issues else 'FAIL'}] {args.text}: density={density}/{ceiling}, "
        f"unexpanded_abbr={sum(1 for a in abbr_report if not a['expanded_at_first_occurrence'])}, "
        f"issues={len(issues)}",
        file=sys.stderr,
    )
    return 0 if not issues else 6


if __name__ == "__main__":
    sys.exit(main())
