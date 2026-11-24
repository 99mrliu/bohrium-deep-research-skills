#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rhetoric_lint.py — 基金申请书章节稿修辞 Lint（规则 L1-L6）。

规则（详见 references/）：
  L1 不可核验修饰词禁用表命中（references/banned_phrases.txt，--extra 可追加）-> error
  L2 口号句：含政策口号模式且句内无引文标记 -> error
  L3 绝对化表述（完全解决/彻底/所有场景 等）-> error
  L4 创新点段落四要件检测（差异定位/点名已有工作/难点/可行性凭据，缺件列明）-> error
  L5 同一修饰词 200 字窗口内重复 >=3 次 -> warning
  L6 中英文标点混用 -> warning

产出：<outdir>/lint_report.json 与 <outdir>/lint_annotated.txt（带行号标注）。
退出码：0 通过（可含 warning）；1 存在 error；2 用法/IO 错误。
仅使用 Python3 标准库；确定性输出（结果按文件顺序排序，不依赖环境）。
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- 内建规则表
# L2 政策口号模式
SLOGAN_PATTERNS = [
    "具有重要意义", "意义重大", "重大意义", "重要的意义",
    "符合国家战略", "国家战略", "重大需求", "国家需求",
    "势在必行", "刻不容缓", "国计民生", "战略意义",
    "具有战略", "高度重视", "重大而深远",
]
# L3 绝对化表述
ABSOLUTE_PATTERNS = [
    "完全解决", "彻底解决", "彻底消除", "彻底",
    "所有场景", "任何场景", "一切场景", "各种场景均",
    "完全消除", "杜绝", "根治", "百分之百",
]
# L4 四要件标记词
DIFF_CUES = ["不同于", "区别于", "相较于", "相比", "而现有", "有别于"]
NAMED_WORK_RE = re.compile(
    r"(《[^》]+》"
    r"|\[[0-9]+\]"
    r"|〔[^〕]*〕"
    r"|（[^）]*(?:19|20)\d{2}[^）]*）"
    r"|\([A-Za-z][^)]*(?:19|20)\d{2}[^)]*\)"
    r"|[一-龥]{2,4}等（(?:19|20)\d{2}）"
    r"|[A-Za-z]+\s*等?\s*（(?:19|20)\d{2}）)"
)
DIFFICULTY_CUES = ["难点", "难在", "挑战", "困难", "瓶颈", "难以", "风险", "不易"]
FEASIBILITY_CUES = [
    "已验证", "可行性", "前期", "预实验", "已有数据", "初步结果",
    "已搭建", "已建立", "已发表", "平台", "试点", "积累", "经验", "具备",
]
# L5 修饰词表（窗口重复检测）
MODIFIER_WORDS = [
    "显著", "重要", "创新", "高效", "优异", "有效",
    "大幅", "极大", "充分", "深入", "系统", "全面",
]
L5_WINDOW = 200
L5_MIN_COUNT = 3

# 引文标记（L2 豁免依据）：[n]、〔…〕、（…年份…）、(Author…年份…)
CITATION_RE = re.compile(
    r"(\[[0-9]+\]|〔[^〕]*〕|（[^）]*(?:19|20)\d{2}[^）]*）|\([A-Za-z][^)]*(?:19|20)\d{2}[^)]*\))"
)
CJK_RE = re.compile(r"[一-龥]")
HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")


# ---------------------------------------------------------------- 工具函数
def load_word_list(path):
    """读取一行一个的词表文件；# 开头行与空行忽略。"""
    words = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if w and not w.startswith("#"):
                words.append(w)
    return words


def line_no_of(text, pos):
    return text.count("\n", 0, pos) + 1


def split_sentences_with_lines(text):
    """把全文切成句子，返回 [(sentence, start_line)]。按 。！？；与换行切分。"""
    sentences = []
    start = 0
    for m in re.finditer(r"[。！？；\n]", text):
        seg = text[start:m.start()].strip()
        if seg:
            sentences.append((seg, line_no_of(text, start)))
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append((tail, line_no_of(text, start)))
    return sentences


def find_section(lines, keyword):
    """找到标题含 keyword 的小节，返回 (start_idx, end_idx)（不含下一同级或更高级标题）。"""
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and keyword in m.group(2):
            level = len(m.group(1))
            j = i + 1
            while j < len(lines):
                m2 = HEADING_RE.match(lines[j])
                if m2 and len(m2.group(1)) <= level:
                    break
                j += 1
            return i, j
    return None


def extract_innovation_items(lines, start, end):
    """把创新点小节内容切成条目。条目起始行：列表标记或“创新点N”。返回 [(text, line_no)]。"""
    item_start_re = re.compile(
        r"^\s*(?:[-*+] |\d+[.、）)]\s*|（\d+）\s*|创新点\s*[一二三四五六七八九十\d])"
    )
    items = []
    cur, cur_line = [], None
    for idx in range(start + 1, end):
        line = lines[idx]
        if item_start_re.match(line):
            if cur:
                items.append(("\n".join(cur), cur_line))
            cur, cur_line = [line.strip()], idx + 1
        elif line.strip():
            cur.append(line.strip())
    if cur:
        items.append(("\n".join(cur), cur_line))
    # 若没有列表条目，退化为按空行分段
    if not items:
        para, para_line = [], None
        for idx in range(start + 1, end):
            if lines[idx].strip():
                if not para:
                    para_line = idx + 1
                para.append(lines[idx].strip())
            elif para:
                items.append(("\n".join(para), para_line))
                para = []
        if para:
            items.append(("\n".join(para), para_line))
    return items


# ---------------------------------------------------------------- 规则实现
def check_l1(text, banned):
    findings = []
    for phrase in banned:
        for m in re.finditer(re.escape(phrase), text):
            findings.append({
                "rule": "L1", "severity": "error",
                "line": line_no_of(text, m.start()),
                "message": "命中不可核验修饰词禁用表：「%s」" % phrase,
                "evidence": phrase,
            })
    return findings


def check_l2(text):
    findings = []
    for sent, ln in split_sentences_with_lines(text):
        hit = next((p for p in SLOGAN_PATTERNS if p in sent), None)
        if hit and not CITATION_RE.search(sent):
            findings.append({
                "rule": "L2", "severity": "error", "line": ln,
                "message": "口号句：含政策口号模式「%s」且句内无引文标记" % hit,
                "evidence": sent[:60] + ("…" if len(sent) > 60 else ""),
            })
    return findings


def check_l3(text):
    findings = []
    seen = set()
    for pattern in ABSOLUTE_PATTERNS:
        for m in re.finditer(re.escape(pattern), text):
            ln = line_no_of(text, m.start())
            key = (pattern, ln)
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "rule": "L3", "severity": "error", "line": ln,
                "message": "绝对化表述：「%s」" % pattern,
                "evidence": pattern,
            })
    # “彻底”是“彻底解决/彻底消除”的子串，去重：同一位置只报最长匹配
    dedup = []
    for f in findings:
        if f["evidence"] == "彻底" and any(
            g["line"] == f["line"] and g["evidence"].startswith("彻底") and g["evidence"] != "彻底"
            for g in findings
        ):
            continue
        dedup.append(f)
    return dedup


def check_l4(text):
    findings = []
    lines = text.split("\n")
    sec = find_section(lines, "创新点")
    if not sec:
        findings.append({
            "rule": "L4", "severity": "error", "line": 0,
            "message": "未找到标题含「创新点」的小节，无法执行四要件检测",
            "evidence": "",
        })
        return findings
    items = extract_innovation_items(lines, sec[0], sec[1])
    if not items:
        findings.append({
            "rule": "L4", "severity": "error", "line": sec[0] + 1,
            "message": "「创新点」小节为空，无条目可检测",
            "evidence": "",
        })
        return findings
    for n, (item_text, ln) in enumerate(items, 1):
        missing = []
        if not any(c in item_text for c in DIFF_CUES):
            missing.append("差异定位（不同于/区别于/相比/而现有 等）")
        if not NAMED_WORK_RE.search(item_text):
            missing.append("点名已有工作（作者年份/《成果名》/文献编号）")
        if not any(c in item_text for c in DIFFICULTY_CUES):
            missing.append("难点表述")
        if not any(c in item_text for c in FEASIBILITY_CUES):
            missing.append("可行性凭据表述")
        if missing:
            findings.append({
                "rule": "L4", "severity": "error", "line": ln,
                "message": "创新点第 %d 条四要件不全，缺：%s" % (n, "；".join(missing)),
                "evidence": item_text[:60] + ("…" if len(item_text) > 60 else ""),
            })
    return findings


def check_l5(text):
    findings = []
    for word in MODIFIER_WORDS:
        positions = [m.start() for m in re.finditer(re.escape(word), text)]
        reported = False
        for i in range(len(positions) - (L5_MIN_COUNT - 1)):
            window = positions[i + L5_MIN_COUNT - 1] - positions[i]
            if window <= L5_WINDOW and not reported:
                findings.append({
                    "rule": "L5", "severity": "warning",
                    "line": line_no_of(text, positions[i]),
                    "message": "修饰词「%s」在 %d 字窗口内出现 ≥%d 次" % (word, L5_WINDOW, L5_MIN_COUNT),
                    "evidence": word,
                })
                reported = True
    return findings


def check_l6(text):
    findings = []
    halfwidth = ",;:!?"
    for m in re.finditer(r"[.,;:!?()]", text):
        ch = m.group()
        prev = text[m.start() - 1] if m.start() > 0 else ""
        nxt = text[m.end()] if m.end() < len(text) else ""
        prev_cjk, next_cjk = bool(CJK_RE.match(prev)), bool(CJK_RE.match(nxt))
        if ch == "." and not (prev_cjk or next_cjk):
            continue
        if ch in halfwidth and (prev_cjk or next_cjk):
            pass
        elif ch in "()" and (prev_cjk or next_cjk):
            pass
        else:
            continue
        findings.append({
            "rule": "L6", "severity": "warning",
            "line": line_no_of(text, m.start()),
            "message": "中英文标点混用：半角「%s」与汉字相邻" % ch,
            "evidence": text[max(0, m.start() - 6):m.end() + 6].replace("\n", " "),
        })
    # 同一行同类问题合并报告，避免刷屏
    compact, seen = [], set()
    for f in findings:
        key = (f["line"], f["message"][:12])
        if key not in seen:
            seen.add(key)
            compact.append(f)
    return compact


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="基金申请书章节稿修辞 Lint（L1-L6），产出 lint_report.json 与带行号标注文本。"
    )
    ap.add_argument("input", help="章节稿 markdown 文件路径")
    ap.add_argument("-o", "--outdir", default=".",
                    help="输出目录（默认当前目录），写 lint_report.json 与 lint_annotated.txt")
    ap.add_argument("--banned", default=None,
                    help="禁用词表路径（默认脚本上级 references/banned_phrases.txt）")
    ap.add_argument("--extra", default=None, action="append",
                    help="追加禁用词表（一行一个，可多次指定）")
    args = ap.parse_args(argv)

    banned_path = args.banned or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, "references", "banned_phrases.txt")
    try:
        with open(args.input, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("错误：无法读取输入文件 %s：%s" % (args.input, e), file=sys.stderr)
        return 2
    try:
        banned = load_word_list(banned_path)
    except OSError as e:
        print("错误：无法读取禁用词表 %s：%s" % (banned_path, e), file=sys.stderr)
        return 2
    if args.extra:
        for path in args.extra:
            try:
                banned.extend(load_word_list(path))
            except OSError as e:
                print("错误：无法读取追加词表 %s：%s" % (path, e), file=sys.stderr)
                return 2

    findings = []
    findings += check_l1(text, banned)
    findings += check_l2(text)
    findings += check_l3(text)
    findings += check_l4(text)
    findings += check_l5(text)
    findings += check_l6(text)
    findings.sort(key=lambda f: (f["line"], f["rule"]))

    n_err = sum(1 for f in findings if f["severity"] == "error")
    n_warn = sum(1 for f in findings if f["severity"] == "warning")
    per_rule = {}
    for f in findings:
        per_rule.setdefault(f["rule"], {"error": 0, "warning": 0})
        per_rule[f["rule"]][f["severity"]] += 1

    report = {
        "input": os.path.abspath(args.input),
        "summary": {"errors": n_err, "warnings": n_warn, "per_rule": per_rule},
        "findings": findings,
    }
    try:
        os.makedirs(args.outdir, exist_ok=True)
        with open(os.path.join(args.outdir, "lint_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        by_line = {}
        for f in findings:
            by_line.setdefault(f["line"], []).append(f)
        with open(os.path.join(args.outdir, "lint_annotated.txt"), "w", encoding="utf-8") as f:
            for i, line in enumerate(text.split("\n"), 1):
                f.write("%4d | %s\n" % (i, line))
                for fnd in by_line.get(i, []):
                    f.write("     ^ [%s %s] %s\n" % (fnd["rule"], fnd["severity"], fnd["message"]))
            for fnd in by_line.get(0, []):
                f.write("     ^ [%s %s] %s\n" % (fnd["rule"], fnd["severity"], fnd["message"]))
    except OSError as e:
        print("错误：写出产物失败：%s" % e, file=sys.stderr)
        return 2

    print("rhetoric_lint: %d error, %d warning -> %s" % (
        n_err, n_warn, os.path.join(args.outdir, "lint_report.json")))
    for rule in sorted(per_rule):
        print("  %s: %d error, %d warning" % (rule, per_rule[rule]["error"], per_rule[rule]["warning"]))
    return 1 if n_err > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
