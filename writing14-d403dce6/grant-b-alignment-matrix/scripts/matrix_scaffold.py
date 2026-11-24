#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix_scaffold.py — 从 case.json / organizer-workorder.json 提取七要素清单与一致性约束，
生成 plan.json（要素清单 + 编号体系约定 + 写作顺序建议）与空矩阵模板 consistency_matrix.template.json。

确定性：同一输入文件产生字节一致的输出（不依赖时间戳、网络或环境）。
退出码：0 成功；2 参数或输入文件错误（缺文件、JSON 无法解析、两个输入都未给）。
"""
import argparse
import json
import os
import sys

VERSION = "1.0"

# SPEC 默认七要素（案例未另行指定时使用）
DEFAULT_ELEMENTS = [
    "立项依据", "科学问题", "研究目标", "研究内容",
    "技术路线", "创新点", "研究基础与可行性",
]

# 在 case / workorder JSON 中查找要素清单时认可的键名（小写比较）
ELEMENT_KEYS = {
    "elements", "elements_required", "required_elements",
    "seven_elements", "section_elements", "要素", "七要素", "要素清单",
}

# 已知要素别名（用于在任意字符串列表中识别"这是一份要素清单"）
KNOWN_ELEMENT_TOKENS = {
    "立项依据", "科学问题", "研究目标", "研究内容", "技术路线",
    "创新点", "研究基础", "可行性", "研究方案", "考核指标",
}

CONSTRAINT_TOKENS = ("一致", "对应", "对齐", "编号", "矩阵", "匹配", "衔接", "关联")

NUMBERING = {
    "Q": {"node_class": "q", "meaning": "科学问题", "pattern": "Q1, Q2, ...",
          "rule": "正文首次出现写作『科学问题 Q1（……）』，此后可直接引用 Q1"},
    "G": {"node_class": "g", "meaning": "研究目标", "pattern": "G1, G2, ...",
          "rule": "每个 G 必须回应至少一个 Q，并被至少一个 C 支撑"},
    "C": {"node_class": "c", "meaning": "研究内容", "pattern": "C1, C2, ...",
          "rule": "每个 C 必须支撑至少一个 G，并被至少一个 R 覆盖"},
    "R": {"node_class": "r", "meaning": "技术路线步骤", "pattern": "R1, R2, ...",
          "rule": "每个 R 必须挂接到具体 C"},
    "K": {"node_class": "k", "meaning": "考核指标", "pattern": "K1, K2, ...",
          "rule": "每个 K 必须挂接到具体 G，不得『另说一套』"},
}

EDGE_RULES = [
    {"from": "G", "to": "Q", "meaning": "研究目标回应科学问题"},
    {"from": "C", "to": "G", "meaning": "研究内容支撑研究目标"},
    {"from": "R", "to": "C", "meaning": "技术路线步骤落实研究内容"},
    {"from": "K", "to": "G", "meaning": "考核指标锚定研究目标"},
]

WRITING_ORDER = [
    "第 1 步：从材料中凝练科学问题并按 Q1..Qn 编号，先写入矩阵 nodes.q",
    "第 2 步：把科学问题拆成研究目标 G1..Gn，写入 nodes.g 并建立 G->Q 边",
    "第 3 步：为每个目标配置研究内容 C1..Cn，写入 nodes.c 并建立 C->G 边",
    "第 4 步：按研究内容组织技术路线步骤 R1..Rn，写入 nodes.r 并建立 R->C 边",
    "第 5 步：把考核指标 K1..Kn 逐个挂到具体 G，写入 nodes.k 并建立 K->G 边",
    "第 6 步：用 matrix_check.py 对矩阵先做结构自检（M1 结构、M2/M3/M4 链路，可选）",
    "第 7 步：按七要素顺序撰写章节稿正文，正文中真实引用 Q/G/C/R/K 编号",
    "第 8 步：每次改稿同步改矩阵，交付前运行 matrix_check.py，exit 0 才允许交付",
    "第 9 步：运行 matrix_render.py 生成要素对照说明表，嵌入章节稿附录",
]


def load_json(path, label):
    if not os.path.isfile(path):
        sys.stderr.write("错误：%s 文件不存在：%s\n" % (label, path))
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        sys.stderr.write("错误：%s 无法解析为 JSON：%s（%s）\n" % (label, path, exc))
        sys.exit(2)


def looks_like_element_list(value):
    """判断一个字符串列表是否像七要素清单：>=4 项命中已知要素别名。"""
    if not isinstance(value, list) or not value:
        return False
    if not all(isinstance(item, str) for item in value):
        return False
    hits = 0
    for item in value:
        for token in KNOWN_ELEMENT_TOKENS:
            if token in item:
                hits += 1
                break
    return hits >= 4 and hits == len(value)


def walk(node, path, elements_hits, constraint_hits):
    """确定性递归遍历（按插入序），收集要素清单候选与一致性约束文本。"""
    if isinstance(node, dict):
        for key, value in node.items():
            child = "%s.%s" % (path, key)
            if key.lower() in ELEMENT_KEYS and looks_like_element_list(value):
                elements_hits.append((child, list(value)))
            elif looks_like_element_list(value):
                elements_hits.append((child, list(value)))
            elif isinstance(value, str) and any(t in value for t in CONSTRAINT_TOKENS) \
                    and any(t in value for t in ("一致", "对应", "对齐", "衔接")):
                constraint_hits.append((child, value))
            walk(value, child, elements_hits, constraint_hits)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            walk(item, "%s[%d]" % (path, idx), elements_hits, constraint_hits)


def main():
    parser = argparse.ArgumentParser(
        description="从 case.json / organizer-workorder.json 提取七要素清单与一致性约束，"
                    "生成 plan.json 与空矩阵模板（找不到要素清单时使用 SPEC 默认七要素）。")
    parser.add_argument("--case", help="案例 case.json 路径（可选）")
    parser.add_argument("--workorder", help="组织方 organizer-workorder.json 路径（可选）")
    parser.add_argument("--outdir", default=".",
                        help="plan.json 与 consistency_matrix.template.json 的输出目录（默认当前目录）")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    args = parser.parse_args()

    if not args.case and not args.workorder:
        sys.stderr.write("错误：--case 与 --workorder 至少提供一个。\n")
        sys.exit(2)
    if not os.path.isdir(args.outdir):
        sys.stderr.write("错误：输出目录不存在：%s\n" % args.outdir)
        sys.exit(2)

    case_doc = load_json(args.case, "case") if args.case else None
    wo_doc = load_json(args.workorder, "workorder") if args.workorder else None

    case_id = None
    if isinstance(case_doc, dict):
        case_id = case_doc.get("case_id") or case_doc.get("id")

    elements_hits, constraint_hits = [], []
    # workorder 优先于 case（组织方要求是显式约束）
    if wo_doc is not None:
        walk(wo_doc, "workorder", elements_hits, constraint_hits)
    if case_doc is not None:
        walk(case_doc, "case", elements_hits, constraint_hits)

    if elements_hits:
        elements_source, elements = elements_hits[0]
    else:
        elements_source, elements = "spec_default", list(DEFAULT_ELEMENTS)

    constraints = [{"path": p, "text": t} for p, t in constraint_hits]

    plan = {
        "plan_version": VERSION,
        "tool": "matrix_scaffold.py",
        "inputs": {"case": args.case, "workorder": args.workorder},
        "case_id": case_id,
        "elements": elements,
        "elements_source": elements_source,
        "numbering": NUMBERING,
        "edge_rules": EDGE_RULES,
        "constraints_found": constraints,
        "writing_order": WRITING_ORDER,
    }

    template = {
        "version": VERSION,
        "_comment": "一致性矩阵模板。nodes 五类节点：q=科学问题(Q#) g=研究目标(G#) c=研究内容(C#) "
                    "r=技术路线步骤(R#) k=考核指标(K#)；edges 方向为子->父："
                    "G->Q（目标回应问题）、C->G（内容支撑目标）、R->C（步骤落实内容）、K->G（指标锚定目标）。"
                    "每个节点对象含 id 与 title 两字段。",
        "case_id": case_id,
        "nodes": {"q": [], "g": [], "c": [], "r": [], "k": []},
        "edges": [],
    }

    plan_path = os.path.join(args.outdir, "plan.json")
    tmpl_path = os.path.join(args.outdir, "consistency_matrix.template.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(tmpl_path, "w", encoding="utf-8") as fh:
        json.dump(template, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("matrix_scaffold.py %s 完成" % VERSION)
    print("  要素来源：%s（%d 项）" % (elements_source, len(elements)))
    for idx, elem in enumerate(elements, 1):
        print("    %d. %s" % (idx, elem))
    print("  一致性约束线索：%d 条" % len(constraints))
    print("  已写出：%s" % plan_path)
    print("  已写出：%s" % tmpl_path)
    print("  写作顺序建议：")
    for step in WRITING_ORDER:
        print("    " + step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
