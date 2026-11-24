#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""query_build.py — 概念块检索式的校验（validate）与双轨渲染（render）。

仅依赖 python3 标准库。退出码约定：
  0  成功
  2  检索式规格违规（输出违规规则编号 R1–R8）
  3  一致性失败（保留给上层管线，本脚本不使用）

spec 模式（JSON 对象）：
  research_question : str                       —— 必填（R6）
  blocks            : [{name, operator, terms}] —— ≥2 块（R1）；operator ∈ {AND, OR}，
                       禁止裸 NOT（R4）；块内词项 [{text, intent}]，
                       intent ∈ {core, variant, classification, exclusion}（R2）
  exclusion_terms   : [{text, reason}]          —— 排除的唯一合法通道，必须附理由（R4）
  classification_codes : [str]                  —— 仅 patent 轨生效（R5）
  date_range        : {start, end}              —— 可选，ISO 日期且 start ≤ end（R7）

渲染约定（R9）：同一 spec 必得同一字符串——块按 spec 顺序连接，块内词项按
(intent 优先级, 文本 casefold) 规范排序并去重；ASCII 词项与 CJK 词项均加双引号。
"""
import argparse
import json
import re
import sys
from datetime import date

INTENTS = ("core", "variant", "classification", "exclusion")
INTENT_RANK = {"core": 0, "variant": 1, "classification": 2, "exclusion": 3}
ISO_DATE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def load_spec(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_iso(value):
    if not isinstance(value, str) or not ISO_DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_spec(spec):
    """返回 [(rule_id, message), ...]；空列表表示全部通过。"""
    errors = []
    if not isinstance(spec, dict):
        return [("R6", "spec 不是 JSON 对象，无法读取 research_question")]

    # R6 research_question 必填
    rq = spec.get("research_question")
    if not isinstance(rq, str) or not rq.strip():
        errors.append(("R6", "research_question 缺失或为空字符串"))

    # R1 至少 2 个概念块
    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        errors.append(("R1", "blocks 缺失或不是数组"))
        blocks = []
    elif len(blocks) < 2:
        errors.append(("R1", "概念块不足 2 个（当前 %d 个）" % len(blocks)))

    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            errors.append(("R3", "blocks[%d] 不是对象" % i))
            continue
        name = block.get("name") or ("blocks[%d]" % i)
        op = str(block.get("operator", "AND")).upper()
        # R4 禁止裸 NOT
        if op == "NOT":
            errors.append(("R4", "块「%s」使用裸 NOT 运算；排除仅允许经顶层 "
                                 "exclusion_terms 并附 reason" % name))
        elif op not in ("AND", "OR"):
            errors.append(("R4", "块「%s」operator 非法：%r（仅允许 AND/OR；"
                                 "排除走 exclusion_terms）" % (name, block.get("operator"))))
        terms = block.get("terms")
        # R3 禁止空块
        if not isinstance(terms, list) or len(terms) == 0:
            errors.append(("R3", "块「%s」为空块（无词项）" % name))
            continue
        has_core_or_variant = False
        for j, term in enumerate(terms):
            if not isinstance(term, dict):
                errors.append(("R2", "块「%s」第 %d 个词项不是对象" % (name, j + 1)))
                continue
            text = term.get("text")
            intent = term.get("intent")
            if not isinstance(text, str) or not text.strip():
                errors.append(("R3", "块「%s」含空文本词项" % name))
            # R2 每个词项必须带合法 intent
            if intent not in INTENTS:
                errors.append(("R2", "块「%s」词项 %r 的 intent 缺失或非法"
                                     "（须为 core/variant/classification/exclusion）"
                                     % (name, text)))
            elif intent == "exclusion":
                errors.append(("R4", "块「%s」内嵌 exclusion 词项 %r；排除词项必须移入"
                                     "顶层 exclusion_terms 并附 reason" % (name, text)))
            if intent in ("core", "variant") and isinstance(text, str) and text.strip():
                has_core_or_variant = True
        # R8 每块至少 1 个 core/variant 词项
        if not has_core_or_variant:
            errors.append(("R8", "块「%s」缺少 core 或 variant 词项"
                                 "（分类块也须保留至少一个描述性词项）" % name))

    # R4 exclusion_terms 必须逐条附理由
    excl = spec.get("exclusion_terms") or []
    if not isinstance(excl, list):
        errors.append(("R4", "exclusion_terms 必须是数组"))
        excl = []
    for k, e in enumerate(excl):
        if not isinstance(e, dict) or not isinstance(e.get("text"), str) \
                or not e.get("text", "").strip():
            errors.append(("R4", "exclusion_terms[%d] 缺少非空 text" % k))
        elif not isinstance(e.get("reason"), str) or not e.get("reason").strip():
            errors.append(("R4", "exclusion_terms[%d]（%r）缺少排除理由 reason"
                                 % (k, e.get("text"))))

    # R5 classification_codes 形态校验（生效范围在 render 阶段按轨处理）
    codes = spec.get("classification_codes") or []
    if not isinstance(codes, list) or any(
            not isinstance(c, str) or not c.strip() for c in codes):
        errors.append(("R5", "classification_codes 必须是非空字符串数组"
                             "（仅在 patent 轨生效）"))

    # R7 date_range 合法性与合理性
    dr = spec.get("date_range")
    if dr is not None:
        if not isinstance(dr, dict):
            errors.append(("R7", "date_range 必须是 {start, end} 对象"))
        else:
            s = _parse_iso(dr.get("start"))
            e = _parse_iso(dr.get("end"))
            if s is None or e is None:
                errors.append(("R7", "date_range.start/end 必须是合法 ISO 日期"
                                     " YYYY-MM-DD（当前：%r / %r）"
                                     % (dr.get("start"), dr.get("end"))))
            elif s > e:
                errors.append(("R7", "date_range.start (%s) 晚于 end (%s)"
                                     % (dr["start"], dr["end"])))
    return errors


def canonical_terms(block):
    """R9 规范化：块内词项按 (intent 优先级, 文本 casefold) 排序并去重。"""
    seen = set()
    out = []
    for t in block.get("terms", []):
        if not isinstance(t, dict):
            continue
        text = (t.get("text") or "").strip()
        intent = t.get("intent")
        if not text or intent not in INTENTS or intent == "exclusion":
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "intent": intent})
    out.sort(key=lambda t: (INTENT_RANK[t["intent"]], t["text"].casefold()))
    return out


def render(spec, track):
    """渲染为可解释的布尔串。返回 (文本, notes)；notes 记录轨道差异说明。"""
    notes = []
    lines = [
        "# dual-track-retrieval-lab 渲染输出（确定性：同一 spec 必得同一串）",
        "# research_question: " + spec["research_question"].strip(),
        "# track: " + track,
    ]
    clauses = []
    for block in spec["blocks"]:
        terms = canonical_terms(block)
        expr = " OR ".join('"%s"' % t["text"] for t in terms)
        clauses.append("( %s )" % expr)
    expr = clauses[0]
    for block, clause in zip(spec["blocks"][1:], clauses[1:]):
        op = str(block.get("operator", "AND")).upper()
        expr = expr + " " + op + " " + clause
    # R5 classification_codes 仅 patent 轨生效
    codes = sorted({c.strip() for c in (spec.get("classification_codes") or [])
                    if isinstance(c, str) and c.strip()})
    if codes:
        if track == "patent":
            expr += " AND CLASS IN ( " + ", ".join('"%s"' % c for c in codes) + " )"
        else:
            notes.append("classification_codes 在 npl 轨不生效，渲染时已丢弃: "
                         + ", ".join(codes))
    dr = spec.get("date_range")
    if dr:
        expr += " AND DATE IN [ %s .. %s ]" % (dr["start"], dr["end"])
    excl = spec.get("exclusion_terms") or []
    if excl:
        expr += " NOT ( " + " OR ".join('"%s"' % e["text"] for e in excl) + " )"
        lines.append("# exclusion reasons: " + "; ".join(
            "%s ← %s" % (e["text"], e.get("reason", "")) for e in excl))
    for n in notes:
        lines.append("# NOTE: " + n)
    lines.append(expr)
    return "\n".join(lines) + "\n", notes


def main(argv=None):
    ap = argparse.ArgumentParser(description="概念块检索式构造：validate / render")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("validate", help="校验 spec，违规时退出码 2 并打印规则编号")
    pv.add_argument("--spec", required=True)
    pr = sub.add_parser("render", help="按轨渲染布尔检索式")
    pr.add_argument("--spec", required=True)
    pr.add_argument("--track", choices=["patent", "npl"], required=True)
    pr.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except (OSError, json.JSONDecodeError) as exc:
        print("FAIL R6: 无法读取 spec：%s" % exc, file=sys.stderr)
        return 2
    errors = validate_spec(spec)

    if args.cmd == "validate":
        if errors:
            for rid, msg in errors:
                print("FAIL %s: %s" % (rid, msg))
            print("validate: %d 条违规" % len(errors))
            return 2
        print("validate: OK（R1–R9 前置规则全部通过；R9 由 render 的确定性保证）")
        return 0

    # render 前先校验，违规即拒绝渲染
    if errors:
        for rid, msg in errors:
            print("FAIL %s: %s" % (rid, msg), file=sys.stderr)
        print("render 中止：spec 未通过校验", file=sys.stderr)
        return 2
    text, notes = render(spec, args.track)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    for n in notes:
        print("NOTE: " + n, file=sys.stderr)
    print("render: 已写出 %s（track=%s，%d 字符）" % (args.out, args.track, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
