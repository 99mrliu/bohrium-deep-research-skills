#!/usr/bin/env python3
"""xref_check.py — 结果与讨论稿件的图表交叉引用审计工具。

功能:
  1. 收集浮动体定义(图/表题注行), 形如 "图1. ..." "Figure 2: ..." "表1. ..." "Table 2. ...";
  2. 收集正文引用(callout), 形如 "图1" "见图2a" "Table 1" "Fig. 3";
  3. 审计:
     * 每个已定义浮动体至少在正文被引用一次;
     * 每个正文引用都能解析到已定义浮动体;
     * 同类浮动体编号连续(无缺号/重号);
     * 每个浮动体都有题注语句;
     * 首次提及顺序与编号顺序一致(仅警告);
  4. --fix-renumber: 按题注出现顺序将编号重写为连续序列(题注与正文引用一并改写),
     并输出 moves.json 供 change_log 使用。

用法:
    python3 xref_check.py --input manuscript.md --report-md xref_report.md --report-json xref_report.json
    python3 xref_check.py --input manuscript.md --fix-renumber manuscript_fixed.md --moves moves.json

退出码: 0 = 无错误(可有警告); 1 = 存在错误; 2 = 用法/IO 错误。
仅使用 Python 标准库, 兼容 Python >= 3.9。
"""

import argparse
import json
import re
import sys

# 题注定义: 行首为标记+编号+分隔符+题注文字
CAPTION_RE = re.compile(
    r"^\s*(图|表|Figure|Fig\.?|Table)\s*(\d+)\s*([.．:：])\s*(\S.*?)\s*$"
)
# 正文引用: 任意位置的标记+编号+可选子图字母
CALLOUT_RE = re.compile(r"(图|表|Figure|Fig\.?|Table)\s*(\d+)([a-z]?)")

KIND_MAP = {
    "图": "figure",
    "表": "table",
    "Figure": "figure",
    "Fig": "figure",
    "Fig.": "figure",
    "Table": "table",
}
KIND_LABEL = {"figure": "图", "table": "表"}


def kind_of(token):
    return KIND_MAP.get(token, KIND_MAP.get(token.rstrip(".")))


def parse_manuscript(text):
    """返回 (floats, callouts)。

    floats:   list[dict(kind, num, token, caption, line_no)]
    callouts: list[dict(kind, num, token, suffix, line_no)]  (不含题注行本身)
    """
    floats = []
    callouts = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        cap = CAPTION_RE.match(line)
        if cap:
            token, num, _sep, caption = cap.groups()
            floats.append(
                {
                    "kind": kind_of(token),
                    "num": int(num),
                    "token": token,
                    "caption": caption,
                    "line_no": line_no,
                }
            )
            continue  # 题注行不再计入正文引用
        for m in CALLOUT_RE.finditer(line):
            token, num, suffix = m.groups()
            callouts.append(
                {
                    "kind": kind_of(token),
                    "num": int(num),
                    "token": token,
                    "suffix": suffix,
                    "line_no": line_no,
                }
            )
    return floats, callouts


def audit(floats, callouts):
    """返回 (errors, warnings, registry)。"""
    errors = []
    warnings = []
    registry = []

    by_kind = {}
    for fl in floats:
        by_kind.setdefault(fl["kind"], []).append(fl)

    # 重号 / 空题注 / 编号连续性
    for kind, items in sorted(by_kind.items()):
        seen = {}
        for fl in items:
            seen.setdefault(fl["num"], []).append(fl["line_no"])
            if not fl["caption"].strip():
                errors.append(
                    "%s%d (第%d行) 缺少题注语句" % (KIND_LABEL[kind], fl["num"], fl["line_no"])
                )
        for num, lines in sorted(seen.items()):
            if len(lines) > 1:
                errors.append(
                    "%s%d 题注重复定义(第%s行)"
                    % (KIND_LABEL[kind], num, ", ".join(map(str, lines)))
                )
        nums = sorted(seen)
        if nums:
            expected = list(range(1, len(nums) + 1))
            if nums != expected:
                errors.append(
                    "%s类编号不连续: 实际为 %s, 应为 %s"
                    % (KIND_LABEL[kind], nums, expected)
                )

    defined = {(fl["kind"], fl["num"]) for fl in floats}
    cite_count = {}
    for co in callouts:
        key = (co["kind"], co["num"])
        if key not in defined:
            errors.append(
                "第%d行引用了未定义的 %s%d%s"
                % (co["line_no"], KIND_LABEL[co["kind"]], co["num"], co["suffix"])
            )
        else:
            cite_count[key] = cite_count.get(key, 0) + 1

    for fl in floats:
        key = (fl["kind"], fl["num"])
        n = cite_count.get(key, 0)
        if n == 0:
            errors.append(
                "%s%d (题注在第%d行) 从未在正文中被引用"
                % (KIND_LABEL[fl["kind"]], fl["num"], fl["line_no"])
            )
        registry.append(
            {
                "kind": fl["kind"],
                "num": fl["num"],
                "caption": fl["caption"],
                "caption_line": fl["line_no"],
                "citations": n,
            }
        )

    # 首次提及顺序(仅警告)
    first_mention = {}
    for co in callouts:
        key = (co["kind"], co["num"])
        if key in defined and key not in first_mention:
            first_mention[key] = co["line_no"]
    for kind in sorted(by_kind):
        ordered = sorted(
            ((num, first_mention[(kind, num)]) for (k, num) in first_mention if k == kind),
            key=lambda t: t[1],
        )
        mention_nums = [num for num, _ln in ordered]
        if mention_nums != sorted(mention_nums):
            warnings.append(
                "%s类首次提及顺序 %s 与编号顺序不一致"
                % (KIND_LABEL[kind], mention_nums)
            )

    return errors, warnings, registry


def build_renumber_map(floats):
    """按题注出现顺序为每类浮动体分配连续编号, 返回 {kind: {old_num_str: new_num}}。"""
    maps = {}
    counters = {}
    for fl in floats:  # floats 已按行号顺序收集
        kind = fl["kind"]
        counters[kind] = counters.get(kind, 0) + 1
        kind_map = maps.setdefault(kind, {})
        old = str(fl["num"])
        if old not in kind_map:  # 重号时以首次出现为准
            kind_map[old] = counters[kind]
    return maps


def apply_renumber(text, maps):
    """单遍正则替换, 同时改写题注与正文引用中的编号, 保留原标记与子图字母。"""

    def _sub(m):
        token, num, suffix = m.groups()
        kind = kind_of(token)
        new = maps.get(kind, {}).get(num)
        if new is None:
            return m.group(0)
        return "%s%s%s" % (token, new, suffix)

    return CALLOUT_RE.sub(_sub, text)


def render_report_md(input_path, errors, warnings, registry, fixes=None):
    lines = []
    lines.append("# 图表交叉引用审计报告")
    lines.append("")
    lines.append("- 输入稿件: `%s`" % input_path)
    status = "PASS" if not errors else "FAIL"
    lines.append(
        "- 审计结果: **%s**(错误 %d 项, 警告 %d 项)" % (status, len(errors), len(warnings))
    )
    if fixes:
        lines.append("- 已执行重编号修复: `%s`" % fixes)
    lines.append("")
    lines.append("## 浮动体注册表")
    lines.append("")
    lines.append("| 类型 | 编号 | 题注所在行 | 正文引用次数 | 题注 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in sorted(registry, key=lambda r: (r["kind"], r["num"])):
        cap = item["caption"]
        if len(cap) > 40:
            cap = cap[:40] + "…"
        lines.append(
            "| %s | %d | %d | %d | %s |"
            % (KIND_LABEL[item["kind"]], item["num"], item["caption_line"], item["citations"], cap)
        )
    if not registry:
        lines.append("| (无) | | | | |")
    lines.append("")
    lines.append("## 问题清单")
    lines.append("")
    lines.append("### 错误")
    lines.append("")
    if errors:
        for e in errors:
            lines.append("- %s" % e)
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("### 警告")
    lines.append("")
    if warnings:
        for w in warnings:
            lines.append("- %s" % w)
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="图表交叉引用审计: 校验题注定义、正文引用与编号连续性。"
    )
    parser.add_argument("--input", required=True, help="稿件 markdown 路径")
    parser.add_argument("--report-md", help="审计报告 markdown 输出路径")
    parser.add_argument("--report-json", help="审计报告 JSON 输出路径")
    parser.add_argument(
        "--fix-renumber",
        metavar="OUT_MD",
        help="按题注出现顺序重编号, 改写后的稿件写入该路径",
    )
    parser.add_argument("--moves", help="重编号映射 moves.json 输出路径(配合 --fix-renumber)")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        sys.stderr.write("ERROR: cannot read %s: %s\n" % (args.input, exc))
        return 2

    floats, callouts = parse_manuscript(text)
    errors, warnings, registry = audit(floats, callouts)

    fixes_label = None
    moves_payload = None
    remaining = errors
    if args.fix_renumber:
        maps = build_renumber_map(floats)
        changed = {
            kind: {old: new for old, new in m.items() if int(old) != new}
            for kind, m in maps.items()
        }
        changed = {k: v for k, v in changed.items() if v}
        fixed_text = apply_renumber(text, maps)
        try:
            with open(args.fix_renumber, "w", encoding="utf-8") as fh:
                fh.write(fixed_text)
        except OSError as exc:
            sys.stderr.write("ERROR: cannot write %s: %s\n" % (args.fix_renumber, exc))
            return 2
        moves_payload = {
            "input": args.input,
            "output": args.fix_renumber,
            "renumber": changed,
            "note": "编号按题注出现顺序重写为连续序列; 题注与正文引用一并改写。",
        }
        if args.moves:
            try:
                with open(args.moves, "w", encoding="utf-8") as fh:
                    json.dump(moves_payload, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
            except OSError as exc:
                sys.stderr.write("ERROR: cannot write %s: %s\n" % (args.moves, exc))
                return 2
        fixes_label = args.fix_renumber
        # 修复后重新审计, 以剩余错误决定退出码
        f_floats, f_callouts = parse_manuscript(fixed_text)
        remaining, _w2, _r2 = audit(f_floats, f_callouts)

    report_md = render_report_md(args.input, errors, warnings, registry, fixes_label)
    if args.report_md:
        try:
            with open(args.report_md, "w", encoding="utf-8") as fh:
                fh.write(report_md)
        except OSError as exc:
            sys.stderr.write("ERROR: cannot write %s: %s\n" % (args.report_md, exc))
            return 2

    report_json = {
        "input": args.input,
        "status": "PASS" if not remaining else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "errors_after_fix": remaining if args.fix_renumber else None,
        "floats": registry,
        "moves": moves_payload,
    }
    if args.report_json:
        try:
            with open(args.report_json, "w", encoding="utf-8") as fh:
                json.dump(report_json, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        except OSError as exc:
            sys.stderr.write("ERROR: cannot write %s: %s\n" % (args.report_json, exc))
            return 2

    sys.stdout.write(report_md.splitlines()[2] + "\n")
    if args.fix_renumber:
        sys.stdout.write(
            "fix-renumber: wrote %s; residual errors after fix: %d\n"
            % (args.fix_renumber, len(remaining))
        )
    if not args.report_md and not args.report_json:
        sys.stdout.write(report_md + "\n")

    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
