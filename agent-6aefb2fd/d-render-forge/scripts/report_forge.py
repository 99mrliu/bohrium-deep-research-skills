#!/usr/bin/env python3
"""report_forge.py — 报告数字单源化：骨架生成 + 数字溯源核验。

子命令：

  scaffold  从统计 JSON 生成 report.md 骨架：统计结果小节的表格由 JSON 直接渲染
            （数字由机器引用，不经人手转录），其余小节留结构化占位由分析者填写。

  verify    数字溯源核验：提取 report 中全部 ≥3 位有效数字的数值字面量，
            逐一在 --sources 给出的 JSON 证据文件中寻找同值（按报告数字的精度
            做半末位容差匹配）。找不到即为"无源数字"——非零退出并列出。
            表格分隔符、坐标、版本号等豁免规则见 references/render_contract.md。

用法：
  python3 report_forge.py scaffold --stats statistics_group.json --out /app/output/report.md \
      --title "分析报告"
  python3 report_forge.py verify --report /app/output/report.md \
      --sources /app/output/statistics.json /app/work/cleaning_log.json ...
"""
import argparse
import json
import math
import os
import re
import sys

NUM_RE = re.compile(r"(?<![\w.])(\d+\.\d+|\d+)(?![\w.])")


def iter_numbers(obj):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, list):
        for x in obj:
            yield from iter_numbers(x)
    elif isinstance(obj, dict):
        for x in obj.values():
            yield from iter_numbers(x)


def sig_digits(s):
    t = s.lstrip("0").replace(".", "").lstrip("0")
    return len(t) if t else 1


def matches(x, nd, y):
    """报告数字 x（nd 位有效数字）与源值 y 在半末位容差内是否同值。"""
    if x == 0:
        return abs(y) < 1e-12
    mag = math.floor(math.log10(abs(x)))
    tol = 0.500001 * 10 ** (mag - nd + 1)
    return abs(x - y) <= tol


def collect_source_values(paths):
    vals = []
    for p in paths:
        try:
            doc = json.load(open(p, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"WARN: 证据文件不可读 {p}: {e}", file=sys.stderr)
            continue
        vals.extend(iter_numbers(doc))
    return vals


def cmd_scaffold(args):
    doc = json.load(open(args.stats, encoding="utf-8"))
    L = [f"# {args.title}", "",
         "<!-- 骨架由 report_forge.py scaffold 生成；统计小节的数字直接渲染自统计 JSON。",
         "     填写其余小节后必须运行 verify 通过才能交付。 -->", ""]
    L += ["## 1 数据与清洗口径", "", "<!-- 填写：数据来源、双源一致性结论、清洗规则与行数变化 -->", ""]
    if doc.get("mode") == "group_compare":
        L += ["## 2 前提检验与统计结果", "",
              f"检验族规模 m={doc['multiple_testing']['size']}，"
              f"Bonferroni 校正后 α={doc['multiple_testing']['bonferroni_alpha']}。", "",
              "| 特征 | 方法 | 统计量 | p 值 | 效应量 | 校正后显著 |",
              "|-|-|-|-|-|-|"]
        for f, r in doc["features"].items():
            if "error" in r:
                L.append(f"| {f} | 无法检验（{r['error']}） | — | — | — | — |")
                continue
            eff = next(iter(r["effect_size"].items()))
            L.append(f"| {f} | {r['method']} | {r['statistic']} | {r['p_value']} | "
                     f"{eff[0]}={eff[1]} | {'是' if r['significant_bonferroni_family'] else '否'} |")
        L += ["", "### 区分度排序（按效应量降序）", "",
              "| 排名 | 特征 | 效应量 | 方法 |", "|-|-|-|-|"]
        for i, r in enumerate(doc["discrimination_ranking"], 1):
            L.append(f"| {i} | {r['feature']} | {r['score']} | {r['method']} |")
        L.append("")
    elif doc.get("mode") == "regression":
        o = doc["ols_standardized"]
        L += ["## 2 相关与回归结果", "",
              f"n={doc['n']}；标准化 OLS：R²={o['r_squared']}，"
              f"调整 R²={o['adj_r_squared']}，残差 Shapiro p={o['residual_shapiro_p']}。", "",
              "| 特征 | Spearman ρ | ρ 的 p | 标准化 β | VIF |", "|-|-|-|-|-|"]
        for f in doc["features"]:
            sp = doc["spearman_with_target"][f]
            co = o["coefficients"][f]
            L.append(f"| {f} | {sp['rho']} | {sp['p']} | {co['beta_std']} | {co['vif']} |")
        L += ["", f"> 口径声明：{o['caveat']}", ""]
    L += ["## 3 图表", "", "<!-- 引用 figures/ 与 figures_manifest.json -->", "",
          "## 4 结论", "", "<!-- 结论逐条对应第 2 节的检验结果 -->", "",
          "## 5 异常与不确定性", "", "<!-- 缺失、异常、无法解释项；无则写'无未解释异常' -->", ""]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"REPORT_FORGE_STATUS: scaffold -> {args.out}")


def cmd_verify(args):
    text = open(args.report, encoding="utf-8").read()
    src_vals = collect_source_values(args.sources)
    problems = []
    for m in NUM_RE.finditer(text):
        s = m.group(0)
        nd = sig_digits(s)
        if nd < 3:
            continue  # 1–2 位数字（小节号、计数）豁免
        x = float(s)
        # 豁免：小节编号样式（行首数字+点）
        line_start = text.rfind("\n", 0, m.start()) + 1
        if re.match(r"^\s*\d+(\.\d+)*\s", text[line_start:m.end() + 1]):
            continue
        if not any(matches(x, nd, y) for y in src_vals):
            ctx = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
            problems.append({"value": s, "sig_digits": nd, "context": ctx})
    if problems:
        for p in problems:
            print(f"UNSOURCED_NUMBER: {p['value']} …{p['context']}…", file=sys.stderr)
        print(f"REPORT_VERIFY_FAIL: {len(problems)} 个无源数字", file=sys.stderr)
        sys.exit(6)
    print(f"REPORT_VERIFY_STATUS: ok all ≥3-sig-digit numbers traced to sources "
          f"({len(src_vals)} source values)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scaffold")
    s.add_argument("--stats", required=True); s.add_argument("--out", required=True)
    s.add_argument("--title", default="数据分析报告")
    v = sub.add_parser("verify")
    v.add_argument("--report", required=True)
    v.add_argument("--sources", nargs="+", required=True)
    args = ap.parse_args()
    {"scaffold": cmd_scaffold, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    main()
