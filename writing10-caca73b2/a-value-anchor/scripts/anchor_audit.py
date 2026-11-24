#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anchor_audit.py — 正文数字锚定审计器（value-anchor-rd）

用法：
  python3 anchor_audit.py --manuscript 文稿.md --ledger values.json \
      [--tol 0.02] [--report audit_report.md]

规则（确定性，无模型调用）：
  1. 逐句抽取文稿中的全部数字（可带单位）。图/表编号（图1、表2、Fig. 3）
     与锚点标记 [Vnn] 自身不计入。
  2. 每个数字所在句必须含至少一个 [Vnn] 锚点，否则 FAIL（无来源数字）。
  3. 锚点 id 必须存在于台账，否则 FAIL（悬空锚点）。
  4. 句内每个数字必须与该句某一锚点的台账值吻合：
       |reported - ledger| / |ledger| <= tol（ledger=0 时要求精确相等）；
     台账 stat ∈ {p, n} 的条目要求精确相等（tol 强制为 0）；
     台账值为 [a, b] 区间（95% CI）时，命中任一端点即视为吻合。
  5. 句内锚点的台账值若与句内任何数字都不吻合，记 WARN（计数不阻断）。
  6. 台账中从未被引用的条目以 INFO 列出（提示可能遗漏的关键数据）。

零 FAIL 时打印 PASS，退出码 0；否则打印 FAIL 与行号明细，退出码 1。
"""

import argparse
import json
import re
import sys

ANCHOR_RE = re.compile(r"\[V(\d{2,})\]")
REF_RE = re.compile(
    r"(?:图|表|Fig\.?|Figure|Table|Suppl\.?|附录)\s*[SＳ]?\d+(?:[-–]\d+)?",
    re.I)
NUM_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*(%|mmol/L|µmol/L|μmol/L|"
                    r"mol/L|mg/mL|µg/mL|μg/mL|ng/mL|g/L|mg/L|mM|µM|μM|nM|"
                    r"mg/kg|mmHg|cm|mm|kg|mg|mL|µL|μL|min|Hz|h|s|g)?")
EXACT_STATS = {"p", "n"}  # 这些统计量要求精确相等
SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])|\n+")


def split_sentences(text):
    """按句切分并保留原始行号：返回 [(line_no, sentence)]。"""
    out = []
    for ln, line in enumerate(text.splitlines(), start=1):
        for seg in SENT_SPLIT.split(line):
            seg = (seg or "").strip()
            if seg:
                out.append((ln, seg))
    return out


CI_TOKEN_RE = re.compile(r"95\s*%\s*(?:CI|置信区间)", re.I)
ID_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")
DF_RE = re.compile(r"\b([tTF])\s*\(\s*\d+(?:\s*[,，]\s*\d+)*\s*\)")


def extract_numbers(sentence):
    """返回 [(value_float, unit, raw_text)]；锚点、图表编号、95%CI 标记与
    t/F 自由度等结构性数字已屏蔽，不计入需锚定的数字。"""
    masked = ANCHOR_RE.sub(" ", sentence)
    masked = REF_RE.sub(" ", masked)
    masked = CI_TOKEN_RE.sub(" ", masked)
    masked = DF_RE.sub(r"\1()", masked)
    masked = ID_RE.sub(" ", masked)  # 含数字的编号 token（如 SYNTH-EXAMPLE-001）
    res = []
    for m in NUM_RE.finditer(masked):
        res.append((float(m.group(1)), m.group(2) or "", m.group(0).strip()))
    return res


def entry_values(entry):
    v = entry.get("value")
    if isinstance(v, list):
        return [float(x) for x in v]
    try:
        return [float(v)]
    except (TypeError, ValueError):
        return []


def matches(reported, ledger_value, entry, tol):
    tol_eff = 0.0 if entry.get("stat") in EXACT_STATS else tol
    if ledger_value == 0:
        return reported == 0
    return abs(reported - ledger_value) / abs(ledger_value) <= tol_eff


def audit(manuscript_text, ledger, tol):
    entries = {e["id"]: e for e in ledger.get("entries", [])}
    fails, warns, infos = [], [], []
    cited = set()
    n_numbers = 0
    n_anchors = 0

    for ln, sent in split_sentences(manuscript_text):
        anchors = ANCHOR_RE.findall(sent)
        numbers = extract_numbers(sent)
        n_numbers += len(numbers)
        n_anchors += len(anchors)

        anchor_ids = ["V%s" % a for a in anchors]
        for aid in anchor_ids:
            if aid not in entries:
                fails.append("L%d: 悬空锚点 [%s] 在台账中不存在（句: %s）"
                             % (ln, aid, sent[:60]))
        valid = [entries[a] for a in anchor_ids if a in entries]
        cited.update(a for a in anchor_ids if a in entries)

        if numbers and not anchors:
            for val, unit, raw in numbers:
                fails.append("L%d: 数字 %s 无锚点来源（句: %s）"
                             % (ln, raw, sent[:60]))
            continue

        for val, unit, raw in numbers:
            ok = False
            for e in valid:
                for lv in entry_values(e):
                    if matches(val, lv, e, tol):
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                fails.append(
                    "L%d: 数字 %s 与句内锚点 %s 的台账值均不吻合（tol=%.4g；"
                    "p/n 要求精确相等）（句: %s）"
                    % (ln, raw, ",".join(anchor_ids) or "无", tol, sent[:60]))

        # WARN：锚点存在但其台账值未出现在句中
        for e in valid:
            if not numbers:
                continue
            if not any(matches(v, lv, e, tol)
                       for lv in entry_values(e) for v, _, _ in numbers):
                warns.append("L%d: 锚点 [%s]（台账值 %s）与句内数字不对应（句: %s）"
                             % (ln, e["id"], e.get("value"), sent[:60]))

    uncited = [e["id"] for e in ledger.get("entries", [])
               if e["id"] not in cited]
    if uncited:
        infos.append("台账条目未被正文引用（可能遗漏关键数据）: %s"
                     % ", ".join(uncited))
    return {
        "counts": {"numbers": n_numbers, "anchors": n_anchors,
                   "fail": len(fails), "warn": len(warns),
                   "info": len(infos)},
        "fails": fails, "warns": warns, "infos": infos,
    }


def render_markdown(result, manuscript_path, ledger_path, tol):
    c = result["counts"]
    verdict = "PASS" if c["fail"] == 0 else "FAIL"
    out = ["# 锚定审计报告（audit_report.md）", "",
           "- 文稿: `%s`" % manuscript_path,
           "- 台账: `%s`" % ledger_path,
           "- 容差 tol=%.4g（p 值与 n 强制精确相等）" % tol,
           "- 数字总数: %(numbers)d；锚点总数: %(anchors)d" % c,
           "- FAIL: %(fail)d；WARN: %(warn)d；INFO: %(info)d" % c, "",
           "## 结论: %s" % verdict, ""]
    if result["fails"]:
        out += ["## FAIL 明细", ""]
        out += ["- %s" % f for f in result["fails"]] + [""]
    if result["warns"]:
        out += ["## WARN 明细", ""]
        out += ["- %s" % w for w in result["warns"]] + [""]
    if result["infos"]:
        out += ["## INFO", ""]
        out += ["- %s" % i for i in result["infos"]] + [""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="anchor_audit.py",
        description="校验文稿中每个数字均带 [Vnn] 锚点且与台账值吻合")
    ap.add_argument("--manuscript", required=True, help="待审 Markdown 文稿")
    ap.add_argument("--ledger", required=True, help="ingest_values.py 生成的 values.json")
    ap.add_argument("--tol", type=float, default=0.02,
                    help="相对容差（默认 0.02；p/n 自动改为精确匹配）")
    ap.add_argument("--report", default=None, help="输出 Markdown 审计报告路径")
    args = ap.parse_args(argv)

    try:
        with open(args.manuscript, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print("FAIL: 无法读取文稿: %s" % e)
        return 1
    try:
        with open(args.ledger, "r", encoding="utf-8") as f:
            ledger = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        print("FAIL: 无法读取台账: %s" % e)
        return 1

    result = audit(text, ledger, args.tol)
    report_md = render_markdown(result, args.manuscript, args.ledger, args.tol)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report_md)

    c = result["counts"]
    print("AUDIT: numbers=%(numbers)d anchors=%(anchors)d "
          "fail=%(fail)d warn=%(warn)d" % c)
    for line in result["fails"]:
        print("FAIL  %s" % line)
    for line in result["warns"]:
        print("WARN  %s" % line)
    for line in result["infos"]:
        print("INFO  %s" % line)
    if c["fail"] == 0:
        print("PASS: 全部数字均已锚定且在容差内与台账一致")
        return 0
    print("FAIL: 存在 %d 处锚定违规，必须修复后重审，不得绕过" % c["fail"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
