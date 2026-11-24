#!/usr/bin/env python3
"""decompose.py — 研究问题六要素抽取与子问题（SQ）骨架生成。

确定性启发式（关键词 + 正则，中英文），仅 Python 标准库。
同一输入必然产生同一输出；不含随机数与时间戳。

用法：
    python3 decompose.py [--task /input/task.md] [--case /input/case.json]
                         [--output /app/output/decomposition.json]

退出码：
    0  成功（TO_FILL 提醒通过 stdout 给出，不影响退出码）
    2  用法 / IO / JSON 解析错误
"""
import argparse
import json
import os
import re
import sys

TO_FILL = "TO_FILL"

ELEMENT_KEYS = [
    "research_object",
    "mechanism_intervention",
    "comparison",
    "outcomes",
    "time_range",
    "evidence_requirements",
]

ELEMENT_LABELS_CN = {
    "research_object": "研究对象",
    "mechanism_intervention": "机制/干预",
    "comparison": "对照",
    "outcomes": "结局指标",
    "time_range": "时间范围",
    "evidence_requirements": "证据要求",
}

# 每个要素的模式列表；按顺序尝试，首个命中生效。re.IGNORECASE 统一生效。
PATTERNS = {
    "research_object": [
        r"研究对象\s*[:：]\s*(.+)",
        r"(?:research object|target system|material system|study system|subject|population)\s*[:：]\s*(.+)",
    ],
    "mechanism_intervention": [
        r"(?:机制/干预|干预/机制)\s*[:：]\s*(.+)",
        r"(?:机制|干预|处理策略|调控手段)\s*[:：]\s*(.+)",
        r"(?:mechanism|intervention|treatment|strategy)\s*[:：]\s*(.+)",
    ],
    "comparison": [
        r"(?:对照|对比对象|比较对象|基线)\s*[:：]\s*(.+)",
        r"(?:comparison|comparator|control group|baseline)\s*[:：]\s*(.+)",
    ],
    "outcomes": [
        r"(?:结局指标|评估指标|性能指标|结局|指标)\s*[:：]\s*(.+)",
        r"(?:outcome measures|outcomes?|metrics?|indicators?)\s*[:：]\s*(.+)",
    ],
    "time_range": [
        r"((?:19|20)\d{2}\s*[-–—~]\s*(?:(?:19|20)\d{2}|至今|现在|present|now))",
        r"((?:19|20)\d{2}\s*(?:至|到)\s*(?:(?:19|20)\d{2}|至今|现在))",
        r"(近\s*\d+\s*年(?:以来)?)",
        r"(last\s+\d+\s+years)",
        r"(?:时间范围|时间窗|检索年限)\s*[:：]\s*(.+)",
        r"(?:time range|date range|publication window)\s*[:：]\s*(.+)",
    ],
    "evidence_requirements": [
        r"(?:证据要求|证据标准|纳入标准|文献类型要求)\s*[:：]\s*(.+)",
        r"(?:evidence requirements?|inclusion criteria|study types?|evidence criteria)\s*[:：]\s*(.+)",
    ],
}

MAX_ELEMENT_LEN = 80


def clean_fragment(text):
    """截断到句读边界并限制长度，保证确定性。"""
    text = text.strip()
    for sep in ["。", "；", ";", "\n"]:
        idx = text.find(sep)
        if idx > 0:
            text = text[:idx]
    text = text.strip().rstrip("，,、. ")
    if len(text) > MAX_ELEMENT_LEN:
        text = text[:MAX_ELEMENT_LEN].rstrip()
    return text


def extract_elements(task_text):
    """逐要素抽取；抽不到置 TO_FILL。"""
    elements = {}
    lines = task_text.splitlines()
    for key in ELEMENT_KEYS:
        value = TO_FILL
        for pat in PATTERNS[key]:
            found = None
            if key == "time_range":
                m = re.search(pat, task_text, re.IGNORECASE)
                if m:
                    found = m.group(1)
            else:
                for line in lines:
                    m = re.search(pat, line, re.IGNORECASE)
                    if m:
                        found = m.group(1)
                        break
            if found:
                value = clean_fragment(found)
                if value:
                    break
                value = TO_FILL
        elements[key] = value
    return elements


def build_sub_questions(elements):
    """由六要素拼装 4-6 个 SQ 模板（确定性规则）。

    必选 4 个：SQ-1 背景定界、SQ-2 机制、SQ-3 对照效果、SQ-4 证据边界。
    可选 2 个：SQ-5 趋势（time_range 已填时启用）、SQ-6 指标测量（outcomes 已填时启用）。
    """
    obj = elements["research_object"]
    mech = elements["mechanism_intervention"]
    comp = elements["comparison"]
    outc = elements["outcomes"]
    span = elements["time_range"]
    evid = elements["evidence_requirements"]

    def facet(*keys):
        return {k: elements[k] for k in keys}

    sqs = [
        {
            "id": "SQ-1",
            "statement": "%s 的定义、分类与研究边界是什么？" % obj,
            "facets": facet("research_object"),
            "query_cn": TO_FILL,
            "query_en": TO_FILL,
            "acceptance_criteria": TO_FILL,
            "depends_on": [],
        },
        {
            "id": "SQ-2",
            "statement": "%s 在 %s 中的作用机制是什么？" % (mech, obj),
            "facets": facet("mechanism_intervention", "research_object"),
            "query_cn": TO_FILL,
            "query_en": TO_FILL,
            "acceptance_criteria": TO_FILL,
            "depends_on": [],
        },
        {
            "id": "SQ-3",
            "statement": "相较 %s，%s 在 %s 上表现如何？" % (comp, obj, outc),
            "facets": facet("comparison", "research_object", "outcomes"),
            "query_cn": TO_FILL,
            "query_en": TO_FILL,
            "acceptance_criteria": TO_FILL,
            "depends_on": [],
        },
        {
            "id": "SQ-4",
            "statement": "关于 %s 的现有证据（时间范围 %s）满足哪些证据要求（%s），其适用边界为何？" % (obj, span, evid),
            "facets": facet("research_object", "time_range", "evidence_requirements"),
            "query_cn": TO_FILL,
            "query_en": TO_FILL,
            "acceptance_criteria": TO_FILL,
            "depends_on": [],
        },
    ]
    if span != TO_FILL:
        sqs.append({
            "id": "SQ-5",
            "statement": "%s 内 %s 相关研究的趋势与演变如何？" % (span, obj),
            "facets": facet("time_range", "research_object"),
            "query_cn": TO_FILL,
            "query_en": TO_FILL,
            "acceptance_criteria": TO_FILL,
            "depends_on": [],
        })
    if outc != TO_FILL:
        sqs.append({
            "id": "SQ-6",
            "statement": "%s 研究中 %s 的测量方法与报告规范如何？" % (obj, outc),
            "facets": facet("outcomes", "research_object"),
            "query_cn": TO_FILL,
            "query_en": TO_FILL,
            "acceptance_criteria": TO_FILL,
            "depends_on": [],
        })
    return sqs


def load_case(path):
    """防御式解析 case.json：任何异常都退化为最小可用结构。"""
    info = {"case_id": "UNKNOWN_CASE", "output_contract": None}
    if not path or not os.path.isfile(path):
        print("[WARN] case.json 不存在或不可读：%s（case_id 置为 UNKNOWN_CASE）" % path,
              file=sys.stderr)
        return info
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("[WARN] case.json 解析失败：%s（case_id 置为 UNKNOWN_CASE）" % exc,
              file=sys.stderr)
        return info
    if isinstance(data, dict):
        cid = data.get("case_id")
        if isinstance(cid, str) and cid.strip():
            info["case_id"] = cid.strip()
        contract = data.get("output_contract")
        if contract is not None:
            info["output_contract"] = contract
    return info


def main():
    parser = argparse.ArgumentParser(
        description="研究问题六要素抽取与 SQ 骨架生成（确定性启发式）")
    parser.add_argument("--task", default="/input/task.md", help="task.md 路径")
    parser.add_argument("--case", default="/input/case.json", help="case.json 路径")
    parser.add_argument("--output", default="/app/output/decomposition.json",
                        help="decomposition.json 输出路径")
    args = parser.parse_args()

    if not os.path.isfile(args.task):
        print("[ERROR] task 文件不存在：%s" % args.task, file=sys.stderr)
        return 2
    try:
        with open(args.task, "r", encoding="utf-8") as fh:
            task_text = fh.read()
    except OSError as exc:
        print("[ERROR] task 文件读取失败：%s" % exc, file=sys.stderr)
        return 2

    case_info = load_case(args.case)
    elements = extract_elements(task_text)
    sub_questions = build_sub_questions(elements)
    to_fill = [k for k in ELEMENT_KEYS if elements[k] == TO_FILL]

    payload = {
        "case_id": case_info["case_id"],
        "source_task": args.task,
        "elements": elements,
        "element_labels_cn": ELEMENT_LABELS_CN,
        "to_fill_elements": to_fill,
        "sub_questions": sub_questions,
        "notes": [
            "本文件由 decompose.py 确定性生成；TO_FILL 字段必须由 Agent 人工补齐。",
            "acceptance_criteria 写法见 references/decomposition_schema.md。",
            "depends_on 仅在构造检索式确实需要另一 SQ 结果时才标注。",
        ],
    }

    out_dir = os.path.dirname(os.path.abspath(args.output))
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        print("[ERROR] 输出写入失败：%s" % exc, file=sys.stderr)
        return 2

    print("[OK] decomposition.json 已写入：%s" % os.path.abspath(args.output))
    print("[OK] 子问题数：%d（%s）" % (len(sub_questions),
          ", ".join(sq["id"] for sq in sub_questions)))
    if to_fill:
        print("[ACTION REQUIRED] 以下六要素未能从 task 文本抽取，已置 TO_FILL，"
              "Agent 必须人工补齐后再进入检索规划：")
        for key in to_fill:
            print("  - %s（%s）" % (key, ELEMENT_LABELS_CN[key]))
        print("[ACTION REQUIRED] 所有 SQ 的 query_cn/query_en/acceptance_criteria "
              "均为 TO_FILL 占位，必须补齐。")
    else:
        print("[OK] 六要素全部抽取成功；仍需补齐各 SQ 的 "
              "query_cn/query_en/acceptance_criteria 占位。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
