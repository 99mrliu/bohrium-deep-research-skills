#!/usr/bin/env python3
"""contract_guard.py -- 终检质量门：契约逐字段核验 + 七要素覆盖检测 + 非空纪律。

用法：
  python3 contract_guard.py CASE_JSON RESULT_JSON REPORT_JSON

检查项（每项 pass/fail 写入 guard_report.json）：
  contract_field:<名>   字段存在且非 null/空串/空数组/空对象；缺项列出
  element:<要素>        对 proposal_draft 文本做关键词段落检测，缺要素报警
  sources_nonempty      sources 为非空数组
  change_records_nonempty / uncertainty_nonempty  非空数组
  status_consistency    status=ok 当且仅当字段与要素全过

任何 fail 都会把 result.json 强制回 status="partial" 并在 uncertainty 点名（原子写回）。
退出码：0 全部通过；1 存在 fail。
"""
import datetime
import json
import os
import sys

ELEMENT_KEYWORDS = [
    ("background_gap", "研究背景与缺口", ["研究背景", "缺口"]),
    ("problem_objective", "问题定义与目标", ["问题定义", "研究目标"]),
    ("technical_route", "技术路线与阶段计划", ["技术路线", "阶段计划"]),
    ("risk_fallback", "风险与备选", ["风险", "备选方案"]),
    ("expected_results", "预期成果", ["预期成果"]),
    ("citation_evidence", "引用证据", ["引用证据", "参考文献"]),
    ("editable_deliverable", "可编辑交付", ["可编辑交付", "交付物"]),
]


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path, obj):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, os.path.basename(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _is_empty(value):
    return value is None or value == "" or value == [] or value == {}


def main():
    if len(sys.argv) != 4 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) == 2 else 2)
    case_path, result_path, report_path = sys.argv[1:4]

    case = _read_json(case_path)
    doc = _read_json(result_path)
    contract = case.get("output_contract") or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract)

    items = []
    missing_fields = []
    for name in fields:
        empty = _is_empty(doc.get(name))
        if empty:
            missing_fields.append(name)
        items.append({
            "id": "contract_field:%s" % name,
            "result": "fail" if empty else "pass",
            "detail": "字段缺失或为空" if empty else "字段已填"})

    draft = doc.get("proposal_draft")
    draft_text = draft if isinstance(draft, str) else ""
    missing_elements = []
    for key, label, keywords in ELEMENT_KEYWORDS:
        hits = [kw for kw in keywords if kw in draft_text]
        ok = bool(hits)
        if not ok:
            missing_elements.append(label)
        items.append({
            "id": "element:%s" % key,
            "result": "pass" if ok else "fail",
            "detail": ("命中关键词: %s" % ",".join(hits)) if ok
                      else "proposal_draft 缺少「%s」段落（关键词 %s 均未命中）"
                           % (label, "/".join(keywords))})

    for key in ("sources", "change_records", "uncertainty"):
        value = doc.get(key)
        ok = isinstance(value, list) and len(value) > 0
        items.append({
            "id": "%s_nonempty" % key,
            "result": "pass" if ok else "fail",
            "detail": "非空，%d 条" % len(value) if ok else "缺失或为空数组"})

    hard_fail = bool(missing_fields or missing_elements)
    status = doc.get("status")
    consistent = (status == "ok") == (not hard_fail) and status in ("ok", "partial", "failed")
    items.append({
        "id": "status_consistency",
        "result": "pass" if consistent else "fail",
        "detail": "status=%r 与完整度一致" % status if consistent
                  else "status=%r 与完整度不一致（缺字段 %s / 缺要素 %s）"
                       % (status, missing_fields, missing_elements)})

    fails = [it for it in items if it["result"] == "fail"]
    forced = False
    if fails and doc.get("status") != "partial":
        doc["status"] = "partial"
        forced = True
    if fails:
        note = "contract_guard 终检拦截：缺字段 %s；缺要素 %s" % (
            missing_fields or "无", missing_elements or "无")
        doc.setdefault("uncertainty", []).append(note)
        doc.setdefault("change_records", []).append({
            "at": _utc_now(), "action": "contract_guard",
            "detail": "终检 %d 项 fail，强制 status=partial" % len(fails)})
        _atomic_write_json(result_path, doc)

    report = {
        "case_id": case.get("case_id", doc.get("case_id", "unknown")),
        "checked_at": _utc_now(),
        "overall": "fail" if fails else "pass",
        "fail_count": len(fails),
        "missing_fields": missing_fields,
        "missing_elements": missing_elements,
        "status_forced_partial": forced,
        "items": items,
    }
    _atomic_write_json(report_path, report)
    print(json.dumps({"overall": report["overall"], "fail_count": len(fails),
                      "missing_fields": missing_fields,
                      "missing_elements": missing_elements,
                      "status_forced_partial": forced,
                      "report": report_path}, ensure_ascii=False, indent=2))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
