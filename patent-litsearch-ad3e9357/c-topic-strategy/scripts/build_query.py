#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_query.py — 概念块检索式构造器（可导入库 + CLI）

把技术主题拆成 2-5 个概念块：块内词项为 OR、块间为 AND；
每个词项必须带 intent（该词为何能识别相关文献）；
支持分面：classification（IPC/CPC）、applicant、year_range。

CLI 子命令：
  build    : 校验 spec 并输出结构化检索式 JSON + 人读布尔表达式
  validate : 仅校验 spec，打印 R1-R9 违规项
  draft    : 从 case.json / task.md / 主题文本生成待补 intent 的草稿 spec

退出码：0 成功；2 结构校验违规（R1-R9）；1 其他错误。
仅依赖标准库。
"""
import argparse
import json
import re
import sys

SPEC_KEYS = {"topic", "version", "mode", "blocks", "facets", "notes"}
BLOCK_KEYS = {"name", "terms"}
TERM_KEYS = {"term", "intent"}
FACET_KEYS = {"classification", "applicant", "year_range"}

# IPC/CPC 截面一级格式，如 A01N 63/00、C12M1/12
CLASS_RE = re.compile(r"^[A-HYa-hy]\d{2}[A-Za-z]\s*\d{1,4}(/\d{1,6})?$")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _err(errors, rule, msg):
    errors.append({"rule": rule, "message": msg})


def _is_not_term(ts):
    up = ts.upper()
    return up == "NOT" or up.startswith("NOT ")


def validate_spec(spec):
    """结构校验 R1-R9，返回违规列表（空列表 = 通过）。

    R1 空块 / 缺块名；R2 块内空 OR；R3 未声明字段；R4 裸 NOT；
    R5 引号不成对；R6 词项缺 intent；R7 分面值格式非法；
    R8 主题模式块数越界（须 2-5）；R9 号码模式必须恰好 1 块。
    """
    errors = []
    if not isinstance(spec, dict):
        return [{"rule": "R3", "message": "spec 必须是 JSON 对象"}]
    for k in sorted(set(spec) - SPEC_KEYS):
        _err(errors, "R3", "未声明的顶层字段: %s" % k)

    mode = spec.get("mode", "topic")
    if mode not in ("topic", "number_lookup"):
        _err(errors, "R3", "mode 只能是 topic 或 number_lookup，实际: %r" % (mode,))
        mode = "topic"

    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        _err(errors, "R1", "blocks 缺失或不是数组")
        blocks = []
    if mode == "topic" and not (2 <= len(blocks) <= 5):
        _err(errors, "R8", "主题模式需要 2-5 个概念块，实际 %d" % len(blocks))
    if mode == "number_lookup" and len(blocks) != 1:
        _err(errors, "R9", "号码模式必须恰好 1 个概念块（号码词项精确匹配），实际 %d" % len(blocks))

    for bi, block in enumerate(blocks):
        if not isinstance(block, dict):
            _err(errors, "R1", "block[%d]: 块必须是对象" % bi)
            continue
        name = block.get("name")
        label = str(name) if name else ("block[%d]" % bi)
        for k in sorted(set(block) - BLOCK_KEYS):
            _err(errors, "R3", "%s: 未声明的块字段: %s" % (label, k))
        if not name or not str(name).strip():
            _err(errors, "R1", "block[%d]: 缺少块名 name" % bi)
        terms = block.get("terms")
        if not isinstance(terms, list) or len(terms) == 0:
            _err(errors, "R1", "%s: 空块（terms 缺失或为空）" % label)
            continue
        positive_seen = False
        not_count = 0
        dict_terms = 0
        for ti, t in enumerate(terms):
            tlabel = "%s.terms[%d]" % (label, ti)
            if not isinstance(t, dict):
                _err(errors, "R2", "%s: 词项必须是对象 {term, intent}" % tlabel)
                continue
            dict_terms += 1
            for k in sorted(set(t) - TERM_KEYS):
                _err(errors, "R3", "%s: 未声明的词项字段: %s" % (tlabel, k))
            term = t.get("term")
            if not isinstance(term, str) or not term.strip():
                _err(errors, "R2", "%s: 块内空 OR（term 为空）" % tlabel)
                continue
            ts = term.strip()
            if ts.count('"') % 2 != 0 or ts.count("“") != ts.count("”"):
                _err(errors, "R5", "%s: 引号不成对: %r" % (tlabel, ts))
            if _is_not_term(ts):
                not_count += 1
                if not positive_seen:
                    _err(errors, "R4", "%s: 裸 NOT（同块内 NOT 之前必须有正向词项）: %r" % (tlabel, ts))
            else:
                positive_seen = True
            intent = t.get("intent")
            if not isinstance(intent, str) or not intent.strip():
                _err(errors, "R6", "%s: 词项缺 intent（该词为何能识别相关文献）: %r" % (tlabel, ts))
        if dict_terms and not_count == dict_terms:
            _err(errors, "R4", "%s: 块内全部词项均为 NOT，属于裸 NOT" % label)

    facets = spec.get("facets")
    if facets is not None:
        if not isinstance(facets, dict):
            _err(errors, "R3", "facets 必须是对象")
        else:
            for k in sorted(set(facets) - FACET_KEYS):
                _err(errors, "R3", "facets: 未声明的分面字段: %s" % k)
            cls = facets.get("classification")
            if cls is not None:
                if not isinstance(cls, list) or not cls or not all(isinstance(x, str) and x.strip() for x in cls):
                    _err(errors, "R7", "classification 分面必须是非空字符串数组")
                else:
                    for x in cls:
                        if not CLASS_RE.match(x.strip()):
                            _err(errors, "R7", "classification 分面值格式非法（应如 A01N 63/00 或 C12M1/00）: %r" % x)
            app = facets.get("applicant")
            if app is not None:
                if not isinstance(app, list) or not app or not all(isinstance(x, str) and x.strip() for x in app):
                    _err(errors, "R7", "applicant 分面必须是非空字符串数组")
            yr = facets.get("year_range")
            if yr is not None:
                ok = (isinstance(yr, list) and len(yr) == 2
                      and all(isinstance(x, (int, str)) and YEAR_RE.match(str(x)) for x in yr))
                if not ok:
                    _err(errors, "R7", "year_range 分面必须是 [起始年, 截止年]，实际: %r" % (yr,))
                elif int(str(yr[0])) > int(str(yr[1])):
                    _err(errors, "R7", "year_range 起始年大于截止年: %r" % (yr,))
    return errors


def build_query(spec):
    """校验并生成结构化检索式。返回 (query, errors)。"""
    errors = validate_spec(spec)
    if errors:
        return None, errors
    mode = spec.get("mode", "topic")
    blocks_expr = []
    for block in spec["blocks"]:
        positives = []
        negatives = []
        for t in block["terms"]:
            ts = t["term"].strip()
            if _is_not_term(ts) and ts.upper().startswith("NOT "):
                negatives.append(ts[4:].strip())
            elif not _is_not_term(ts):
                positives.append(ts)
        expr = "(" + " OR ".join(positives) + ")"
        if negatives:
            expr += " AND NOT (" + " OR ".join(negatives) + ")"
        blocks_expr.append(expr)
    boolean = " AND ".join(blocks_expr)
    facets = spec.get("facets") or {}
    facet_exprs = []
    if facets.get("classification"):
        facet_exprs.append("IPC/CPC=(" + " OR ".join(x.strip() for x in facets["classification"]) + ")")
    if facets.get("applicant"):
        facet_exprs.append("申请人=(" + " OR ".join(x.strip() for x in facets["applicant"]) + ")")
    if facets.get("year_range"):
        facet_exprs.append("年份=%s-%s" % (facets["year_range"][0], facets["year_range"][1]))
    boolean_full = boolean + ("  [分面] " + " AND ".join(facet_exprs) if facet_exprs else "")
    query = {
        "topic": spec.get("topic", ""),
        "version": spec.get("version", "1.0"),
        "mode": mode,
        "blocks": spec["blocks"],
        "facets": facets,
        "boolean": boolean_full,
    }
    return query, []


def _extract_theme_text(case_path=None, task_path=None, theme=None):
    parts = []
    if theme:
        parts.append(theme)
    if case_path:
        try:
            with open(case_path, encoding="utf-8") as f:
                case = json.load(f)
            for key in ("task", "title", "description", "theme", "case_summary", "question"):
                v = case.get(key)
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())
        except (OSError, json.JSONDecodeError):
            pass
    if task_path:
        try:
            with open(task_path, encoding="utf-8") as f:
                txt = f.read()
            txt = re.sub(r"[#*>`\-]{1,3}\s*", " ", txt)
            parts.append(txt.strip())
        except OSError:
            pass
    return "\n".join(p for p in parts if p)


def draft_spec(theme_text):
    """从主题文本生成草稿 spec（intent 留空，须人工/Agent 补齐后再 build）。"""
    segs = [s.strip() for s in re.split(r"[。；;，,\n：:]|(?:\b(?:and|or|with|for|using)\b)", theme_text) if len(s.strip()) >= 2]
    segs = segs[:5] if segs else [theme_text.strip() or "主题"]
    if len(segs) < 2:
        segs = segs + ["同义词/上位词待补充"]
    blocks = []
    for i, seg in enumerate(segs[:5]):
        toks = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}|[一-鿿]{2,6}", seg)
        seen = []
        for tk in toks:
            if tk.lower() not in {x.lower() for x in seen}:
                seen.append(tk)
        blocks.append({
            "name": "概念块%d" % (i + 1),
            "terms": [{"term": tk, "intent": ""} for tk in seen[:4]] or [{"term": seg[:20], "intent": ""}],
        })
    return {
        "topic": theme_text.strip()[:200],
        "version": "0.1-draft",
        "mode": "topic",
        "blocks": blocks,
        "facets": {},
        "notes": "DRAFT：intent 全部为空，不会通过 R6 校验。请逐词补写 intent（该词为何能识别相关文献），"
                 "并按 rules/topic_query_construction.md 调整块划分与同义词后再运行 build。",
    }


def _print_errors(errors):
    for e in errors:
        sys.stderr.write("[%s] %s\n" % (e["rule"], e["message"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="概念块检索式构造器（可导入库 + CLI）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="校验 spec 并输出检索式 JSON")
    b.add_argument("--spec", required=True, help="检索式 spec JSON 路径")
    b.add_argument("--out", help="结构化检索式 JSON 输出路径（缺省打印到 stdout）")
    b.add_argument("--expr-out", help="人读布尔表达式输出路径（UTF-8 文本）")

    v = sub.add_parser("validate", help="仅校验 spec")
    v.add_argument("--spec", required=True)

    d = sub.add_parser("draft", help="从主题描述生成草稿 spec（intent 待补）")
    d.add_argument("--case", help="/input/case.json 路径")
    d.add_argument("--task", help="/input/task.md 路径")
    d.add_argument("--theme", help="直接给出主题文本")
    d.add_argument("--out", required=True, help="草稿 spec 输出路径")

    args = ap.parse_args(argv)

    if args.cmd in ("build", "validate"):
        try:
            with open(args.spec, encoding="utf-8") as f:
                spec = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write("无法读取 spec: %s\n" % e)
            return 1
        if args.cmd == "validate":
            errors = validate_spec(spec)
            if errors:
                _print_errors(errors)
                return 2
            print("spec 校验通过（R1-R9）")
            return 0
        query, errors = build_query(spec)
        if errors:
            _print_errors(errors)
            return 2
        text = json.dumps(query, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            sys.stderr.write("检索式已写入 %s\n" % args.out)
        else:
            print(text)
        if args.expr_out:
            with open(args.expr_out, "w", encoding="utf-8") as f:
                f.write(query["boolean"] + "\n")
        return 0

    # draft
    theme_text = _extract_theme_text(args.case, args.task, args.theme)
    if not theme_text:
        sys.stderr.write("draft: 未获得主题文本（--case/--task/--theme 至少其一）\n")
        return 1
    spec = draft_spec(theme_text)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    sys.stderr.write("草稿 spec 已写入 %s；注意：intent 为空，补齐后才能通过 build 校验。\n" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
