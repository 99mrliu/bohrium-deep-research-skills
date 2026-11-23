#!/usr/bin/env python3
"""把源索引、机器裁决和门禁结果汇总为平台 result.json。"""
import argparse
import json
import os
import sys
import tempfile

from source_index import atomic_json

CORE_FIELDS = {"case_id", "status", "status_reason", "sources", "uncertainty", "change_records"}
INTERNAL_FIELDS = {"mode", "expected_count", "gate_issues", "formal_bank_allowed", "formal_answers_allowed"}


def read_json(path, required=False):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        if required:
            raise
        return None


def atomic_text(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".export-result-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def contract_fields(case):
    contract = case.get("output_contract") if isinstance(case, dict) else None
    fields = []

    def add(value):
        if isinstance(value, str):
            fields.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name", item.get("field", item.get("key")))
                    if isinstance(name, str):
                        fields.append(name)
                elif isinstance(item, str):
                    fields.append(item)
        elif isinstance(value, dict):
            fields.extend(str(key) for key in value)

    if isinstance(contract, dict):
        for key in ("fields", "required_fields", "output_fields", "required"):
            if key in contract:
                add(contract[key])
                break
    else:
        add(contract)
    seen, result = set(), []
    for field in fields:
        if field not in seen:
            seen.add(field)
            result.append(field)
    return result


def load_work(work_dir):
    item_path = os.path.join(work_dir, "items_validated.json")
    answer_path = os.path.join(work_dir, "answers_validated.json")
    items, answers = read_json(item_path), read_json(answer_path)
    work = items if isinstance(items, dict) and (items.get("mode") == "T2" or not isinstance(answers, dict)) else answers
    return work, items, answers


def work_values(work):
    values = {}
    if not isinstance(work, dict):
        return values
    rows = work.get("item_bank") if isinstance(work.get("item_bank"), list) else work.get("answers")
    fit_rows = [row for row in rows or [] if isinstance(row, dict) and row.get("status") == "fit"]
    for key, value in work.items():
        if key in INTERNAL_FIELDS:
            continue
        if key == "item_bank":
            values[key] = fit_rows
        elif key == "answers":
            values[key] = fit_rows
        elif key not in ("unfit_items",):
            values[key] = value
    return values


def evidence_map(work, verdicts):
    if not isinstance(work, dict):
        return {}
    rows = work.get("item_bank") if isinstance(work.get("item_bank"), list) else work.get("answers")
    by_item = {}
    for row in verdicts.get("verdicts", []) if isinstance(verdicts, dict) else []:
        by_item.setdefault(str(row.get("item_id")), []).append({"locator": row.get("locator"), "quote": row.get("quote"), "verdict": row.get("verdict"), "reason": row.get("reason"), "machine_code": row.get("machine_code")})
    result = {}
    for row in rows or []:
        if isinstance(row, dict):
            item_id = str(row.get("id", "unowned"))
            result[item_id] = {"status": row.get("status"), "evidence": row.get("evidence"), "machine_verdicts": by_item.get(item_id, [])}
    return result


def fix_advice(code):
    advice = {
        "locator_drift": "将 locator 改到 found_elsewhere 中实际命中的锚点，或改引文以匹配原锚点。",
        "not_in_corpus": "回源逐字复制连续片段；原文不支持时删除论断并标记无法判断。",
        "possible_extraction_defect": "按争议建议修复抽取缺陷后重建索引，再复跑 quote_gate。",
        "bad_locator": "按 references/anchor_spec.md 的 <文件名>#<锚点ID> 语法修正。",
    }
    return advice.get(code, "补齐缺失字段、修正证据后复跑 quote_gate 与 item_forge。")


def failure_report(work, verdicts):
    lines = ["# Failure Analysis", ""]
    failures = []
    if isinstance(verdicts, dict):
        for row in verdicts.get("verdicts", []):
            if row.get("verdict") in ("fail", "degraded"):
                failures.append(("evidence:" + str(row.get("item_id")), {"locator": row.get("locator"), "quote": row.get("quote")}, [row.get("reason", "")], fix_advice(row.get("machine_code"))))
    rows = []
    if isinstance(work, dict):
        rows = work.get("item_bank") if isinstance(work.get("item_bank"), list) else work.get("answers", [])
    for row in rows or []:
        if isinstance(row, dict) and row.get("status") != "fit":
            failures.append(("item:" + str(row.get("id")), row, row.get("unfit_reasons", []), "补齐字段并让全部证据获得 pass 后复跑门禁；仍不合格则禁止入正式题集。"))
    if not failures:
        lines += ["当前没有未处理的 fail/degraded/unfit 记录。", ""]
        return "\n".join(lines)
    for item_id, original, reasons, fix in failures:
        lines += ["## " + item_id, "", "### 原始输出", "", "```json", json.dumps(original, ensure_ascii=False, indent=2, sort_keys=True), "```", "", "### 原因"]
        lines += ["- " + str(reason) for reason in reasons] or ["- 未记录原因"]
        lines += ["", "### 修法", "", fix, ""]
    return "\n".join(lines)


def score_rows(work, verdicts):
    rows = []
    source_rows = []
    if isinstance(work, dict):
        source_rows = work.get("item_bank") if isinstance(work.get("item_bank"), list) else work.get("answers", [])
    grouped = {}
    for row in verdicts.get("verdicts", []) if isinstance(verdicts, dict) else []:
        grouped.setdefault(str(row.get("item_id")), []).append(row)
    for row in source_rows or []:
        if not isinstance(row, dict):
            continue
        item_id, checks = str(row.get("id", "unowned")), grouped.get(str(row.get("id", "unowned")), [])
        if any(check.get("verdict") == "fail" for check in checks) or not any(check.get("verdict") == "pass" for check in checks):
            evidence_score = 0
        elif any(check.get("verdict") == "degraded" for check in checks) or row.get("status") == "pending_verification":
            evidence_score = 1
        else:
            evidence_score = 2
        judgeability = {"fit": 2, "pending_verification": 1, "unfit": 0}.get(row.get("status"), 0)
        rows.append({"id": item_id, "score": min(evidence_score, judgeability), "evidence_anchor_score": evidence_score, "judgeability_score": judgeability, "machine_verdicts": [{"locator": row2.get("locator"), "verdict": row2.get("verdict"), "machine_code": row2.get("machine_code")} for row2 in checks], "gate_status": row.get("status"), "reasons": row.get("unfit_reasons", [])})
    return rows


def export(case_path, work_dir, output_dir, init=False):
    os.makedirs(output_dir, exist_ok=True)
    try:
        case = read_json(case_path, required=True)
    except Exception as exc:
        case = {"case_id": None, "output_contract": {}}
        case_error = str(exc)
    else:
        case_error = None
    fields = contract_fields(case)
    base = {"case_id": case.get("case_id") if isinstance(case, dict) else None, "status": "无法判断", "status_reason": "初始化占位：尚未建立源索引或生成工作文件；不编造答案。", "sources": [], "uncertainty": ["--init 阶段仅锁定合法部分结果。"], "change_records": [{"step": 0, "action": "init_partial_result", "file": "result.json"}]}
    if case_error:
        base["uncertainty"].append("case.json 缺失或畸形：" + case_error)
    for field in fields:
        if field not in CORE_FIELDS:
            base[field] = None
            base["uncertainty"].append("output_contract 字段 `%s` 初始化缺失，置为 null。" % field)
    if init:
        atomic_json(os.path.join(output_dir, "result.json"), base)
        print("init: 已写合法部分 result.json")
        return 0
    index = read_json(os.path.join(work_dir, "source_index.json")) or {}
    verdicts = read_json(os.path.join(work_dir, "verdicts.json")) or {}
    work, _, _ = load_work(work_dir)
    values = work_values(work)
    if "evidence_map" not in values:
        values["evidence_map"] = evidence_map(work, verdicts)
    uncertainty = []
    if case_error:
        uncertainty.append("case.json 缺失或畸形：" + case_error)
    index_degraded = bool(index.get("degraded"))
    if index_degraded:
        uncertainty.append("源索引 degraded：" + "；".join(index.get("notes", [])[:3]))
    null_fields = []
    for field in fields:
        if field in CORE_FIELDS:
            uncertainty.append("output_contract 与核心运行字段 `%s` 冲突，保留运行字段。" % field)
            continue
        value = values.get(field)
        if value is None:
            null_fields.append(field)
        base[field] = value
    summary = verdicts.get("summary", {}) if isinstance(verdicts, dict) else {}
    failed = int(summary.get("fail", 0)) + int(summary.get("degraded", 0))
    allowed = bool(work.get("formal_bank_allowed") if isinstance(work, dict) and work.get("mode") == "T2" else work.get("formal_answers_allowed") if isinstance(work, dict) else False)
    if failed or not allowed or null_fields or index_degraded:
        base["status"] = "部分完成"
        reason_parts = []
        if failed:
            reason_parts.append("存在 %d 条未处理 fail/degraded 证据裁决" % failed)
        if not allowed:
            reason_parts.append("内容未通过完整可判性门禁")
        if index_degraded:
            reason_parts.append("至少一个源材料索引 degraded")
        if null_fields:
            reason_parts.append("契约字段缺失：" + ",".join(null_fields))
        base["status_reason"] = "；".join(reason_parts) + "。局限已在 failure_analysis.md 与 uncertainty 记录。"
    else:
        base["status"] = "成功"
        base["status_reason"] = "全部 required output_contract 字段已填充；全部证据锚点由机器裁决 pass，门禁允许交付。"
    base["sources"] = [{"doc_id": doc.get("doc_id"), "file": doc.get("file"), "sha256": doc.get("sha256"), "bytes": doc.get("bytes"), "degraded": doc.get("degraded"), "notes": doc.get("notes", [])} for doc in index.get("documents", [])]
    for field in null_fields:
        uncertainty.append("output_contract 字段 `%s` 无法由工作文件填充，置为 null。" % field)
    if failed:
        uncertainty.append("仍有证据未获得 pass；禁止把这些题卡/论断视为已核验。")
    base["uncertainty"] = uncertainty
    base["change_records"] = [{"step": 1, "action": "build_source_index", "file": "source_index.json"}, {"step": 2, "action": "draft_and_gate", "file": os.path.basename((work or {}).get("mode", "") and ("items_validated.json" if work.get("mode") == "T2" else "answers_validated.json") or "work_file.json")}, {"step": 3, "action": "quote_gate", "file": "verdicts.json"}, {"step": 4, "action": "export_result", "file": "result.json"}]
    atomic_json(os.path.join(output_dir, "result.json"), base)
    atomic_text(os.path.join(output_dir, "failure_analysis.md"), failure_report(work, verdicts))
    atomic_json(os.path.join(output_dir, "scoring_record.json"), {"schema_version": "1.0", "case_id": base["case_id"], "items": score_rows(work, verdicts), "note": "evidence_anchor_score 仅由 quote_gate 机器 verdict 决定；人工不得覆盖。"})
    print("export: status=%s fields=%d" % (base["status"], len(fields)))
    return 0


def main():
    parser = argparse.ArgumentParser(description="契约驱动导出 result.json、failure_analysis.md、scoring_record.json。")
    parser.add_argument("--case", default="/input/case.json", help="case.json 路径")
    parser.add_argument("--work-dir", default="/app/work", help="工作目录")
    parser.add_argument("--output-dir", default="/app/output", help="交付目录")
    parser.add_argument("--init", action="store_true", help="立即写合法部分 result.json 后退出")
    args = parser.parse_args()
    return export(args.case, args.work_dir, args.output_dir, args.init)


if __name__ == "__main__":
    sys.exit(main())
