#!/usr/bin/env python3
"""T2 题卡装配与可判性门禁；T1 答案结构校验。"""
import argparse
import json
import os
import re
import sys

from source_index import atomic_json, normalize_with_map

T2_WORDS = ("出题", "题卡", "benchmark", "draft", "草拟", "4道", "四道")
REQUIRED_ITEM_FIELDS = ("task", "scope", "reference_answer", "rubric", "evidence")


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def detect_mode(task_path, requested):
    if requested != "auto":
        return requested
    try:
        task = open(task_path, "r", encoding="utf-8").read().lower()
    except OSError:
        return "T1"
    return "T2" if any(word.lower() in task for word in T2_WORDS) else "T1"


def verdict_map(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        rows = read_json(path).get("verdicts", [])
    except Exception:
        return {}
    mapping = {}
    for row in rows:
        mapping.setdefault(str(row.get("item_id", "")), []).append(row)
    return mapping


def rubric_ok(rubric):
    if not isinstance(rubric, dict):
        return False
    bands = [rubric.get(key) for key in ("0", "1", "2")]
    if any(not isinstance(text, str) or not text.strip() for text in bands):
        return False
    anchored = all(("证据" in text or "锚" in text or "source" in text.lower() or "quote" in text.lower()) for text in bands)
    return bool(rubric.get("machine_check")) or anchored


def validate_item(item, verdicts, index):
    reasons, verdict_rows = [], verdicts.get(str(item.get("id", "")), []) if verdicts is not None else []
    for field in REQUIRED_ITEM_FIELDS:
        value = item.get(field)
        if value is None or value == "" or value == [] or value == {}:
            reasons.append("缺少字段：" + field)
    if not str(item.get("difficulty", "")).strip():
        reasons.append("缺少难度说明 difficulty")
    if not str(item.get("data_license", "")).strip():
        reasons.append("缺少数据授权说明 data_license")
    if not str(item.get("unique_answer_rationale", "")).strip():
        reasons.append("缺少答案唯一可辩护说明")
    if not rubric_ok(item.get("rubric")):
        reasons.append("评分规则必须含 0/1/2 分档，且可机判或每档锚定证据")
    task_norm = normalize_with_map(str(item.get("task", "")))[0]
    answer_norm = normalize_with_map(str(item.get("reference_answer", "")))[0]
    if answer_norm and len(answer_norm) >= 3 and answer_norm in task_norm:
        reasons.append("题干泄露参考答案")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("证据锚点列表为空")
    else:
        for number, row in enumerate(evidence):
            if not isinstance(row, dict) or not row.get("locator") or not row.get("quote"):
                reasons.append("第 %d 条证据缺少 locator/quote" % (number + 1))
    if verdicts is None:
        status = "pending_verification"
    else:
        failed = [row for row in verdict_rows if row.get("verdict") in ("fail", "degraded")]
        passed = [row for row in verdict_rows if row.get("verdict") == "pass"]
        if failed:
            reasons.extend("证据机器裁决 %s：%s" % (row.get("verdict"), row.get("reason")) for row in failed)
        if not passed:
            reasons.append("参考答案没有至少一条 pass 证据")
        status = "unfit" if reasons else "fit"
    result = dict(item)
    result["status"] = "unfit" if status == "pending_verification" and reasons else status
    result["unfit_reasons"] = reasons
    result["checklist_order"] = index + 1
    result["machine_verdict_summary"] = {"pass": sum(1 for row in verdict_rows if row.get("verdict") == "pass"), "fail": sum(1 for row in verdict_rows if row.get("verdict") == "fail"), "degraded": sum(1 for row in verdict_rows if row.get("verdict") == "degraded")}
    return result


def forge(work_path, verdicts_path, output, expected):
    verdicts = verdict_map(verdicts_path)
    try:
        plan = read_json(work_path)
    except Exception as exc:
        plan = {"item_bank": [], "global_issues": ["work_plan 缺失或 JSON 畸形：" + str(exc)]}
    items = plan.get("item_bank")
    if not isinstance(items, list):
        items = []
    validated = [validate_item(item, verdicts, index) for index, item in enumerate(items) if isinstance(item, dict)]
    issues = list(plan.get("global_issues", []))
    if len(validated) != expected:
        issues.append("正式 T2 要求 %d 张题卡，当前 %d 张；未入集。" % (expected, len(validated)))
        for item in validated:
            if item["status"] == "fit":
                item["status"] = "unfit"
            item["unfit_reasons"].append("题卡数量不符合工单要求")
    result = dict((key, value) for key, value in plan.items() if key != "item_bank")
    result.update({"mode": "T2", "expected_count": expected, "item_bank": validated, "unfit_items": [row["id"] for row in validated if row.get("status") != "fit"], "gate_issues": issues, "formal_bank_allowed": verdicts is not None and len(validated) == expected and all(row.get("status") == "fit" for row in validated)})
    atomic_json(output, result)
    return result


def claim_has_number(claim):
    text = claim.get("claim", "") if isinstance(claim, dict) else str(claim)
    marker = str(claim.get("honesty", "")).lower() if isinstance(claim, dict) else ""
    return any(word in marker for word in ("unreported", "uncertain", "unable", "无法判断", "未报告")) and bool(re.search(r"\d", text))


def validate_answers(path, verdicts_path, output):
    try:
        data = read_json(path)
    except Exception as exc:
        data = {"answers": [], "global_issues": ["answers 缺失或 JSON 畸形：" + str(exc)]}
    answers = data.get("answers", []) if isinstance(data.get("answers", []), list) else []
    verdicts = verdict_map(verdicts_path)
    validated = []
    for index, answer in enumerate(answers):
        reasons = []
        if not isinstance(answer, dict):
            reasons.append("答案记录不是对象")
            answer = {"id": "answer%d" % (index + 1)}
        for field in ("answer", "claims", "evidence"):
            if field not in answer or answer[field] in (None, "", [], {}):
                reasons.append("缺少字段：" + field)
        if any(claim_has_number(claim) for claim in answer.get("claims", []) if isinstance(claim, (dict, str))):
            reasons.append("诚实标记 claim 不得含具体数值")
        answer_id = str(answer.get("id", "answer%d" % (index + 1)))
        rows = verdicts.get(answer_id, []) if verdicts is not None else []
        if verdicts is None:
            status = "pending_verification"
        elif any(row.get("verdict") != "pass" for row in rows):
            reasons.append("存在非 pass 证据裁决")
            status = "unfit"
        elif not rows:
            reasons.append("没有 pass 证据裁决")
            status = "unfit"
        else:
            status = "fit"
        row = dict(answer)
        row.update({"id": answer_id, "status": "unfit" if status == "pending_verification" and reasons else status, "unfit_reasons": reasons})
        validated.append(row)
    result = dict((key, value) for key, value in data.items() if key != "answers")
    result.update({"mode": "T1", "answers": validated, "unfit_items": [row["id"] for row in validated if row.get("status") != "fit"], "formal_answers_allowed": verdicts is not None and bool(validated) and all(row.get("status") == "fit" for row in validated)})
    atomic_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description="按工单类型校验/装配内容，并执行可判性门禁。")
    parser.add_argument("--task", default="/input/task.md", help="task.md 路径，用于 T1/T2 识别")
    parser.add_argument("--mode", choices=("auto", "T1", "T2"), default="auto", help="工单模式")
    parser.add_argument("--work-plan", default="/app/work/items.json", help="T2 工作计划 JSON")
    parser.add_argument("--answers", default="/app/work/answers.json", help="T1 答案 JSON")
    parser.add_argument("--verdicts", default="/app/work/verdicts.json", help="quote_gate 裁决；不存在时输出 pending")
    parser.add_argument("--output", default="/app/work/items_validated.json", help="验证输出")
    parser.add_argument("--expected-count", type=int, default=4, help="T2 正式题卡数；示例可设为 2")
    args = parser.parse_args()
    mode = detect_mode(args.task, args.mode)
    result = forge(args.work_plan, args.verdicts, args.output, args.expected_count) if mode == "T2" else validate_answers(args.answers, args.verdicts, args.output)
    counts = {}
    rows = result.get("item_bank") or result.get("answers") or []
    for row in rows:
        counts[row.get("status", "unknown")] = counts.get(row.get("status", "unknown"), 0) + 1
    print("item_forge(%s): %s -> %s" % (mode, counts, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
