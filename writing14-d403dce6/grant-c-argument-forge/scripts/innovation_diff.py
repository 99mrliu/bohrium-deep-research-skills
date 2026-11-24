#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""innovation_diff.py — 创新点“差异定位表”生成与校验。

两个子命令：

  generate  输入已有工作清单 JSON，生成“差异定位表”markdown 模板：
            已有工作 | 其局限(引原文) | 本研究差异 | 难点 | 可行性凭据
            JSON 结构：
              {"existing_works": [{"name": str, "method": str, "limitation": str}, ...],
               "candidates": [{"title": str, "works": [name, ...]}, ...]  # 可选}
            每个候选创新点一张表；无 candidates 时生成一张含全部已有工作的通用表。
            “其局限(引原文)”由 limitation 字段预填，其余三列为【待填】占位。

  check     校验已填表的完整性：任何空单元格或仍为【待填…】占位的单元格均记 error，
            并指明第几张表、第几行、哪一列。

退出码：0 成功/校验通过；1 校验发现 error；2 用法/IO/JSON 错误。
仅使用 Python3 标准库；确定性输出。
"""
import argparse
import json
import os
import re
import sys

COLUMNS = ["已有工作", "其局限(引原文)", "本研究差异", "难点", "可行性凭据"]
PLACEHOLDER = "【待填】"
PLACEHOLDER_RE = re.compile(r"^【待填.*】$")


def load_works(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("existing_works"), list) \
            or not data["existing_works"]:
        raise ValueError("JSON 须含非空 existing_works 列表")
    for i, w in enumerate(data["existing_works"]):
        for key in ("name", "method", "limitation"):
            if not isinstance(w.get(key), str) or not w[key].strip():
                raise ValueError("existing_works[%d] 缺字段或非空字符串：%s" % (i, key))
    return data


def render_table(works):
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    for w in works:
        row = [
            "%s（%s）" % (w["name"], w["method"]),
            "“%s”" % w["limitation"],
            PLACEHOLDER, PLACEHOLDER, PLACEHOLDER,
        ]
        lines.append("| " + " | ".join(row) + " |")
    return lines


def cmd_generate(args):
    try:
        data = load_works(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print("错误：读取已有工作清单失败：%s" % e, file=sys.stderr)
        return 2
    works_by_name = {w["name"]: w for w in data["existing_works"]}
    candidates = data.get("candidates") or []
    out = ["# 创新点差异定位表",
           "",
           "<!-- 由 innovation_diff.py generate 生成；填写后请用 innovation_diff.py check 校验。 -->",
           ""]
    if candidates:
        for c in candidates:
            title = c.get("title", "未命名创新点")
            names = c.get("works") or list(works_by_name)
            unknown = [n for n in names if n not in works_by_name]
            if unknown:
                print("错误：候选「%s」引用了未知已有工作：%s" % (title, "、".join(unknown)),
                      file=sys.stderr)
                return 2
            out.append("## 候选创新点：%s" % title)
            out.append("")
            out += render_table([works_by_name[n] for n in names])
            out.append("")
    else:
        out.append("## 候选创新点：（通用，覆盖全部已有工作）")
        out.append("")
        out += render_table(data["existing_works"])
        out.append("")
    text = "\n".join(out)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        print("错误：写出模板失败：%s" % e, file=sys.stderr)
        return 2
    print("innovation_diff generate: 已生成 %s（%d 项已有工作，%d 个候选创新点）" % (
        args.output, len(data["existing_works"]), max(1, len(candidates))))
    return 0


def split_row(line):
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def cmd_check(args):
    try:
        with open(args.input, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError as e:
        print("错误：无法读取表格文件 %s：%s" % (args.input, e), file=sys.stderr)
        return 2
    errors = []
    tables = 0
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block, j = [], i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                block.append((j + 1, lines[j]))
                j += 1
            tables += 1
            if len(block) < 3:
                errors.append({"line": block[0][0],
                               "message": "第 %d 张表行数不足（须含表头、分隔行与至少一行数据）" % tables})
                i = j
                continue
            header = split_row(block[0][1])
            for ln, row_line in block[2:]:
                cells = split_row(row_line)
                for k, cell in enumerate(cells):
                    col = header[k] if k < len(header) else "第%d列" % (k + 1)
                    if not cell:
                        errors.append({"line": ln,
                                       "message": "第 %d 张表：第 %d 行「%s」为空单元格" % (
                                           tables, ln, col)})
                    elif PLACEHOLDER_RE.match(cell):
                        errors.append({"line": ln,
                                       "message": "第 %d 张表：第 %d 行「%s」仍为占位符 %s" % (
                                           tables, ln, col, cell)})
            i = j
        else:
            i += 1
    if tables == 0:
        errors.append({"line": 0, "message": "未在文件中发现任何 markdown 表格"})

    report = {"input": os.path.abspath(args.input), "tables": tables,
              "errors": errors, "pass": not errors}
    try:
        outdir = args.outdir or os.path.dirname(os.path.abspath(args.input))
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "innovation_diff_report.json"), "w",
                  encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    except OSError as e:
        print("错误：写出报告失败：%s" % e, file=sys.stderr)
        return 2
    print("innovation_diff check: 表格 %d 张，error %d 处" % (tables, len(errors)))
    for e in errors:
        print("  行 %s: %s" % (e["line"], e["message"]))
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="由已有工作清单 JSON 生成差异定位表模板")
    g.add_argument("input", help="已有工作清单 JSON 路径")
    g.add_argument("-o", "--output", required=True, help="输出 markdown 模板路径")
    g.set_defaults(func=cmd_generate)
    c = sub.add_parser("check", help="校验已填差异定位表的完整性")
    c.add_argument("input", help="已填写的差异定位表 markdown 路径")
    c.add_argument("-o", "--outdir", default=None,
                   help="报告输出目录（默认与输入文件同目录），写 innovation_diff_report.json")
    c.set_defaults(func=cmd_check)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
