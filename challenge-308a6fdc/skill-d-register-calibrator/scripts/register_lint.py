#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
register_lint.py — 中文学术文体 lint 与措辞强度校准（R1–R8）

纯 Python3 标准库实现，规则表驱动（默认加载 ../references/rules.json，可用 --rules 覆盖）。

用法：
  检查：  python3 register_lint.py --draft draft.md --materials m1.md m2.md \
              --report style_report.md --findings-json findings.json --stats-json lint_stats.json
  修复：  python3 register_lint.py --draft draft.md --fix --out draft_fixed.md --fix-log fix_log.json
          （--fix 只自动修 R2 全角化与 R1 无歧义替换，R3–R8 只报告不自动改）
  复检：  python3 register_lint.py --draft deliverable.md --verify
          （退出码 0 = 高级别项清零；1 = 仍有高级别项）
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 中文字符区间（CJK 统一表意文字及扩展 A）
ZH = r"一-鿿㐀-䶿"
ZH_RE = re.compile(f"[{ZH}]")
SEV_ORDER = {"高": 0, "中": 1, "低": 2}


# ---------------------------------------------------------------- 工具函数

def load_rules(path: Path) -> dict:
    """加载规则表 JSON。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def iter_body_lines(lines):
    """逐行产出 (行号[1基], 行文本, 是否在代码块内)。跳过围栏代码块供规则判断。"""
    in_code = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            yield i, line, True
            continue
        yield i, line, in_code


def is_heading(line: str):
    m = re.match(r"^#{1,6}\s*(.+?)\s*$", line)
    return m.group(1) if m else None


def split_sentences(line: str):
    """按中文句读切分句子，保留原文片段用于报告。"""
    parts = re.split(r"(?<=[。！？；])", line)
    return [p for p in parts if p.strip()]


def snippet(text: str, limit: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------- R1 人称

def check_r1(lines, rules):
    cfg = rules["r1_person"]
    pat = re.compile(cfg["pattern"])
    findings = []
    for i, line, in_code in iter_body_lines(lines):
        if in_code or is_heading(line):
            continue
        for m in pat.finditer(line):
            findings.append({
                "rule": "R1", "severity": cfg["severity"], "line": i,
                "snippet": snippet(line), "hit": m.group(0),
                "message": f"正文出现人称代词「{m.group(0)}」",
                "suggestion": cfg["suggestion"],
            })
    return findings


# ---------------------------------------------------------------- R2 标点

def _r2_matches_in_line(line: str, punct_map):
    """返回 (列号[0基], 半角符, 全角符) 列表。仅匹配中文语境中的半角标点。"""
    out = []
    for idx, ch in enumerate(line):
        if ch not in punct_map:
            continue
        prev = line[idx - 1] if idx > 0 else ""
        nxt = line[idx + 1] if idx + 1 < len(line) else ""
        prev_zh = bool(ZH_RE.match(prev)) if prev else False
        next_zh = bool(ZH_RE.match(nxt)) if nxt else False
        if ch in ",.:;":
            # 句读类：前为中文字符才算中文语境（小数点、英文缩写自然排除）
            if prev_zh:
                out.append((idx, ch, punct_map[ch]))
        elif ch == "(":
            # 前为中文、或括号内直接跟中文
            if prev_zh or next_zh:
                out.append((idx, ch, punct_map[ch]))
        elif ch == ")":
            if prev_zh or next_zh:
                out.append((idx, ch, punct_map[ch]))
    return out


def check_r2(lines, rules):
    cfg = rules["r2_punctuation"]
    findings = []
    for i, line, in_code in iter_body_lines(lines):
        if in_code:
            continue
        for col, half, full in _r2_matches_in_line(line, cfg["map"]):
            findings.append({
                "rule": "R2", "severity": cfg["severity"], "line": i,
                "snippet": snippet(line), "hit": half,
                "message": f"中文语境出现半角标点「{half}」（应为「{full}」）",
                "suggestion": cfg["suggestion"],
            })
    return findings


# ---------------------------------------------------------------- R3 口语化

def check_r3(lines, rules):
    cfg = rules["r3_colloquial"]
    findings = []
    hen_wl = re.compile(cfg.get("hen_whitelist", r"$^"))
    hen = cfg.get("hen_term", "很")
    for i, line, in_code in iter_body_lines(lines):
        if in_code or is_heading(line):
            continue
        for term in cfg["terms"]:
            if term in line:
                findings.append({
                    "rule": "R3", "severity": cfg["severity"], "line": i,
                    "snippet": snippet(line), "hit": term,
                    "message": f"口语化用词「{term}」",
                    "suggestion": cfg["suggestion"],
                })
        # 程度副词「很」：白名单语境（很可能/很多/很少…）豁免
        for m in re.finditer(re.escape(hen), line):
            ctx = line[m.start(): m.start() + 3]
            if not hen_wl.match(ctx):
                findings.append({
                    "rule": "R3", "severity": cfg["severity"], "line": i,
                    "snippet": snippet(line), "hit": hen,
                    "message": "程度副词「很」属口语化强度词（白名单语境除外）",
                    "suggestion": cfg["suggestion"],
                })
    return findings


# ---------------------------------------------------------------- R4 夸大词

def check_r4(lines, rules):
    cfg = rules["r4_exaggeration"]
    findings = []
    for i, line, in_code in iter_body_lines(lines):
        if in_code or is_heading(line):
            continue
        for term in cfg["terms"]:
            if term in line:
                # 同行附「材料依据」标注则豁免（视为作者已自证）
                if cfg.get("evidence_marker") and cfg["evidence_marker"] in line:
                    continue
                findings.append({
                    "rule": "R4", "severity": cfg["severity"], "line": i,
                    "snippet": snippet(line), "hit": term,
                    "message": f"夸大/越级表述「{term}」",
                    "suggestion": cfg["suggestion"],
                })
    return findings


# ---------------------------------------------------------------- R5 强度校准

def scan_material_strength(material_texts, cfg):
    """扫描材料文本的证据强度信号。
    返回 (level, signals)：level ∈ {"L1","strong","none"}。
    L1 = 仅见初步/小样本信号；strong = 见强证据设计信号；none = 无任何信号。"""
    l1_hits, strong_hits = [], []
    small_re = re.compile(cfg["small_sample_regex"])
    threshold = cfg.get("small_sample_threshold", 30)
    for text in material_texts:
        for w in cfg["material_l1_signals"]:
            if w in text:
                l1_hits.append(w)
        for w in cfg["material_strong_signals"]:
            if w in text:
                strong_hits.append(w)
        for m in small_re.finditer(text):
            if int(m.group(1)) < threshold:
                l1_hits.append(f"小样本标记 n={m.group(1)}")
    if strong_hits:
        return "strong", sorted(set(strong_hits))
    if l1_hits:
        return "L1", sorted(set(l1_hits))
    return "none", []


def check_r5(lines, rules, material_texts, materials_provided):
    cfg = rules["r5_strength"]
    findings = []
    l3_pat = re.compile("|".join(re.escape(w) for w in cfg["l3_markers"]))
    level, signals = ("none", [])
    if materials_provided:
        level, signals = scan_material_strength(material_texts, cfg)
    for i, line, in_code in iter_body_lines(lines):
        if in_code or is_heading(line):
            continue
        for sent in split_sentences(line):
            m = l3_pat.search(sent)
            if not m:
                continue
            if not materials_provided or level == "none":
                findings.append({
                    "rule": "R5", "severity": "低", "line": i,
                    "snippet": snippet(sent), "hit": m.group(0),
                    "message": f"L3 定论措辞「{m.group(0)}」，但材料中未检出证据强度信号，请人工确认证据等级",
                    "suggestion": cfg["suggestion"],
                })
            elif level == "L1":
                findings.append({
                    "rule": "R5", "severity": "高", "line": i,
                    "snippet": snippet(sent), "hit": m.group(0),
                    "message": (
                        f"CALIBRATION-MISMATCH：稿件使用 L3 定论措辞「{m.group(0)}」，"
                        f"但材料仅含 L1 初步证据信号（{ '、'.join(signals[:5]) }）"
                    ),
                    "suggestion": cfg["suggestion"],
                })
            # level == "strong"：材料支持强断言，不报
    return findings


# ---------------------------------------------------------------- R6 因果越界

def check_r6(lines, rules, material_texts, materials_provided):
    cfg = rules["r6_causality"]
    findings = []
    all_material = "\n".join(material_texts) if materials_provided else ""
    has_design = any(sig in all_material for sig in cfg["design_signals"])
    if has_design:
        return findings  # 材料含因果设计信号，不启用本条
    verb_pat = re.compile("|".join(re.escape(v) for v in cfg["causal_verbs"]))
    section = ""
    for i, line, in_code in iter_body_lines(lines):
        if in_code:
            continue
        h = is_heading(line)
        if h is not None:
            section = h
            continue
        if not any(s in section for s in cfg["sections"]):
            continue
        for m in verb_pat.finditer(line):
            findings.append({
                "rule": "R6", "severity": cfg["severity"], "line": i,
                "snippet": snippet(line), "hit": m.group(0),
                "message": (
                    f"「{section}」章节出现因果动词「{m.group(0)}」，"
                    "但材料未出现因果设计信号（随机对照/干预实验等）"
                ),
                "suggestion": cfg["suggestion"],
            })
    return findings


# ---------------------------------------------------------------- R7 缩写规范

def check_r7(lines, rules):
    cfg = rules["r7_abbreviation"]
    token_pat = re.compile(cfg["token_pattern"])
    ignore = set(cfg.get("ignore", []))
    findings = []
    seen = {}  # abbr -> {"definition_line": int|None}
    for i, line, in_code in iter_body_lines(lines):
        if in_code:
            continue
        tokens = [t for t in token_pat.findall(line) if t not in ignore]
        for tok in tokens:
            def_pat = re.compile(
                f"[{ZH}]{{2,}}[（(]\\s*{re.escape(tok)}\\s*[）)]"
            )
            defined_here = bool(def_pat.search(line))
            if tok not in seen:
                # 首次出现：必须以「中文全称（ABBR）」定义
                seen[tok] = {"definition_line": i if defined_here else None}
                if not defined_here:
                    findings.append({
                        "rule": "R7", "severity": cfg["severity_undefined"], "line": i,
                        "snippet": snippet(line), "hit": tok,
                        "message": f"缩写「{tok}」首次出现未以「中文全称（{tok}）」模式定义",
                        "suggestion": cfg["suggestion"],
                    })
            elif defined_here:
                if seen[tok]["definition_line"] is not None:
                    findings.append({
                        "rule": "R7", "severity": cfg["severity_redefined"], "line": i,
                        "snippet": snippet(line), "hit": tok,
                        "message": f"缩写「{tok}」在第 {seen[tok]['definition_line']} 行已定义，此处重复定义",
                        "suggestion": cfg["suggestion"],
                    })
                else:
                    # 此前裸用已报「未定义」，此处为迟到的首次定义，仅登记不再报
                    seen[tok]["definition_line"] = i
    return findings


# ---------------------------------------------------------------- R8 术语一致

def load_glossary(workdir: Path, filename: str):
    """解析 glossary.lock：每行 `标准形式 <= 变体1 | 变体2`（# 开头为注释）。"""
    entries = []
    path = workdir / filename
    if not path.exists():
        return entries
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "<=" not in line:
            continue
        canonical, variants = line.split("<=", 1)
        canonical = canonical.strip()
        vs = [v.strip() for v in re.split(r"[|，,]", variants) if v.strip()]
        if canonical and vs:
            entries.append((canonical, vs))
    return entries


def extract_term_candidates(lines, cfg):
    """自动抽取候选术语：≥2 字中文复合词、全文频次 ≥ min_freq。
    返回 [(形式, 频次)]，仅保留不被等频更长形式吸收的最大项。"""
    text = "\n".join(line for _, line, in_code in iter_body_lines(lines) if not in_code)
    seqs = re.findall(f"[{ZH}]{{2,}}", text)
    min_len, max_len = cfg["min_term_len"], cfg["max_term_len"]
    counts = {}
    for seq in seqs:
        upper = min(len(seq), max_len)
        for n in range(min_len, upper + 1):
            for j in range(0, len(seq) - n + 1):
                gram = seq[j: j + n]
                counts[gram] = counts.get(gram, 0) + 1
    min_freq = cfg["min_freq"]
    cands = {g: c for g, c in counts.items() if c >= min_freq}
    # 吸收规则：若某短形式的全部出现都被一个等频的更长形式覆盖，则丢弃短形式
    maximal = {}
    for g, c in cands.items():
        absorbed = False
        for g2, c2 in cands.items():
            if len(g2) > len(g) and g in g2 and c2 == c:
                absorbed = True
                break
        if not absorbed:
            maximal[g] = c
    return sorted(maximal.items(), key=lambda kv: (-kv[1], kv[0]))


def check_r8(lines, rules, workdir):
    cfg = rules["r8_terminology"]
    findings = []
    full_text_lines = [(i, l) for i, l, c in iter_body_lines(lines) if not c]

    # (a) glossary.lock 变体检索
    for canonical, variants in load_glossary(Path(workdir), cfg["glossary_filename"]):
        for i, line in full_text_lines:
            for v in variants:
                if v in line and canonical not in line:
                    findings.append({
                        "rule": "R8", "severity": cfg["severity"], "line": i,
                        "snippet": snippet(line), "hit": v,
                        "message": f"glossary.lock 锁定「{canonical}」，此处使用变体「{v}」",
                        "suggestion": cfg["suggestion"],
                    })

    # (b) 自动候选术语组：共享 ≥2 字核心子串但表面形式不同 → 交模型裁决
    cands = extract_term_candidates(lines, cfg)
    groups = []
    used = set()
    for idx, (g1, c1) in enumerate(cands):
        if g1 in used:
            continue
        mates = []
        for g2, c2 in cands[idx + 1:]:
            if g2 in used or g2 == g1:
                continue
            # 公共子串长度 ≥2 且形式不同（排除真子串：吸收规则已处理等频情形）
            common = max(
                (g1[k: k + n] for n in range(2, min(len(g1), len(g2)) + 1)
                 for k in range(0, len(g1) - n + 1) if g1[k: k + n] in g2),
                key=len, default=""
            )
            if len(common) >= 2 and g1 not in g2 and g2 not in g1:
                mates.append((g2, c2))
        if mates:
            group = [(g1, c1)] + mates
            for g, _ in group:
                used.add(g)
            groups.append(group)
        if len(groups) >= cfg["max_groups"]:
            break
    for group in groups:
        desc = " / ".join(f"{g}（{c} 次）" for g, c in group)
        findings.append({
            "rule": "R8", "severity": cfg["severity"], "line": 0,
            "snippet": desc, "hit": desc,
            "message": f"候选术语组表面形式不一致：{desc}，请模型裁决统一译名",
            "suggestion": cfg["suggestion"],
        })
    return findings


# ---------------------------------------------------------------- 报告与修复

def summarize(findings):
    stats = {}
    for f in findings:
        r = stats.setdefault(f["rule"], {"高": 0, "中": 0, "低": 0})
        r[f["severity"]] += 1
    totals = {"高": 0, "中": 0, "低": 0}
    for f in findings:
        totals[f["severity"]] += 1
    return {"by_rule": stats, "totals": totals, "total": len(findings)}


def render_report(findings, stats, draft_path, material_paths):
    """生成 style_report.md：带行号、规则号、严重级、原文片段、修改建议。"""
    out = []
    out.append("# style_report.md — 中文学术文体 lint 报告\n")
    out.append(f"- 稿件：`{draft_path}`")
    mats = "、".join(f"`{p}`" for p in material_paths) if material_paths else "（未提供材料，R5/R6 降级为提示模式）"
    out.append(f"- 材料：{mats}")
    t = stats["totals"]
    out.append(f"- 合计 {stats['total']} 条：高 {t['高']} / 中 {t['中']} / 低 {t['低']}\n")
    out.append("## 规则命中汇总\n")
    out.append("| 规则 | 高 | 中 | 低 |")
    out.append("|------|----|----|----|")
    for rule in sorted(stats["by_rule"]):
        s = stats["by_rule"][rule]
        out.append(f"| {rule} | {s['高']} | {s['中']} | {s['低']} |")
    out.append("\n## 明细（按行号排序）\n")
    out.append("| 行号 | 规则 | 严重级 | 命中 | 原文片段 | 问题 | 修改建议 |")
    out.append("|------|------|--------|------|----------|------|----------|")
    for f in sorted(findings, key=lambda x: (x["line"], SEV_ORDER[x["severity"]], x["rule"])):
        cells = [str(f["line"]), f["rule"], f["severity"], f["hit"],
                 snippet(f["snippet"], 40), f["message"], snippet(f["suggestion"], 40)]
        cells = [c.replace("|", "\\|").replace("\n", " ") for c in cells]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    return "\n".join(out)


def apply_fixes(text: str, rules):
    """--fix：只自动修 R2（全角化）与 R1 无歧义替换。返回 (新文本, fix_log)。"""
    fix_log = []
    punct_map = rules["r2_punctuation"]["map"]
    autofix_map = rules["r1_person"]["autofix_map"]
    new_lines = []
    lines = text.splitlines()
    in_code = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            new_lines.append(line)
            continue
        if in_code:
            new_lines.append(line)
            continue
        # R1 无歧义替换（笔者→本文，我们→本研究）
        for src, dst in autofix_map.items():
            start = 0
            while True:
                j = line.find(src, start)
                if j < 0:
                    break
                fix_log.append({
                    "rule": "R1", "line": i, "column": j + 1,
                    "original": src, "replacement": dst,
                    "context": snippet(line, 50),
                })
                line = line[:j] + dst + line[j + len(src):]
                start = j + len(dst)
        # R2 全角化（从右往左替换避免列号漂移）
        for col, half, full in sorted(_r2_matches_in_line(line, punct_map), reverse=True):
            fix_log.append({
                "rule": "R2", "line": i, "column": col + 1,
                "original": half, "replacement": full,
                "context": snippet(line, 50),
            })
            line = line[:col] + full + line[col + 1:]
        new_lines.append(line)
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), fix_log


# ---------------------------------------------------------------- 主流程

def run_checks(draft_text, rules, material_texts, materials_provided, workdir):
    lines = draft_text.splitlines()
    findings = []
    findings += check_r1(lines, rules)
    findings += check_r2(lines, rules)
    findings += check_r3(lines, rules)
    findings += check_r4(lines, rules)
    findings += check_r5(lines, rules, material_texts, materials_provided)
    findings += check_r6(lines, rules, material_texts, materials_provided)
    findings += check_r7(lines, rules)
    findings += check_r8(lines, rules, workdir)
    return findings


def main():
    ap = argparse.ArgumentParser(description="中文学术文体 lint 与措辞强度校准（R1–R8）")
    ap.add_argument("--draft", required=True, help="待检查的中文稿件（Markdown/纯文本）")
    ap.add_argument("--materials", nargs="*", default=[], help="材料文件（供 R5/R6 证据信号扫描）")
    ap.add_argument("--rules", default=None, help="规则表 JSON（默认 ../references/rules.json）")
    ap.add_argument("--workdir", default=".", help="工作目录（查找 glossary.lock）")
    ap.add_argument("--report", default=None, help="输出 style_report.md 路径")
    ap.add_argument("--findings-json", default=None, help="输出机器可读 findings JSON")
    ap.add_argument("--stats-json", default=None, help="输出统计 JSON（供 assemble_result.py）")
    ap.add_argument("--fix", action="store_true", help="自动修复 R2 全角化与 R1 无歧义替换")
    ap.add_argument("--out", default=None, help="--fix 修复后稿件输出路径")
    ap.add_argument("--fix-log", default=None, help="--fix 修复日志 fix_log.json 输出路径")
    ap.add_argument("--verify", action="store_true", help="复检模式：高级别项未清零时退出码为 1")
    args = ap.parse_args()

    rules_path = Path(args.rules) if args.rules else Path(__file__).resolve().parent.parent / "references" / "rules.json"
    if not rules_path.exists():
        print(f"错误：规则表不存在：{rules_path}（可用 --rules 指定）", file=sys.stderr)
        sys.exit(2)
    rules = load_rules(rules_path)

    draft_text = read_text(args.draft)

    # --fix 子流程：修复后写出，再继续对修复结果做检查
    if args.fix:
        fixed_text, fix_log = apply_fixes(draft_text, rules)
        out_path = args.out or str(Path(args.draft).with_suffix(".fixed.md"))
        Path(out_path).write_text(fixed_text, encoding="utf-8")
        if args.fix_log:
            Path(args.fix_log).write_text(
                json.dumps(fix_log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"--fix 完成：{len(fix_log)} 处自动修改（仅 R1/R2）→ {out_path}")
        draft_text = fixed_text  # 后续检查基于修复后文本

    material_texts = [read_text(p) for p in args.materials]
    materials_provided = len(material_texts) > 0

    findings = run_checks(draft_text, rules, material_texts, materials_provided, args.workdir)
    stats = summarize(findings)

    if args.report:
        Path(args.report).write_text(
            render_report(findings, stats, args.draft, args.materials), encoding="utf-8")
        print(f"报告已写出：{args.report}")
    if args.findings_json:
        Path(args.findings_json).write_text(
            json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.stats_json:
        Path(args.stats_json).write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    t = stats["totals"]
    print(f"检查完成：共 {stats['total']} 条（高 {t['高']} / 中 {t['中']} / 低 {t['低']}）")

    if args.verify:
        if t["高"] > 0:
            print(f"VERIFY FAIL：仍有 {t['高']} 条高级别项未处理")
            sys.exit(1)
        print("VERIFY PASS：高级别项已清零")
        sys.exit(0)


if __name__ == "__main__":
    main()
