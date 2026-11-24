#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hedge_scan.py — 章节稿"套话限制 + 静默填平 + 缺口点名"三项检查。

纯标准库、确定性、无网络。

用法：
    python3 hedge_scan.py --md <章节md> --materials <材料目录>
                          [--gaps <gaps.json>] --out-dir <输出目录>

检查项：
    1. 空泛限制句式：内置中/英套话模式表，命中即告警
       （限制必须指向具体失效场景：何种数据、何种条件、何种度量下失效）。
    2. 静默填平：正文中"参数语境行"内的数值若在材料中找不到任何来源
       （词边界精确匹配），记为无来源数值。
    3. 缺口点名：若提供 gaps.json，检查每个 G 编号是否在正文中出现
       （即是否都被"待作者确认"段点名）。

退出码：0 = PASS；2 = FAIL（任一检查未过）；1 = 用法/IO 错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

TEXT_EXTS = {
    ".md", ".txt", ".log", ".out", ".yaml", ".yml", ".json",
    ".py", ".sh", ".toml", ".ini", ".cfg", ".csv", ".tex",
}

# 空泛套话模式表：(编号, 语言, 正则, 修改建议)
HEDGE_PATTERNS = [
    ("ZH01", "zh", r"某些情况下可能不适用",
     "请写明在何种数据/条件下不适用、失效表现是什么。"),
    ("ZH02", "zh", r"在?某些(?:情况下|条件下|场景中)可能",
     "请把\"某些情况\"替换为具体失效场景。"),
    ("ZH03", "zh", r"可能存在一定的?局限",
     "请列出具体局限条目，不要泛指。"),
    ("ZH04", "zh", r"有待进一步(?:研究|验证|探索|讨论)",
     "请说明具体待验证的内容与当前证据边界。"),
    ("ZH05", "zh", r"未来工作将",
     "限制段应描述当前失效场景，而非用未来工作搪塞。"),
    ("ZH06", "zh", r"效果可能因.{0,8}而异",
     "请指明差异来源（数据规模/领域/硬件）及影响方向。"),
    ("ZH07", "zh", r"一般认为|众所周知",
     "请给出引证或删除该断言。"),
    ("EN01", "en", r"\bin some cases\b",
     "Replace with the concrete failure scenario."),
    ("EN02", "en", r"\bmay not (?:apply|generalize|work)\b",
     "State where and why it fails."),
    ("EN03", "en", r"\bfuture work\b",
     "Limitations must describe current failure modes, not defer to future work."),
    ("EN04", "en", r"\bto some extent\b",
     "Quantify or remove."),
    ("EN05", "en", r"\bit is generally believed\b",
     "Cite or remove."),
]

# “参数语境行”触发词：只有包含这些特征的行才做无来源数值检查
TRIGGER = re.compile(
    r"[=:=：%]|为|是|取|学习率|批|轮|比例|准确率|样本|种子|"
    r"epoch|lr|batch|seed|split|ratio|acc(?:uracy)?|loss|lr\b",
    re.IGNORECASE,
)

NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
LISTNUM_RE = re.compile(r"^\s*\d+[\.、\)]\s")   # 列表编号行首
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")       # 年份不做来源核查
CITE_RE = re.compile(r"[\w.\-/]+:\d+(?:-\d+)?")  # 来源定位 file:line(-line)，非陈述数值


def read_lines(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def material_text(materials_dir: str, exclude_abs: str):
    """拼接材料目录中全部文本（排除被审 md 自身），用于数值来源核查。"""
    chunks = []
    for root, dirs, files in os.walk(materials_dir):
        dirs.sort()
        for fn in sorted(files):
            if os.path.splitext(fn)[1].lower() not in TEXT_EXTS:
                continue
            ap = os.path.abspath(os.path.join(root, fn))
            if ap == exclude_abs:
                continue
            try:
                with open(ap, "r", encoding="utf-8", errors="replace") as f:
                    chunks.append(f.read())
            except OSError:
                continue
    return "\n".join(chunks)


def number_in_materials(num: str, corpus: str) -> bool:
    pat = re.compile(r"(?<![\d.])" + re.escape(num) + r"(?![\d.])")
    return pat.search(corpus) is not None


def main(argv=None):
    ap = argparse.ArgumentParser(description="套话与静默填平检查")
    ap.add_argument("--md", required=True, help="待检查的章节 md")
    ap.add_argument("--materials", required=True, help="材料目录（数值来源池）")
    ap.add_argument("--gaps", default=None, help="可选 gap_audit 产出的 gaps.json")
    ap.add_argument("--out-dir", required=True, help="输出目录（hedge_report.json / .md）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.md):
        print(f"[hedge_scan] ERROR: 章节文件不存在: {args.md}", file=sys.stderr)
        return 1
    if not os.path.isdir(args.materials):
        print(f"[hedge_scan] ERROR: 材料目录不存在: {args.materials}", file=sys.stderr)
        return 1

    md_abs = os.path.abspath(args.md)
    lines = read_lines(md_abs)

    # ---- 1. 空泛套话 ----
    hedge_hits = []
    in_fence = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for pid, lang, pat, advice in HEDGE_PATTERNS:
            if re.search(pat, line, re.IGNORECASE):
                hedge_hits.append({
                    "line": i, "pattern_id": pid, "lang": lang,
                    "snippet": line.strip()[:120], "advice": advice,
                })

    # ---- 2. 无来源数值（静默填平） ----
    corpus = material_text(args.materials, md_abs)
    unsourced = []
    in_fence = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.lstrip().startswith("#"):        # 标题中的章节编号不查
            continue
        if not TRIGGER.search(line):             # 非参数语境行不查
            continue
        body = LISTNUM_RE.sub("", line)          # 去掉列表编号
        body = CITE_RE.sub("", body)             # 去掉来源定位（file:line）
        for m in NUM_RE.finditer(body):
            num = m.group(1)
            if YEAR_RE.match(num):
                continue
            if not number_in_materials(num, corpus):
                unsourced.append({
                    "line": i, "number": num,
                    "snippet": line.strip()[:120],
                    "note": "该数值在材料中找不到来源，疑似静默填平；"
                            "请提供来源定位（file:line）或改写为“待作者确认”。",
                })

    # ---- 3. 缺口点名核对 ----
    gap_check = {"provided": False, "missing_ids": [], "ok_ids": []}
    if args.gaps:
        if not os.path.isfile(args.gaps):
            print(f"[hedge_scan] WARN: gaps.json 不存在，跳过 G 编号核对: {args.gaps}",
                  file=sys.stderr)
        else:
            with open(args.gaps, "r", encoding="utf-8") as f:
                gaps = json.load(f)
            md_text = "\n".join(lines)
            gap_check["provided"] = True
            for g in gaps.get("gaps", []):
                gid = g.get("id", "")
                if gid and re.search(r"\b" + re.escape(gid) + r"\b", md_text):
                    gap_check["ok_ids"].append(gid)
                elif gid:
                    gap_check["missing_ids"].append(gid)

    failed = bool(hedge_hits or unsourced or gap_check["missing_ids"])
    verdict = "FAIL" if failed else "PASS"

    result = {
        "tool": "hedge_scan",
        "md": md_abs,
        "materials_dir": os.path.abspath(args.materials),
        "verdict": verdict,
        "hedge_hits": hedge_hits,
        "unsourced_numbers": unsourced,
        "gap_coverage": gap_check,
    }

    os.makedirs(args.out_dir, exist_ok=True)
    jpath = os.path.join(args.out_dir, "hedge_report.json")
    mpath = os.path.join(args.out_dir, "hedge_report.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    out = ["# 套话与静默填平检查报告", "", f"- 章节文件: `{md_abs}`",
           f"- 结论: **{verdict}**", ""]
    out.append("## 1. 空泛限制句式")
    if not hedge_hits:
        out.append("未命中。")
    for h in hedge_hits:
        out.append(f"- 行 {h['line']} [{h['pattern_id']}] {h['snippet']}  ")
        out.append(f"  建议：{h['advice']}")
    out.append("")
    out.append("## 2. 无来源数值（静默填平嫌疑）")
    if not unsourced:
        out.append("未发现。")
    for u in unsourced:
        out.append(f"- 行 {u['line']} 数值 `{u['number']}`：{u['snippet']}  ")
        out.append(f"  {u['note']}")
    out.append("")
    out.append("## 3. 缺口点名核对（G 编号）")
    if not gap_check["provided"]:
        out.append("未提供 gaps.json，跳过。")
    else:
        out.append(f"- 已点名: {gap_check['ok_ids'] or '无'}")
        out.append(f"- 未点名: {gap_check['missing_ids'] or '无'}")
    out.append("")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print(f"[hedge_scan] verdict={verdict} 套话 {len(hedge_hits)} 处；"
          f"无来源数值 {len(unsourced)} 处；未点名缺口 {len(gap_check['missing_ids'])} 个 "
          f"-> {jpath}, {mpath}")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
