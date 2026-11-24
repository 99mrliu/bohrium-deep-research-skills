#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix_check.py — 目标-内容-路线-指标一致性矩阵机器回检（规则 M1..M8）。

输入：--matrix consistency_matrix.json --draft proposal_sections.md [--plan plan.json]
      [--report check_report.json] [--threshold 0.35]

规则总览（细则见 references/matrix_rules.md）：
  M1 矩阵 JSON 结构合法（q/g/c/r/k 五类节点 + edges，ID 形态合法、无重复、边型合法）
  M2 覆盖链闭合 Q<-G<-C<-R 且 K->G（每个上层节点至少被一个下层节点覆盖）
  M3 无孤儿节点（G/C/R/K 均有出边挂到上层节点）
  M4 无悬空引用（edge 两端 ID 都必须已登记为节点）
  M5 矩阵 ID 与正文双向一致（矩阵每个 ID 在正文出现；正文同类编号都已登记）
  M6 七要素标题齐备（plan 清单或 SPEC 默认清单，允许常见别名）
  M7 厚度平衡（任一要素正文 < 全局均值 x 阈值时 warning；空要素 error）
  M8 正文计数表述与矩阵实际计数一致（若正文出现此类表述）

退出码：0 通过（允许 warning）；1 存在 error 级发现；2 参数或输入文件错误。
确定性：同一输入产生字节一致的报告（发现按规则号与消息排序，无时间戳）。
"""
import argparse
import json
import os
import re
import sys

VERSION = "1.0"

DEFAULT_ELEMENTS = [
    "立项依据", "科学问题", "研究目标", "研究内容",
    "技术路线", "创新点", "研究基础与可行性",
]

ELEMENT_ALIASES = {
    "立项依据": ["立项依据", "立项依据与研究意义", "研究意义"],
    "科学问题": ["科学问题", "拟解决的关键科学问题", "关键科学问题"],
    "研究目标": ["研究目标", "总体目标", "研究总体目标"],
    "研究内容": ["研究内容"],
    "技术路线": ["技术路线", "研究方案与技术路线", "技术路线与研究方案", "研究方案"],
    "创新点": ["创新点", "特色与创新", "创新之处", "项目特色与创新"],
    "研究基础与可行性": ["研究基础与可行性", "研究基础", "可行性分析", "工作基础"],
}

CLASSES = {
    "q": {"prefix": "Q", "label": "科学问题"},
    "g": {"prefix": "G", "label": "研究目标"},
    "c": {"prefix": "C", "label": "研究内容"},
    "r": {"prefix": "R", "label": "技术路线步骤"},
    "k": {"prefix": "K", "label": "考核指标"},
}
PREFIX_TO_CLASS = {v["prefix"]: k for k, v in CLASSES.items()}

# 合法的边型（子 -> 父）
ALLOWED_EDGES = {("g", "q"), ("c", "g"), ("r", "c"), ("k", "g")}

ID_FULL_RE = re.compile(r"[QGCRK][0-9]+\Z")
HEAD_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
ENUM_STRIP_RE = re.compile(
    r"^(?:第[一二三四五六七八九十0-9]+[章节部分][、.．:：]?\s*)?"
    r"(?:[（(]?[一二三四五六七八九十0-9]+[）)][、.．]?\s*|[一二三四五六七八九十0-9]+[、.．]\s*)*")

CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def id_scan_re(prefix):
    """正文中的编号识别：仅排除紧邻的 ASCII 字母数字（兼容中文语境，\\b 对 CJK 不可靠）。"""
    return re.compile(r"(?<![A-Za-z0-9])" + prefix + r"[0-9]+(?![A-Za-z0-9])")


def class_of(node_id):
    return PREFIX_TO_CLASS.get(node_id[0]) if node_id else None


def num_key(node_id):
    return int(node_id[1:])


def parse_cn_number(text):
    """解析 0-99 的中文/阿拉伯计数，失败返回 None。"""
    if text.isdigit():
        return int(text)
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CN_DIGIT.get(left, 1) if left else 1
        ones = CN_DIGIT.get(right, 0) if right else 0
        if (left and left not in CN_DIGIT) or (right and right not in CN_DIGIT):
            return None
        return tens * 10 + ones
    if len(text) == 1 and text in CN_DIGIT:
        return CN_DIGIT[text]
    return None


M8_LABELS = {
    "q": ["科学问题"],
    "g": ["研究目标", "总体目标"],
    "c": ["研究内容"],
    "r": ["技术路线"],
    "k": ["考核指标"],
}
M8_VERBS = ["共", "计", "设置", "提出", "凝练出", "凝练", "分解为", "分为",
            "包括", "包含", "安排", "确定"]
M8_NUM = r"(?:[0-9]+|[一二两三四五六七八九]?十[一二三四五六七八九]?|[一二两三四五六七八九])"


def m8_patterns(class_key):
    labels = "|".join(M8_LABELS[class_key])
    verbs = "|".join(M8_VERBS)
    units = "个|项|条|步" if class_key == "r" else "个|项|条"
    return re.compile(
        r"(?:%s)[^0-9一二两三四五六七八九十\n]{0,8}?(?:%s)?\s*(%s)\s*(?:%s)"
        % (labels, verbs, M8_NUM, units))


class Report:
    def __init__(self):
        self.findings = []

    def add(self, rule, severity, message, detail=None):
        self.findings.append({"rule": rule, "severity": severity,
                              "message": message, "detail": detail or {}})

    def errors(self):
        return [f for f in self.findings if f["severity"] == "error"]

    def warnings(self):
        return [f for f in self.findings if f["severity"] == "warning"]


def load_matrix(path, report):
    if not os.path.isfile(path):
        sys.stderr.write("错误：矩阵文件不存在：%s\n" % path)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.add("M1", "error", "矩阵文件无法解析为 JSON：%s" % exc)
        return None
    return doc


def check_m1(doc, report):
    """返回 (nodes_by_class, id_to_class, edges) ；结构不合法时尽量返回部分结果。"""
    nodes_by_class = {k: {} for k in CLASSES}
    id_to_class = {}
    edges = []
    if not isinstance(doc, dict):
        report.add("M1", "error", "矩阵顶层必须是 JSON 对象")
        return nodes_by_class, id_to_class, edges
    nodes = doc.get("nodes")
    if not isinstance(nodes, dict):
        report.add("M1", "error", "缺少 nodes 对象")
    else:
        for key in sorted(nodes.keys()):
            if key not in CLASSES:
                report.add("M1", "error", "nodes 含未知类别键：%s" % key)
        for class_key in CLASSES:
            entries = nodes.get(class_key, [])
            if not isinstance(entries, list):
                report.add("M1", "error", "nodes.%s 必须是数组" % class_key)
                continue
            for entry in entries:
                if not isinstance(entry, dict) or "id" not in entry:
                    report.add("M1", "error", "nodes.%s 含缺 id 的节点：%r" % (class_key, entry))
                    continue
                node_id = entry["id"]
                if not isinstance(node_id, str) or not ID_FULL_RE.match(node_id):
                    report.add("M1", "error", "非法节点 ID：%r" % (node_id,))
                    continue
                if class_of(node_id) != class_key:
                    report.add("M1", "error",
                               "节点 %s 前缀与类别 %s 不符" % (node_id, class_key))
                    continue
                if node_id in id_to_class:
                    report.add("M1", "error", "节点 ID 重复登记：%s" % node_id)
                    continue
                id_to_class[node_id] = class_key
                nodes_by_class[class_key][node_id] = entry
    raw_edges = doc.get("edges")
    if not isinstance(raw_edges, list):
        report.add("M1", "error", "缺少 edges 数组")
    else:
        for edge in raw_edges:
            if not isinstance(edge, dict) or "from" not in edge or "to" not in edge:
                report.add("M1", "error", "非法边对象：%r" % (edge,))
                continue
            src, dst = edge["from"], edge["to"]
            if not (isinstance(src, str) and ID_FULL_RE.match(src)
                    and isinstance(dst, str) and ID_FULL_RE.match(dst)):
                report.add("M1", "error", "边端点 ID 形态非法：%r" % (edge,))
                continue
            pair = (class_of(src), class_of(dst))
            if pair not in ALLOWED_EDGES:
                report.add("M1", "error",
                           "边型非法：%s->%s（只允许 G->Q、C->G、R->C、K->G）" % (src, dst))
                continue
            edges.append({"from": src, "to": dst})
    return nodes_by_class, id_to_class, edges


def check_m2(nodes_by_class, edges, report):
    """覆盖链闭合：每个 Q 至少一个 G->Q；每个 G 至少一个 C->G；每个 C 至少一个 R->C；
    每个 K 至少一条 K->G 出边。"""
    in_from = {}   # parent_id -> [child_ids]
    for edge in edges:
        in_from.setdefault(edge["to"], []).append(edge["from"])
    for qid in sorted(nodes_by_class["q"], key=num_key):
        children = [c for c in in_from.get(qid, []) if class_of(c) == "g"]
        if not children:
            report.add("M2", "error", "科学问题 %s 没有任何研究目标回应（缺 G->Q）" % qid)
    for gid in sorted(nodes_by_class["g"], key=num_key):
        children = [c for c in in_from.get(gid, []) if class_of(c) == "c"]
        if not children:
            report.add("M2", "error", "研究目标 %s 没有任何研究内容支撑（缺 C->G）" % gid)
    for cid in sorted(nodes_by_class["c"], key=num_key):
        children = [c for c in in_from.get(cid, []) if class_of(c) == "r"]
        if not children:
            report.add("M2", "error", "研究内容 %s 没有任何技术路线步骤覆盖（缺 R->C）" % cid)
    for kid in sorted(nodes_by_class["k"], key=num_key):
        outs = [e["to"] for e in edges if e["from"] == kid and class_of(e["to"]) == "g"]
        if not outs:
            report.add("M2", "error", "考核指标 %s 未挂接任何研究目标（缺 K->G）" % kid)


def check_m3(nodes_by_class, edges, report):
    """无孤儿：每个 G/C/R/K 至少一条出边挂到上层。"""
    expected = {"g": "q", "c": "g", "r": "c", "k": "g"}
    for class_key, parent_class in expected.items():
        for node_id in sorted(nodes_by_class[class_key], key=num_key):
            outs = [e for e in edges if e["from"] == node_id
                    and class_of(e["to"]) == parent_class]
            if not outs:
                report.add("M3", "error",
                           "孤儿节点：%s（%s）没有任何指向 %s 类上层的出边"
                           % (node_id, CLASSES[class_key]["label"], parent_class.upper()))


def check_m4(id_to_class, edges, report):
    for edge in edges:
        for endpoint in (edge["from"], edge["to"]):
            if endpoint not in id_to_class:
                report.add("M4", "error",
                           "悬空引用：边 %s->%s 指向未登记的 ID %s"
                           % (edge["from"], edge["to"], endpoint))


def check_m5(nodes_by_class, draft, report):
    registered = set()
    for class_key in CLASSES:
        registered.update(nodes_by_class[class_key].keys())
    # 正向：矩阵每个 ID 必须在正文出现
    for class_key in CLASSES:
        pat = id_scan_re(CLASSES[class_key]["prefix"])
        found = set(pat.findall(draft))
        for node_id in sorted(nodes_by_class[class_key], key=num_key):
            if node_id not in found:
                report.add("M5", "error",
                           "矩阵节点 %s 未在正文出现" % node_id)
    # 反向：正文出现的同类编号必须已登记
    for class_key in CLASSES:
        pat = id_scan_re(CLASSES[class_key]["prefix"])
        for node_id in sorted(set(pat.findall(draft)), key=num_key):
            if node_id not in registered:
                report.add("M5", "error",
                           "正文出现的编号 %s 未登记进矩阵（%s类）"
                           % (node_id, CLASSES[class_key]["label"]))


def parse_headings(draft):
    """返回 [(level, raw_text, stripped_text, body)]，body 为到下一标题前的正文。"""
    matches = list(HEAD_RE.finditer(draft))
    headings = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(draft)
        raw = match.group(2).strip()
        stripped = ENUM_STRIP_RE.sub("", raw).strip()
        headings.append((len(match.group(1)), raw, stripped, draft[start:end]))
    return headings


def match_element(stripped_heading):
    for element, aliases in ELEMENT_ALIASES.items():
        for alias in aliases:
            if alias in stripped_heading:
                return element
    return None


def check_m6_m7(elements, draft, threshold, report, stats):
    headings = parse_headings(draft)
    bodies = {}
    for element in elements:
        body = None
        for _level, _raw, stripped, text in headings:
            if match_element(stripped) == element or element in stripped:
                body = text if body is None else body + text
        bodies[element] = body
    lengths = {}
    for element in elements:
        body = bodies[element]
        if body is None:
            report.add("M6", "error",
                       "七要素标题缺失：未找到『%s』（含别名：%s）对应的 markdown 标题"
                       % (element, "、".join(ELEMENT_ALIASES.get(element, [element]))))
            lengths[element] = None
        else:
            lengths[element] = len(re.sub(r"\s+", "", body))
    present = [lengths[e] for e in elements if lengths[e] is not None]
    for element in elements:
        if lengths[element] == 0:
            report.add("M7", "error", "要素『%s』标题存在但正文为空" % element)
    if present:
        mean = sum(present) / float(len(present))
        floor = mean * threshold
        for element in elements:
            length = lengths[element]
            if length is not None and 0 < length < floor:
                report.add("M7", "warning",
                           "要素『%s』正文厚度 %d 字符，低于全局均值 %.0f 的 %.2f 倍（%.0f）"
                           % (element, length, mean, threshold, floor))
        stats["element_char_mean"] = round(mean, 1)
    stats["element_chars"] = lengths


def check_m8(nodes_by_class, draft, report):
    for class_key in CLASSES:
        pat = m8_patterns(class_key)
        actual = len(nodes_by_class[class_key])
        for match in pat.finditer(draft):
            stated = parse_cn_number(match.group(1))
            if stated is None:
                continue
            if stated != actual:
                report.add("M8", "error",
                           "计数不一致：正文称%s %s 个/项/条，矩阵实际 %d 个（原文：%s）"
                           % (CLASSES[class_key]["label"], match.group(1), actual,
                              match.group(0)))


def load_elements(plan_path):
    if plan_path is None:
        return list(DEFAULT_ELEMENTS), "spec_default"
    if not os.path.isfile(plan_path):
        sys.stderr.write("错误：plan 文件不存在：%s\n" % plan_path)
        sys.exit(2)
    try:
        with open(plan_path, "r", encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        sys.stderr.write("错误：plan 文件无法解析：%s\n" % exc)
        sys.exit(2)
    elements = plan.get("elements")
    if not isinstance(elements, list) or not all(isinstance(e, str) for e in elements):
        sys.stderr.write("错误：plan.json 中 elements 字段非法。\n")
        sys.exit(2)
    return list(elements), plan_path


def main():
    parser = argparse.ArgumentParser(
        description="一致性矩阵机器回检：校验 Q/G/C/R/K 矩阵与章节稿正文的双向一致性（M1..M8）。")
    parser.add_argument("--matrix", required=True, help="consistency_matrix.json 路径")
    parser.add_argument("--draft", required=True, help="章节稿 markdown 路径")
    parser.add_argument("--plan", help="plan.json 路径（缺省用 SPEC 默认七要素）")
    parser.add_argument("--report", help="check_report.json 输出路径（缺省只打印摘要）")
    parser.add_argument("--threshold", type=float, default=0.35,
                        help="M7 厚度预警阈值（相对全局均值，默认 0.35）")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    args = parser.parse_args()

    if not os.path.isfile(args.draft):
        sys.stderr.write("错误：章节稿文件不存在：%s\n" % args.draft)
        sys.exit(2)
    try:
        with open(args.draft, "r", encoding="utf-8") as fh:
            draft = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("错误：章节稿无法读取：%s\n" % exc)
        sys.exit(2)

    elements, elements_source = load_elements(args.plan)

    report = Report()
    stats = {}
    doc = load_matrix(args.matrix, report)
    if doc is not None:
        nodes_by_class, id_to_class, edges = check_m1(doc, report)
        check_m2(nodes_by_class, edges, report)
        check_m3(nodes_by_class, edges, report)
        check_m4(id_to_class, edges, report)
        check_m5(nodes_by_class, draft, report)
        stats["node_counts"] = {k: len(v) for k, v in nodes_by_class.items()}
        stats["edge_count"] = len(edges)
    else:
        stats["node_counts"] = None
    check_m6_m7(elements, draft, args.threshold, report, stats)
    if doc is not None:
        check_m8(nodes_by_class, draft, report)

    report.findings.sort(key=lambda f: (f["rule"], f["severity"], f["message"]))
    out = {
        "tool": "matrix_check.py",
        "version": VERSION,
        "inputs": {"matrix": args.matrix, "draft": args.draft,
                   "plan": args.plan, "threshold": args.threshold},
        "elements_source": elements_source,
        "elements": elements,
        "summary": {
            "errors": len(report.errors()),
            "warnings": len(report.warnings()),
            "rules_triggered": sorted({f["rule"] for f in report.findings}),
        },
        "stats": stats,
        "findings": report.findings,
    }
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    print("matrix_check.py %s：error=%d warning=%d" %
          (VERSION, len(report.errors()), len(report.warnings())))
    for finding in report.findings:
        print("  [%s][%s] %s" % (finding["rule"], finding["severity"], finding["message"]))
    if args.report:
        print("  报告已写出：%s" % args.report)
    if report.errors():
        print("结果：不通过（存在 error 级发现）")
        return 1
    print("结果：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
