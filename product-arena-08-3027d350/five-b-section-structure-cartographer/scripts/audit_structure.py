#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_structure.py — 结构一致性审计 + 契约感知 result.json。

审计项：
  1. 编号：跳号 / 重复 / 逆序（同级兄弟序列）
  2. 层级断裂：如 1 → 1.1.1 缺 1.1（编号前缀缺失）
  3. 图表双向核对：正文引用 "Figure N"/"Table N" 集合 vs 题注
     "Figure N:"/"Fig. N"/"Table N:" 行集合；双向列出差异
     （引用了不存在的、存在但未被引用）
  4. 树字符覆盖率：落在任一结构区间内的字符 / 全文非空字符
  5. 参考文献切分对账复核（char_accounting.balanced）

另写 result.json：读取 case.json 的 output_contract 字段名逐个填充；
无法填充的字段置空（null）并在 uncertainty 说明，status 标 partial；
含 status / sources / uncertainty / change_record / case_id。

退出码：0=success；2=partial（降级模式/契约字段空缺/无 case.json）；3=失败。
"""
import argparse
import json
import os
import re
import sys
import time

CAPTION_RE = re.compile(r"^\s*(fig(?:ure)?s?|tables?)\.?\s*(\d+)\s*[:.]", re.I)
CITE_RE = re.compile(r"\b(fig(?:ure)?s?|tables?)\.?\s+(\d+)\b", re.I)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_lines(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for row in f:
            row = row.strip()
            if row:
                out.append(json.loads(row))
    return out


def flatten(tree):
    """按文档顺序展开树节点（先序）。"""
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(n)
            walk(n.get("children", []))

    walk(tree)
    return out


def audit_numbering(nodes):
    """nodes：先序展开节点。返回 {gaps, duplicates, inversions, level_breaks}。"""
    numbered = [n for n in nodes if n.get("number")]
    nums = [n["number"] for n in numbered]
    issues = {"gaps": [], "duplicates": [], "inversions": [], "level_breaks": []}

    seen = set()
    for n in nums:
        if n in seen:
            issues["duplicates"].append(n)
        seen.add(n)

    # 同级兄弟序列检查（按文档顺序）
    by_parent = {}

    def key(num):
        return tuple(int(x) for x in num.split("."))

    siblings = {}
    for n in nums:
        parent = ".".join(n.split(".")[:-1])
        siblings.setdefault(parent, []).append(int(n.split(".")[-1]))
    for parent, seq in siblings.items():
        if seq != sorted(seq):
            issues["inversions"].append({"parent": parent or "<root>", "sequence": seq})
        for a, b in zip(seq, seq[1:]):
            if b > a + 1:
                issues["gaps"].append(
                    {"parent": parent or "<root>", "from": a, "to": b,
                     "missing": list(range(a + 1, b))}
                )

    # 层级断裂：编号前缀缺失（如存在 1.1.1 但无 1.1）
    numset = set(nums)
    for n in nums:
        parts = n.split(".")
        for d in range(1, len(parts)):
            prefix = ".".join(parts[:d])
            if prefix not in numset:
                issues["level_breaks"].append({"number": n, "missing_prefix": prefix})
    return issues


def audit_figures_tables(lines, spans):
    """题注集合 vs 引用集合，双向差异。"""
    body = spans.get("body")
    if body:
        seg = [l for l in lines
               if body["start_line_idx"] <= l["line_idx"] <= body["end_line_idx"]]
    else:
        seg = lines  # 无 body 区间时全文扫描（降级，报告注明）
    captions = {"figure": set(), "table": set()}
    cites = {"figure": set(), "table": set()}
    caption_lines = []
    for l in seg:
        text = l["text"]
        m = CAPTION_RE.match(text)
        rest = text
        if m:
            kind = "figure" if m.group(1).lower().startswith(("fig",)) else "table"
            captions[kind].add(int(m.group(2)))
            caption_lines.append(
                {"page": l["page"], "y0": l["y0"], "kind": kind,
                 "n": int(m.group(2)), "text": text.strip()[:120]}
            )
            rest = text[m.end():]  # 题注自身的编号不算引用
        for c in CITE_RE.finditer(rest):
            kind = "figure" if c.group(1).lower().startswith("fig") else "table"
            cites[kind].add(int(c.group(2)))
    result = {}
    for kind in ("figure", "table"):
        result[kind] = {
            "cited": sorted(cites[kind]),
            "captioned": sorted(captions[kind]),
            "cited_not_captioned": sorted(cites[kind] - captions[kind]),
            "captioned_not_cited": sorted(captions[kind] - cites[kind]),
        }
    return result, caption_lines


def audit_coverage(lines, spans):
    total = sum(len(l["text"]) for l in lines)
    if total == 0:
        return {"total_chars": 0, "covered_chars": 0, "coverage": None}
    intervals = [
        (v["start_line_idx"], v["end_line_idx"])
        for v in spans.values()
        if isinstance(v, dict) and "start_line_idx" in v
    ]
    covered = 0
    for l in lines:
        i = l["line_idx"]
        if any(a <= i <= b for a, b in intervals):
            covered += len(l["text"])
    return {
        "total_chars": total,
        "covered_chars": covered,
        "coverage": round(covered / total, 4),
        "note": "front_matter/body/references/appendix 等区间并集对全文字符的覆盖率。",
    }


# ------------------------------------------------------------ result.json
DEFAULT_FIELDS = ["document_tree", "section_spans", "references",
                  "reference_count", "structure_audit", "engine"]


def build_result(case, tree_doc, spans_doc, refs_doc, audit, engine_info, srcs):
    contract = None
    if case:
        oc = case.get("output_contract")
        if isinstance(oc, dict):
            contract = oc.get("fields") or oc.get("required_fields")
        elif isinstance(oc, list):
            contract = oc
    contract = contract or DEFAULT_FIELDS

    issues_summary = {
        "issue_count": audit["issue_count"],
        "figures": audit["figures_tables"]["figure"],
        "tables": audit["figures_tables"]["table"],
        "numbering": audit["numbering"],
        "coverage": audit["coverage"],
    }
    field_values = {
        "document_tree": tree_doc.get("tree"),
        "section_spans": spans_doc.get("spans"),
        "references": refs_doc.get("entries") if refs_doc else None,
        "reference_count": (refs_doc or {}).get("entry_count"),
        "structure_audit": issues_summary,
        "engine": engine_info,
        "title": tree_doc.get("title"),
        "authors": tree_doc.get("authors"),
    }

    uncertainty = list(audit.get("uncertainty", []))
    filled, null_fields = {}, []
    for name in contract:
        v = field_values.get(name)
        if v is None:
            null_fields.append(name)
        filled[name] = v
    if not case:
        uncertainty.append("未提供 case.json：output_contract 未知，按默认字段集合填充。")
    if null_fields:
        uncertainty.append(f"以下契约字段无法填充，已置空: {null_fields}")
    if engine_info.get("mode") != "styled":
        uncertainty.append(
            f"抽取模式 mode={engine_info.get('mode')}：字号/粗体不可用，"
            "层级主要依据编号与关键词，置信度下降。"
        )

    status = "success"
    if null_fields or not case or engine_info.get("mode") != "styled":
        status = "partial"

    return {
        "case_id": (case or {}).get("case_id"),
        "status": status,
        "output_contract_fields": contract,
        **filled,
        "sources": srcs,
        "uncertainty": uncertainty,
        "change_record": [
            {"step": "extract_styled_lines", "engine": engine_info.get("engine"),
             "mode": engine_info.get("mode")},
            {"step": "build_hierarchy",
             "heading_count": tree_doc.get("heading_count")},
            {"step": "split_references",
             "entry_count": (refs_doc or {}).get("entry_count")},
            {"step": "audit_structure", "issue_count": audit["issue_count"],
             "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        ],
    }, status


def main(argv=None):
    ap = argparse.ArgumentParser(description="结构一致性审计 + result.json")
    ap.add_argument("--lines", required=True)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--spans", required=True)
    ap.add_argument("--references", required=True)
    ap.add_argument("--case", default=None, help="case.json（可选）")
    ap.add_argument("--audit", required=True, help="输出 audit_report.json")
    ap.add_argument("--result", required=True, help="输出契约感知 result.json")
    ap.add_argument("--source-pdf", default=None)
    args = ap.parse_args(argv)

    for p in (args.lines, args.tree, args.spans, args.references):
        if not os.path.isfile(p):
            print(f"[audit] 输入不存在: {p}", file=sys.stderr)
            return 3

    lines = load_lines(args.lines)
    tree_doc = load_json(args.tree)
    spans_doc = load_json(args.spans)
    refs_doc = load_json(args.references)
    case = None
    if args.case and os.path.isfile(args.case):
        case = load_json(args.case)

    spans = spans_doc.get("spans", {})
    nodes = flatten(tree_doc.get("tree", []))

    numbering = audit_numbering(nodes)
    figtab, caption_lines = audit_figures_tables(lines, spans)
    coverage = audit_coverage(lines, spans)

    uncertainty = []
    if not spans.get("body"):
        uncertainty.append("body 区间缺失：图表核对退化为全文扫描。")

    issue_count = (
        len(numbering["gaps"]) + len(numbering["duplicates"])
        + len(numbering["inversions"]) + len(numbering["level_breaks"])
        + len(figtab["figure"]["cited_not_captioned"])
        + len(figtab["figure"]["captioned_not_cited"])
        + len(figtab["table"]["cited_not_captioned"])
        + len(figtab["table"]["captioned_not_cited"])
    )

    audit_doc = {
        "checks": {
            "numbering": numbering,
            "figures_tables": figtab,
            "caption_lines": caption_lines,
            "coverage": coverage,
            "references_char_accounting": refs_doc.get("char_accounting"),
        },
        "issue_count": issue_count,
        "uncertainty": uncertainty,
        "note": "issue 为审计发现（如引用无题注），不等同于流水线失败。",
    }
    with open(args.audit, "w", encoding="utf-8") as f:
        json.dump(audit_doc, f, ensure_ascii=False, indent=2)

    engine_info = {
        "engine": lines[0].get("engine") if lines else None,
        "mode": lines[0].get("mode") if lines else None,
    }
    srcs = [os.path.abspath(p) for p in (args.lines, args.tree, args.spans,
                                         args.references)]
    if args.source_pdf:
        srcs.insert(0, os.path.abspath(args.source_pdf))
    if args.case:
        srcs.append(os.path.abspath(args.case))

    audit_for_result = {
        "issue_count": issue_count,
        "numbering": numbering,
        "figures_tables": figtab,
        "coverage": coverage,
        "uncertainty": uncertainty,
    }
    result, status = build_result(case, tree_doc, spans_doc, refs_doc,
                                  audit_for_result, engine_info, srcs)
    with open(args.result, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[audit] issues={issue_count} coverage={coverage['coverage']} "
          f"fig_cited_not_captioned={figtab['figure']['cited_not_captioned']} "
          f"status={status}")
    return 0 if status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
