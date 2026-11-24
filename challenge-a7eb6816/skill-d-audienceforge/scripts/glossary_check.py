#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glossary_check.py — 术语表一致性检查器。

加载 glossary.tsv（列：source_term<TAB>approved_rendering<TAB>expansion<TAB>forbidden_synonyms，
forbidden_synonyms 逗号分隔；'#' 开头为注释；首列为 'source_term' 的行视为表头）。
约定：expansion 末位括号内以「；」或「;」分段，最后一个含拉丁字母的分段视为英文批准译法，
供 --pair 双语对齐使用，如「碳捕集利用与封存（CCUS；Carbon Capture, Utilization and Storage）」。

单稿模式（--text）：
  (a) 出现 forbidden_synonyms → 记 inconsistent_term（带行号与替换建议）；
  (b) approved_rendering 首次出现的行内必须带 expansion 的至少一个括号分段
      （即首次出现须展开，如「碳捕集利用与封存（CCUS）」），否则记 missing_expansion。

双语模式（--pair zh.md en.md）：
  除对两稿分别执行 (a)(b) 外，统计同一 source_term 的批准中文译法在中文稿出现次数
  与英文批准译法在英文稿出现次数（英文计数不区分大小写）：
    - 一侧为 0 另一侧非 0 → 记 count_mismatch（译法缺失）；
    - 两侧均非 0 且 max/min > --ratio-threshold（默认 3.0）→ 记 count_mismatch；
    - 否则视为「差距可解释」，计入 notes。

退出码：
  0  全部通过
  7  存在 inconsistent_term / missing_expansion / count_mismatch
  1  用法错误 / IO 错误 / 术语表格式错误
"""
import argparse
import json
import os
import re
import sys


def load_glossary(path):
    terms = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if parts[0].strip() == "source_term":
                continue
            if len(parts) < 4:
                raise ValueError(f"第 {ln} 行列数不足 4：{line!r}")
            terms.append({
                "source_term": parts[0].strip(),
                "approved_rendering": parts[1].strip(),
                "expansion": parts[2].strip(),
                "forbidden_synonyms": [s.strip() for s in parts[3].split(",") if s.strip()],
            })
    if not terms:
        raise ValueError("术语表为空")
    return terms


def expansion_tokens(expansion):
    """取 expansion 末位括号内的分段列表，如 ['CCUS', 'Carbon Capture, Utilization and Storage']。"""
    m = re.search(r"[（(]([^（）()]*)[)）]\s*$", expansion)
    if not m:
        return []
    return [seg.strip() for seg in re.split(r"[；;]", m.group(1)) if seg.strip()]


def english_rendering(expansion):
    toks = expansion_tokens(expansion)
    if toks and re.search(r"[A-Za-z]", toks[-1]):
        return toks[-1]
    return None


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def count_en(text, phrase):
    pat = r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])"
    return len(re.findall(pat, text, re.IGNORECASE))


def check_single(text, text_name, term, issues, details):
    approved = term["approved_rendering"]
    detail = {
        "source_term": term["source_term"],
        "approved_rendering": approved,
        "approved_count": text.count(approved),
        "forbidden_hits": [],
        "first_occurrence_expanded": None,
    }
    # (a) 禁用同义词
    for syn in term["forbidden_synonyms"]:
        start = 0
        while True:
            i = text.find(syn, start)
            if i < 0:
                break
            ln = line_of(text, i)
            detail["forbidden_hits"].append({"synonym": syn, "line": ln})
            issues.append({
                "type": "inconsistent_term",
                "file": text_name,
                "line": ln,
                "source_term": term["source_term"],
                "found": syn,
                "message": f"出现禁用同义词「{syn}」（第 {ln} 行），请统一为批准术语「{approved}」。",
                "suggestion": f"将「{syn}」替换为「{approved}」。",
            })
            start = i + len(syn)
    # (b) 首次出现须带 expansion
    idx = text.find(approved)
    if idx >= 0:
        ln = line_of(text, idx)
        first_line_text = text.split("\n")[ln - 1]
        toks = expansion_tokens(term["expansion"])
        ok = any(tok in first_line_text for tok in toks) if toks else False
        detail["first_occurrence_expanded"] = ok
        detail["first_occurrence_line"] = ln
        if not ok:
            issues.append({
                "type": "missing_expansion",
                "file": text_name,
                "line": ln,
                "source_term": term["source_term"],
                "found": approved,
                "message": (
                    f"批准术语「{approved}」在第 {ln} 行首次出现时未带展开"
                    f"（期望同段出现 expansion 片段：{' / '.join(toks) or '无'}）。"
                ),
                "suggestion": f"首次出现写为「{term['expansion']}」或其等价形式。",
            })
    else:
        detail["note"] = "批准术语未在本稿出现，跳过首次展开检查。"
    details.append(detail)


def main():
    ap = argparse.ArgumentParser(description="术语表一致性检查（同义词收敛 / 首次展开 / 双语对齐）")
    ap.add_argument("--glossary", required=True, help="glossary.tsv 路径")
    ap.add_argument("--text", default=None, help="单稿模式：待检查稿件路径")
    ap.add_argument("--pair", nargs=2, metavar=("ZH", "EN"), default=None, help="双语模式：中文稿 英文稿")
    ap.add_argument("--ratio-threshold", type=float, default=3.0, help="双语出现次数比例阈值（默认 3.0）")
    ap.add_argument("--out-json", default=None, help="输出 JSON 报告路径（缺省打印到 stdout）")
    ap.add_argument("--out-md", default=None, help="输出 Markdown 报告路径")
    args = ap.parse_args()

    if bool(args.text) == bool(args.pair):
        print("[ERROR] 必须且只能指定 --text 或 --pair 之一", file=sys.stderr)
        return 1

    try:
        terms = load_glossary(args.glossary)
    except (OSError, ValueError) as e:
        print(f"[ERROR] 术语表加载失败 {args.glossary}: {e}", file=sys.stderr)
        return 1

    issues = []
    details = []
    notes = []
    files = {}
    if args.text:
        files[args.text] = None
    else:
        files[args.pair[0]] = "zh"
        files[args.pair[1]] = "en"
    texts = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                texts[path] = f.read()
        except OSError as e:
            print(f"[ERROR] 无法读取稿件 {path}: {e}", file=sys.stderr)
            return 1

    for term in terms:
        for path in files:
            check_single(texts[path], os.path.basename(path), term, issues, details)

    pair_report = None
    if args.pair:
        zh_text, en_text = texts[args.pair[0]], texts[args.pair[1]]
        pair_rows = []
        for term in terms:
            en_render = english_rendering(term["expansion"])
            if not en_render:
                pair_rows.append({
                    "source_term": term["source_term"],
                    "note": "expansion 中未解析到英文批准译法，跳过双语对齐。",
                })
                continue
            zh_count = zh_text.count(term["approved_rendering"])
            en_count = count_en(en_text, en_render)
            row = {
                "source_term": term["source_term"],
                "zh_rendering": term["approved_rendering"],
                "en_rendering": en_render,
                "zh_count": zh_count,
                "en_count": en_count,
            }
            if zh_count == 0 and en_count == 0:
                row["status"] = "absent_both"
                notes.append(f"「{term['source_term']}」在两稿均未出现，跳过。")
            elif zh_count == 0 or en_count == 0:
                row["status"] = "missing_one_side"
                issues.append({
                    "type": "count_mismatch",
                    "file": f"{os.path.basename(args.pair[0])} <-> {os.path.basename(args.pair[1])}",
                    "line": None,
                    "source_term": term["source_term"],
                    "message": (
                        f"「{term['source_term']}」批准译法缺失：中文稿 {zh_count} 次 / "
                        f"英文稿「{en_render}」{en_count} 次。"
                    ),
                    "suggestion": "两稿须都使用批准译法，请补齐或统一。",
                })
            else:
                ratio = max(zh_count, en_count) / min(zh_count, en_count)
                row["ratio"] = round(ratio, 3)
                if ratio > args.ratio_threshold:
                    row["status"] = "ratio_exceeded"
                    issues.append({
                        "type": "count_mismatch",
                        "file": f"{os.path.basename(args.pair[0])} <-> {os.path.basename(args.pair[1])}",
                        "line": None,
                        "source_term": term["source_term"],
                        "message": (
                            f"「{term['source_term']}」出现次数比例 {round(ratio, 3)} 超过阈值 "
                            f"{args.ratio_threshold}（中 {zh_count} / 英 {en_count}）。"
                        ),
                        "suggestion": "检查是否存在漏译、重复或改用非批准译法；若确属行文需要，可调高 --ratio-threshold 并说明。",
                    })
                else:
                    row["status"] = "ok"
                    notes.append(
                        f"「{term['source_term']}」中 {zh_count} 次 / 英 {en_count} 次，"
                        f"比例 {round(ratio, 3)} ≤ {args.ratio_threshold}，差距可解释。"
                    )
            pair_rows.append(row)
        pair_report = {
            "zh": args.pair[0],
            "en": args.pair[1],
            "ratio_threshold": args.ratio_threshold,
            "terms": pair_rows,
        }

    report = {
        "tool": "glossary_check.py",
        "mode": "pair" if args.pair else "single",
        "glossary": args.glossary,
        "terms_checked": len(terms),
        "issues": issues,
        "term_details": details,
        "pair": pair_report,
        "notes": notes,
        "exit_code": 0 if not issues else 7,
    }

    md_lines = [
        "# glossary_report",
        "",
        f"- 模式：{report['mode']}",
        f"- 术语表：{args.glossary}（{len(terms)} 条）",
        f"- 结论：{'全部通过' if not issues else f'发现 {len(issues)} 个问题'}",
        "",
        "## 问题清单",
    ]
    if issues:
        for it in issues:
            loc = f"第 {it['line']} 行" if it.get("line") else it.get("file", "")
            md_lines.append(f"- [{it['type']}] {loc}：{it['message']} 建议：{it['suggestion']}")
    else:
        md_lines.append("- 无")
    if pair_report:
        md_lines += ["", "## 双语对齐", "| source_term | 中文稿次数 | 英文译法 | 英文稿次数 | 状态 |",
                     "| --- | --- | --- | --- | --- |"]
        for r in pair_report["terms"]:
            md_lines.append(
                f"| {r['source_term']} | {r.get('zh_count', '-')} | "
                f"{r.get('en_rendering', '-')} | {r.get('en_count', '-')} | {r.get('status', r.get('note', '-'))} |"
            )
    if notes:
        md_lines += ["", "## 说明"] + [f"- {n}" for n in notes]
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

    print(f"[{'OK' if not issues else 'FAIL'}] glossary_check: issues={len(issues)}", file=sys.stderr)
    return 0 if not issues else 7


if __name__ == "__main__":
    sys.exit(main())
