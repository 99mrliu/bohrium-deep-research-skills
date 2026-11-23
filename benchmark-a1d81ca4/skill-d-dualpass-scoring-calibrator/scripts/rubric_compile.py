#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 task.md 与 case.json 编译双通道评分表。"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

DIMENSIONS = [
    {
        "key": "correctness",
        "name": "正确性",
        "t1_focus": "答案命题被源材料支持，不无源推断。",
        "t2_focus": "参考答案被源文支持；评分规则不会奖励无源结论。",
        "scoring_mode": "semantic_with_written_reason",
    },
    {
        "key": "evidence_anchoring",
        "name": "证据锚定",
        "t1_focus": "每个关键断言有可机检引文，引文位于声称锚点内。",
        "t2_focus": "题卡引文可机检，且位于声称材料范围/锚点内。",
        "scoring_mode": "deterministic_machine_check",
    },
    {
        "key": "completeness",
        "name": "完整性",
        "t1_focus": "逐项回应任务，必要答案、证据与限制齐备。",
        "t2_focus": "任务、材料范围、参考答案、评分规则、证据锚点五字段齐备。",
        "scoring_mode": "deterministic_field_count",
    },
    {
        "key": "boundary_honesty",
        "name": "边界诚实",
        "t1_focus": "未报告、冲突、不确定与不可判断处显式标注。",
        "t2_focus": "未报告信息与材料冲突显式标注，不把缺失写成事实。",
        "scoring_mode": "deterministic_marker_plus_review",
    },
]


def atomic_write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp_name, str(target))
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path, payload):
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        if isinstance(default, dict):
            payload = dict(default)
            payload["_load_error"] = "{}: {}".format(type(exc).__name__, exc)
            return payload
        return {"_load_error": "{}: {}".format(type(exc).__name__, exc)} if default is None else default


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def detect_task_type(task_text):
    keywords = ["出题", "题卡", "benchmark", "DRAFT", "草拟", "4道", "四道"]
    hits = [kw for kw in keywords if kw.lower() in task_text.lower()]
    return ("T2" if hits else "T1"), hits


def chinese_number(token):
    table = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if token.isdigit():
        return int(token)
    return table.get(token)


def expected_count(task_text, task_type):
    if task_type == "T2":
        pattern = r"(?:起草|草拟|设计|编制|编写)[^。；\n]{0,20}?(\d+|一|二|两|三|四|五|六|七|八|九|十)\s*道"
        match = re.search(pattern, task_text, flags=re.I)
        if match:
            value = chinese_number(match.group(1))
            if value:
                return max(1, min(20, value))
        return 4
    numbered = re.findall(r"^\s*(?:\d+|[一二三四五六七八九十]+)[、.．]", task_text, flags=re.M)
    return max(1, min(20, len(numbered) if numbered else 1))


def contract_fields(case):
    spec = case.get("output_contract", {})
    fields = []
    if isinstance(spec, dict):
        fields = [str(k) for k in spec.keys()]
    elif isinstance(spec, list):
        for entry in spec:
            if isinstance(entry, str):
                fields.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    fields.append(str(name))
    return fields


def discover_sources(root):
    base = Path(root)
    found = []
    if not base.exists():
        return found
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".txt", ".md", ".text", ".pdf"}:
            found.append(str(path.relative_to(base)))
    return found


def read_anchor_section(task_type):
    default_path = Path(__file__).resolve().parents[1] / "references" / "rubric_anchors.md"
    text = read_text(default_path)
    marker = "## T1" if task_type == "T1" else "## T2"
    start = text.find(marker)
    if start < 0:
        return "锚点库缺失；仅使用 rubric.json 中的维度摘要。"
    end = text.find("\n## ", start + 1)
    return text[start:end if end >= 0 else len(text)].strip()


def build_rubric(case, task_text, source_root):
    task_type, hits = detect_task_type(task_text)
    count = expected_count(task_text, task_type)
    dims = []
    for dim in DIMENSIONS:
        copied = dict(dim)
        copied["scale"] = {"0": "不满足", "1": "部分满足", "2": "满足"}
        copied["focus"] = copied.pop("t2_focus" if task_type == "T2" else "t1_focus")
        copied.pop("t1_focus" if task_type == "T2" else "t2_focus", None)
        dims.append(copied)
    return {
        "rubric_id": "dualpass-scoring-calibrator-v1",
        "case_id": str(case.get("case_id", "unknown")),
        "task_type": task_type,
        "detected_keywords": hits,
        "expected_item_count": count,
        "output_contract_fields": contract_fields(case),
        "dimensions": dims,
        "anchor_policy": read_anchor_section(task_type),
        "source_files": discover_sources(source_root),
        "compilation_warnings": [],
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="编译 T1/T2 双通道评分 rubric.json")
    parser.add_argument("--case", required=True, help="/input/case.json")
    parser.add_argument("--task", required=True, help="/input/task.md")
    parser.add_argument("--source-root", required=True, help="源材料目录")
    parser.add_argument("--output", required=True, help="输出 rubric.json")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        case = load_json(args.case, {})
        if not isinstance(case, dict):
            case = {}
        task_text = read_text(args.task)
        rubric = build_rubric(case, task_text, args.source_root)
        if not task_text.strip():
            rubric["compilation_warnings"].append("task.md 为空或不可读，按 T1/单项任务降级编译。")
        if isinstance(case, dict) and "_load_error" in case:
            rubric["compilation_warnings"].append("case.json 畸形，contract 字段无法读取。")
        atomic_write_json(args.output, rubric)
        print(json.dumps({"ok": True, "output": args.output, "task_type": rubric["task_type"], "expected_item_count": rubric["expected_item_count"]}, ensure_ascii=False))
        return 0
    except Exception as exc:  # 最后的防崩溃兜底
        print(json.dumps({"ok": False, "error": "{}: {}".format(type(exc).__name__, exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
