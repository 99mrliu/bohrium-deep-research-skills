#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""书面裁决双通道分歧，导出最终分、 agreement report 与 result.json。"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

RESERVED = {"case_id", "status", "status_reason", "sources", "uncertainty", "change_records", "scores", "agreement"}
DIMENSION_ORDER = ["correctness", "evidence_anchoring", "completeness", "boundary_honesty"]


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


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        if isinstance(default, dict):
            payload = dict(default)
            payload["_load_error"] = "{}: {}".format(type(exc).__name__, exc)
            return payload
        if default is not None:
            return default
        return {"_load_error": "{}: {}".format(type(exc).__name__, exc)}


def contract_fields(case):
    spec = case.get("output_contract", {}) if isinstance(case, dict) else {}
    if isinstance(spec, dict):
        return [str(key) for key in spec]
    fields = []
    if isinstance(spec, list):
        for entry in spec:
            if isinstance(entry, str):
                fields.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    fields.append(str(name))
    return fields


def anchor_ok(value):
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, dict) or not value:
        return False
    has_source = bool(str(value.get("source") or value.get("file") or "").strip())
    has_pointer = bool(value.get("quote") or value.get("locator") or value.get("lines"))
    return has_source and has_pointer


def validate_record(record, disagreement):
    errors = []
    if not isinstance(record, dict):
        return ["record_not_object"]
    for key in ("item", "dimension", "pass1", "pass2", "final"):
        if key not in record:
            errors.append("missing_" + key)
    if errors:
        return errors
    if str(record.get("item")) != str(disagreement.get("item")):
        errors.append("item_mismatch")
    if record.get("dimension") != disagreement.get("dimension"):
        errors.append("dimension_mismatch")
    if record.get("pass1") != disagreement.get("pass1") or record.get("pass2") != disagreement.get("pass2"):
        errors.append("pass_score_mismatch")
    if record.get("final") not in (0, 1, 2):
        errors.append("invalid_final_score")
    if not str(record.get("rationale") or "").strip():
        errors.append("missing_rationale")
    if not anchor_ok(record.get("evidence_anchor")):
        errors.append("missing_evidence_anchor")
    return errors


def process_adjudications(disagreements, adjudication_payload):
    records = adjudication_payload.get("records", adjudication_payload) if isinstance(adjudication_payload, dict) else adjudication_payload
    if not isinstance(records, list):
        records = []
    by_key = {"{}::{}".format(d.get("item"), d.get("dimension")): d for d in disagreements}
    resolved = {}
    pending = {}
    rejected = []
    for idx, record in enumerate(records, 1):
        key = "{}::{}".format(record.get("item") if isinstance(record, dict) else None,
                              record.get("dimension") if isinstance(record, dict) else None)
        disagreement = by_key.get(key)
        if disagreement is None:
            rejected.append({"record_index": idx, "record": record, "errors": ["no_matching_disagreement"]})
            continue
        errors = validate_record(record, disagreement)
        if errors:
            rejected.append({"record_index": idx, "record": record, "errors": errors})
            pending[key] = {"disagreement": disagreement, "errors": errors, "status": "pending"}
            continue
        resolved[key] = {
            "item": str(record["item"]),
            "dimension": record["dimension"],
            "pass1": record["pass1"],
            "pass2": record["pass2"],
            "final": record["final"],
            "rationale": str(record["rationale"]).strip(),
            "evidence_anchor": record["evidence_anchor"],
        }
        pending.pop(key, None)
    for key, disagreement in by_key.items():
        if key not in resolved and key not in pending:
            pending[key] = {"disagreement": disagreement, "errors": ["missing_adjudication_record"], "status": "pending"}
    return list(resolved.values()), list(pending.values()), rejected


def apply_final_scores(pass1, resolved):
    final_items = []
    resolution_map = {"{}::{}".format(r["item"], r["dimension"]): r for r in resolved}
    for item in pass1.get("items", []):
        item_id = str(item.get("item_id"))
        dims = {}
        for dim in DIMENSION_ORDER:
            source_dim = dict(item.get("dimensions", {}).get(dim, {}))
            key = "{}::{}".format(item_id, dim)
            if key in resolution_map:
                adjudication = resolution_map[key]
                source_dim["score"] = adjudication["final"]
                source_dim["justification"] = adjudication["rationale"]
                source_dim["source"] = "adjudicated"
                source_dim["adjudication"] = adjudication
            dims[dim] = source_dim
        total = sum(dims[dim].get("score", 0) for dim in dims if isinstance(dims[dim].get("score"), int))
        final_items.append({"item_id": item_id, "dimensions": dims, "total_score": total, "max_score": 8})
    return {"case_id": pass1.get("case_id"), "task_type": pass1.get("task_type"), "items": final_items, "pending_count": 0}


def item_bank(items_payload):
    if isinstance(items_payload, list):
        return items_payload
    if isinstance(items_payload, dict):
        for key in ("item_bank", "items", "answers", "cards"):
            if isinstance(items_payload.get(key), list):
                return items_payload[key]
    return []


def evidence_map(cards):
    mapped = []
    for pos, item in enumerate(cards, 1):
        if not isinstance(item, dict):
            continue
        anchors = item.get("evidence_anchors") or item.get("evidence") or item.get("anchors") or []
        mapped.append({"item_id": item.get("item_id") or item.get("id") or "item-{}".format(pos), "evidence_anchors": anchors})
    return mapped


def source_list(root):
    base = Path(root)
    if not base.exists():
        return []
    allowed = {".txt", ".text", ".md", ".pdf"}
    return [
        str(path.relative_to(base))
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.suffix.lower() in allowed and path.name != "task.md"
    ]


def update_result(result_path, case, items_payload, final_scores, agreement, pending, source_root):
    result = load_json(result_path, {})
    if not isinstance(result, dict) or "_load_error" in result:
        result = {}
    result["case_id"] = str(case.get("case_id") or result.get("case_id") or "unknown")
    for field in contract_fields(case):
        if field not in RESERVED and field not in result:
            result[field] = None
    status = "部分完成" if pending else "成功"
    reason = ("存在 {} 个未清零下书面裁决分歧；按铁律不得标记为成功。".format(len(pending))
              if pending else "双通道评分、κ 计算与全部分歧书面裁决均已完成。")
    cards = item_bank(items_payload)
    known_values = {
        "answer_summary": "完成 {} 个作答/题卡的双通道评分；分歧 {} 个，pending {} 个。".format(len(final_scores.get("items", [])), agreement.get("disagreement_count", 0), len(pending)),
        "item_bank": cards,
        "evidence_map": evidence_map(cards),
        "status_note": reason,
    }
    for field in contract_fields(case):
        if field in known_values:
            result[field] = known_values[field]
    result["status"] = status
    result["status_reason"] = reason
    result["scores"] = final_scores
    result["agreement"] = agreement
    result["sources"] = source_list(source_root)
    uncertainty = result.get("uncertainty") if isinstance(result.get("uncertainty"), list) else []
    additions = [
        "双通道使用同一模型与同一源材料，κ 是一致性下界而非真值保证。",
        "κ 的小样本解释以 agreement_report.md 为准。",
    ]
    if agreement.get("small_sample_warning"):
        additions.append("κ 配对数小于 30，单个分歧会显著改变估计。")
    for text in additions:
        if text not in uncertainty:
            uncertainty.append(text)
    result["uncertainty"] = uncertainty
    records = result.get("change_records") if isinstance(result.get("change_records"), list) else []
    records.append({"step": 6, "actor": "adjudicate.py", "change": "写入最终分、一致性报告结论与聚合 status", "pending_count": len(pending)})
    result["change_records"] = records
    atomic_write_json(result_path, result)
    return result


def fmt(value):
    return "undefined" if value is None else ("{:.6f}".format(value))


def make_report(agreement, disagreements, resolved, pending, rejected):
    lines = [
        "# 双通道评分一致性报告",
        "",
        "## 一致性汇总",
        "",
        "- 配对数 N：{}".format(agreement.get("n_pairs")),
        "- 观察一致率 Po：{}".format(fmt(agreement.get("observed_agreement"))),
        "- 偶然一致率 Pe：{}".format(fmt(agreement.get("expected_agreement"))),
        "- Cohen's kappa：{}".format(fmt(agreement.get("cohens_kappa"))),
        "- 解释：{}".format(agreement.get("kappa_interpretation")),
        "",
        "## 逐维一致率",
        "",
        "| 维度 | 一致/总数 | 一致率 |",
        "|---|---:|---:|",
    ]
    for dim, stat in agreement.get("dimension_agreement", {}).items():
        rate = stat.get("agreement_rate")
        lines.append("| {} | {}/{} | {} |".format(dim, stat.get("agree"), stat.get("total"), fmt(rate)))
    lines += ["", "## 分歧与裁决", ""]
    lines.append("- 处置统计：分歧 {} 个；已接受裁决 {} 条；pending {} 条；被拒绝记录 {} 条。".format(len(disagreements), len(resolved), len(pending), len(rejected)))
    if not disagreements:
        lines.append("未发现跨通道分歧。")
    for item in disagreements:
        lines.append("- {} / {}：pass1={}，pass2={}".format(item.get("item"), item.get("dimension"), item.get("pass1"), item.get("pass2")))
    lines += ["", "### 已接受裁决", ""]
    for item in resolved:
        lines.append("- {} / {} → final={}；理由：{}".format(item["item"], item["dimension"], item["final"], item["rationale"]))
    if not resolved:
        lines.append("无。")
    lines += ["", "### 被拒绝/待补裁决", ""]
    for item in rejected:
        lines.append("- 记录 {}：{}".format(item.get("record_index"), ",".join(item.get("errors", []))))
    for item in pending:
        lines.append("- pending：{} / {}；原因：{}".format(item["disagreement"].get("item"), item["disagreement"].get("dimension"), ",".join(item.get("errors", []))))
    if not rejected and not pending:
        lines.append("无。")
    lines += [
        "",
        "## 残余风险",
        "",
        "- κ 度量一致性，不度量答案真实正确性。",
        "- 双通道可能共享同一模型偏差与同一源材料遗漏。",
        "- 小样本时 κ 置信区间很宽；低 κ 或退化分布必须升人工复核。",
    ]
    return "\n".join(lines) + "\n"


def write_human_queue(path, pending):
    lines = ["# human_review 队列", ""]
    for item in pending:
        d = item["disagreement"]
        lines.append("- {} / {}：pass1={}，pass2={}；阻塞原因：{}".format(d.get("item"), d.get("dimension"), d.get("pass1"), d.get("pass2"), ",".join(item.get("errors", []))))
    atomic_write_text(path, "\n".join(lines) + "\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="裁决 pass1/pass2 分歧并更新 result.json")
    parser.add_argument("--case", required=True)
    parser.add_argument("--pass1", required=True)
    parser.add_argument("--pass2", required=True)
    parser.add_argument("--agreement", required=True)
    parser.add_argument("--disagreements", required=True)
    parser.add_argument("--adjudications", required=True)
    parser.add_argument("--items", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--final-out", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--human-review-out")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        case = load_json(args.case, {})
        pass1 = load_json(args.pass1, {})
        pass2 = load_json(args.pass2, {})
        agreement = load_json(args.agreement, {})
        disagreement_payload = load_json(args.disagreements, {})
        adjudications = load_json(args.adjudications, {})
        items_payload = load_json(args.items, {})
        if not all(isinstance(value, dict) for value in (case, pass1, pass2, agreement, disagreement_payload, adjudications)) or not isinstance(items_payload, (dict, list)):
            raise ValueError("输入 JSON 顶层类型不合法。")
        for name, payload in (("case", case), ("pass1", pass1), ("pass2", pass2), ("agreement", agreement), ("disagreements", disagreement_payload), ("adjudications", adjudications), ("items", items_payload)):
            if isinstance(payload, dict) and "_load_error" in payload:
                raise ValueError(name + " JSON 畸形: " + payload["_load_error"])
        disagreements = disagreement_payload.get("disagreements", [])
        if not isinstance(disagreements, list):
            disagreements = []
        resolved, pending, rejected = process_adjudications(disagreements, adjudications)
        final_scores = apply_final_scores(pass1, resolved)
        final_scores["pending_count"] = len(pending)
        final_scores["pending"] = pending
        atomic_write_json(args.final_out, final_scores)
        report = make_report(agreement, disagreements, resolved, pending, rejected)
        atomic_write_text(args.report_out, report)
        if pending:
            queue_path = args.human_review_out or str(Path(args.report_out).with_name("human_review.md"))
            write_human_queue(queue_path, pending)
        update_result(args.result, case, items_payload, final_scores, agreement, pending, args.source_root)
        print(json.dumps({"ok": True, "final_scores": args.final_out, "report": args.report_out, "resolved": len(resolved), "pending": len(pending), "rejected_records": len(rejected)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "{}: {}".format(type(exc).__name__, exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
