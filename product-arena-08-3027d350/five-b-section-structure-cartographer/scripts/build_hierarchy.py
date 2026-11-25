#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_hierarchy.py — 标题检测与层级定级，切分 front_matter/body/references/appendix。

输入：extract_styled_lines.py 的 lines.jsonl。
信号（阈值见 references/heading-patterns.md，代码与文档保持一致）：
  - 编号模式  ^\\d+(\\.\\d+){0,3}[.)]?\\s+  → 深度定级（编号深度优先）
  - 字号显著高于正文中位数（>= 1.15x）且粗体或短行
  - 全大写短行
  - 关键词 Abstract/摘要/Introduction/References/Bibliography/Acknowledg/Appendix
定级：编号深度优先；无编号标题按字号秩映射层级；无法定级 → heading_candidates + 降级说明。

输出：
  document_tree.json — 嵌套 children；节点含 number/title/page/y0/level/kind
  spans.json         — front_matter / body / references / appendix(/acknowledgments) 区间锚点
  build_report.json  — 机器可读报告（正文基线字号、降级说明、候选计数）

退出码：0=成功；2=部分（几何/文本模式或存在无法定级候选）；3=失败。
"""
import argparse
import json
import os
import re
import statistics
import sys

NUM_RE = re.compile(r"^(\d+(?:\.\d+){0,3})[.)]?\s+(\S.*)$")
REF_ENTRY_LIKE = re.compile(r"(19|20)\d{2}")  # 编号行含年份+逗号 → 疑似参考文献条目
KEYWORD_KIND = [
    (re.compile(r"^(references|bibliography|参考文献)\s*$", re.I), "references"),
    (re.compile(r"^(acknowledg(e)?ments?|致谢)\b", re.I), "acknowledgments"),
    (re.compile(r"^(abstract|摘要)\s*$", re.I), "abstract"),
    (re.compile(r"^(appendix|附录)\b\s*([A-Z0-9.:-]*)", re.I), "appendix"),
    (re.compile(r"^(introduction|引言)\b", re.I), "introduction"),
]
SIZE_RATIO = 1.15      # 标题字号阈值（相对正文中位数）
TITLE_RATIO = 1.40     # 文档标题字号阈值
MAX_HEADING_LEN = 90   # 标题最大字符数（无编号信号时）
MAX_NUMBERED_LEN = 120 # 编号标题允许更长（含标题文本）


def load_lines(path):
    lines = []
    with open(path, encoding="utf-8") as f:
        for row in f:
            row = row.strip()
            if row:
                lines.append(json.loads(row))
    return lines


def is_allcaps_short(text):
    alpha = [c for c in text if c.isalpha()]
    return 3 <= len(text) <= 60 and len(alpha) >= 2 and all(c.isupper() for c in alpha)


def detect(lines, styled):
    """返回 (headings, candidates, notes)。headings 按 line_idx 升序。"""
    body_median = None
    if styled:
        sizes = [l["max_size"] for l in lines if l.get("max_size") and len(l["text"]) >= 30]
        body_median = statistics.median(sizes) if sizes else None
    notes = []
    if not styled or body_median is None:
        notes.append("字号信号不可用（mode!=styled）：仅使用编号与关键词信号检测标题。")

    # 先定位 References 行，抑制其后的伪编号（如 "1. Smith, A." 条目）
    ref_idx = None
    for l in lines:
        t = l["text"].strip()
        if re.match(r"^(references|bibliography|参考文献)\s*$", t, re.I):
            ref_idx = l["line_idx"]
            break

    headings, candidates = [], []

    # ---- 第 1 遍：关键词 + 编号标题（强信号）----
    first_struct_idx = None
    for l in lines:
        idx, text = l["line_idx"], l["text"].strip()
        size = l.get("max_size")

        kind = None
        for rx, k in KEYWORD_KIND:
            if rx.match(text) and len(text) <= 60:
                kind = k
                break
        if kind:
            headings.append(
                {"line_idx": idx, "number": None, "title": text, "level": 1,
                 "kind": kind, "page": l["page"], "y0": l["y0"]}
            )
            first_struct_idx = idx if first_struct_idx is None else min(first_struct_idx, idx)
            continue

        m = NUM_RE.match(text)
        if m and not (ref_idx is not None and idx > ref_idx):
            number = m.group(1)
            depth = number.count(".") + 1
            looks_ref = bool(REF_ENTRY_LIKE.search(text)) and "," in text
            if len(text) > MAX_NUMBERED_LEN or looks_ref:
                candidates.append(
                    {"line_idx": idx, "text": text, "page": l["page"], "y0": l["y0"],
                     "reason": "编号开头但过长/疑似列表或文献条目，未定为标题"}
                )
                continue
            headings.append(
                {"line_idx": idx, "number": number, "title": m.group(2).strip(),
                 "level": depth, "kind": "numbered",
                 "page": l["page"], "y0": l["y0"], "size": size}
            )
            first_struct_idx = idx if first_struct_idx is None else min(first_struct_idx, idx)

    # ---- 第 2 遍：无编号标题（弱信号，仅扫描首个强信号标题之后）----
    # 首个关键词/编号标题之前的区域按定义是 front_matter（题名/作者/摘要等），
    # 其中的大字号行是文档题名而非章节标题，必须排除，否则题名会污染层级树。
    detected = {h["line_idx"] for h in headings}
    for l in lines:
        idx, text = l["line_idx"], l["text"].strip()
        size, bold = l.get("max_size"), l.get("bold")
        if idx in detected:
            continue  # 第 1 遍已定为标题，避免重复
        if first_struct_idx is not None and idx <= first_struct_idx:
            continue

        if styled and size is not None and body_median:
            if size >= SIZE_RATIO * body_median and len(text) <= MAX_HEADING_LEN \
                    and (bold or size >= TITLE_RATIO * body_median):
                headings.append(
                    {"line_idx": idx, "number": None, "title": text, "level": None,
                     "kind": "unnumbered", "page": l["page"], "y0": l["y0"],
                     "size": size}
                )
                continue

        if is_allcaps_short(text):
            candidates.append(
                {"line_idx": idx, "text": text, "page": l["page"], "y0": l["y0"],
                 "reason": "全大写短行，疑似标题但证据不足，列入候选"}
            )

    headings.sort(key=lambda h: h["line_idx"])

    # 无编号标题按字号秩映射层级（rank 1 = 最大字号 → level 1）
    unnum = [h for h in headings if h["kind"] == "unnumbered"]
    if unnum:
        sizes_desc = sorted({h["size"] for h in unnum}, reverse=True)
        rank = {s: i + 1 for i, s in enumerate(sizes_desc)}
        for h in unnum:
            h["level"] = rank[h["size"]]
        notes.append(
            f"无编号标题 {len(unnum)} 个，按字号秩 {sizes_desc} 映射层级。"
        )
    return headings, candidates, notes, body_median


def build_tree(headings):
    """按 level 用栈构建嵌套树；同时计算每个节点的行区间。"""
    root = []
    stack = []  # (level, node)
    for h in headings:
        node = {
            "number": h["number"],
            "title": h["title"],
            "level": h["level"],
            "kind": h["kind"],
            "page": h["page"],
            "y0": h["y0"],
            "line_idx": h["line_idx"],
            "children": [],
        }
        while stack and stack[-1][0] >= h["level"]:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            root.append(node)
        stack.append((h["level"], node))
    # 行区间：到下一个 level <= 自身的标题前一行为止
    n = len(headings)
    for i, h in enumerate(headings):
        end = None
        for j in range(i + 1, n):
            if headings[j]["level"] <= h["level"]:
                end = headings[j]["line_idx"] - 1
                break
        h["end_line_idx"] = end  # None → 到文档末尾
    return root


def find_node_span(lines, headings, kind_or_pred):
    for h in headings:
        if (callable(kind_or_pred) and kind_or_pred(h)) or h["kind"] == kind_or_pred:
            end = h["end_line_idx"]
            end_line = lines[end] if end is not None else lines[-1]
            start_line = lines[h["line_idx"]]
            return {
                "start": {"page": start_line["page"], "y0": start_line["y0"]},
                "end": {"page": end_line["page"], "y0": end_line["y0"]},
                "start_line_idx": h["line_idx"],
                "end_line_idx": end if end is not None else lines[-1]["line_idx"],
            }
    return None


def compute_spans(lines, headings):
    notes = []
    last = lines[-1]

    def line_anchor(l):
        return {"page": l["page"], "y0": l["y0"]}

    # body 起点：编号 "1" 或 Introduction 关键词标题
    body_h = next(
        (h for h in headings
         if h["number"] == "1" or h["kind"] == "introduction"),
        None,
    )
    if body_h is None:
        body_h = next((h for h in headings if h["kind"] == "numbered"), None)
    if body_h is None:
        notes.append("未找到正文起点（编号 1 / Introduction）：body 区间为空，全部归入 front_matter。")

    ref_span = find_node_span(lines, headings, "references")
    app_span = find_node_span(lines, headings, "appendix")
    ack_span = find_node_span(lines, headings, "acknowledgments")

    spans = {}
    body_start_idx = body_h["line_idx"] if body_h else None
    # front_matter：文档起点 → body 前一行（含 title/authors/abstract）
    if body_start_idx is not None and body_start_idx > 0:
        fm_end = lines[body_start_idx - 1]
        spans["front_matter"] = {
            "start": line_anchor(lines[0]),
            "end": line_anchor(fm_end),
            "start_line_idx": 0,
            "end_line_idx": body_start_idx - 1,
        }
    elif body_start_idx == 0:
        spans["front_matter"] = None
        notes.append("文档首行即正文，无 front_matter。")

    if body_h is not None:
        body_end_idx = None
        for sp in (ref_span, app_span):
            if sp:
                cand = sp["start_line_idx"] - 1
                body_end_idx = cand if body_end_idx is None else min(body_end_idx, cand)
        body_end = lines[body_end_idx] if body_end_idx is not None else last
        spans["body"] = {
            "start": line_anchor(lines[body_start_idx]),
            "end": line_anchor(body_end),
            "start_line_idx": body_start_idx,
            "end_line_idx": body_end_idx if body_end_idx is not None else last["line_idx"],
        }
    else:
        spans["body"] = None

    spans["references"] = ref_span
    spans["appendix"] = app_span
    if ack_span:
        spans["acknowledgments"] = ack_span
    return spans, notes


def front_matter_detail(lines, spans, styled, body_median):
    """从 front_matter 区间提取 title / authors（大字号行=title，其余=authors/affiliation）。"""
    fm = spans.get("front_matter")
    if not fm:
        return {"title": None, "authors": None}
    seg = [l for l in lines
           if fm["start_line_idx"] <= l["line_idx"] <= fm["end_line_idx"]]
    seg = [l for l in seg
           if not re.match(r"^(abstract|摘要)\s*$", l["text"].strip(), re.I)]
    title_lines, other = [], []
    for l in seg:
        if styled and body_median and l.get("max_size") \
                and l["max_size"] >= TITLE_RATIO * body_median:
            title_lines.append(l["text"].strip())
        else:
            other.append(l["text"].strip())
    # 摘要正文行较长，authors 取 abstract 关键词之前的短行（此处近似：非 title 的前两行）
    authors = " ".join(other[:2]) if other else None
    return {
        "title": " ".join(title_lines) if title_lines else (seg[0]["text"].strip() if seg else None),
        "authors": authors,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="标题检测与层级定级")
    ap.add_argument("--lines", required=True, help="extract_styled_lines.py 的 lines.jsonl")
    ap.add_argument("--tree", required=True, help="输出 document_tree.json")
    ap.add_argument("--spans", required=True, help="输出 spans.json")
    ap.add_argument("--report", required=True, help="输出 build_report.json")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.lines):
        print(f"[build] 输入不存在: {args.lines}", file=sys.stderr)
        return 3
    lines = load_lines(args.lines)
    if not lines:
        print("[build] lines.jsonl 为空", file=sys.stderr)
        return 3

    styled = all(l.get("mode") == "styled" for l in lines)
    mode = lines[0].get("mode", "unknown")
    engine = lines[0].get("engine", "unknown")

    headings, candidates, notes, body_median = detect(lines, styled)
    if not headings:
        report = {
            "status": "failed", "mode": mode, "engine": engine,
            "uncertainty": "未检测到任何标题，无法构建层级树。",
            "degraded_notes": notes,
        }
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return 3

    tree = build_tree(headings)
    spans, span_notes = compute_spans(lines, headings)
    notes.extend(span_notes)
    fm = front_matter_detail(lines, spans, styled, body_median)

    # end_line_idx 回填进树节点
    end_map = {h["line_idx"]: h["end_line_idx"] for h in headings}

    def fill(node):
        node["end_line_idx"] = end_map.get(node["line_idx"])
        for c in node["children"]:
            fill(c)
        return node

    tree = [fill(n) for n in tree]

    tree_doc = {
        "engine": engine,
        "mode": mode,
        "body_size_median": body_median,
        "title": fm["title"],
        "authors": fm["authors"],
        "heading_count": len(headings),
        "tree": tree,
        "heading_candidates": candidates,
        "degraded_notes": notes + (
            ["存在无法定级的标题候选，详见 heading_candidates。"] if candidates else []
        ),
    }
    with open(args.tree, "w", encoding="utf-8") as f:
        json.dump(tree_doc, f, ensure_ascii=False, indent=2)

    spans_doc = {"spans": spans, "engine": engine, "mode": mode}
    with open(args.spans, "w", encoding="utf-8") as f:
        json.dump(spans_doc, f, ensure_ascii=False, indent=2)

    status = "success"
    if mode != "styled" or candidates:
        status = "partial"
    report = {
        "status": status,
        "engine": engine,
        "mode": mode,
        "body_size_median": body_median,
        "heading_count": len(headings),
        "candidate_count": len(candidates),
        "span_names": [k for k, v in spans.items() if v],
        "degraded_notes": tree_doc["degraded_notes"],
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[build] headings={len(headings)} candidates={len(candidates)} "
          f"spans={report['span_names']} status={status}")
    return 0 if status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
