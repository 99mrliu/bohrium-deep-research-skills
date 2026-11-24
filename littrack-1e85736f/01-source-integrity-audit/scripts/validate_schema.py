#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_schema.py — 题录 Schema 校验（schema_report.json）。

对每条题录校验必备字段的存在性与类型：
  * title    ：必须存在且为 str（空字符串的标题由 detect_anomalies 另行标记）；
  * authors  ：必须存在、为 list 且非空；
  * 日期字段 ：published/date/issued/publication_date/... 至少存在一个；
  * 标识符   ：doi/arxiv_id/pmid/record_id/... 至少存在一个。

历史快照（文件名形如 *_v1.json / *_v2.json）不参与逐条校验，仅用于漂移检测。
无法抽取出题录列表的文件标记为 skipped，不计入失败率。

用法：
    python3 validate_schema.py --materials <材料目录> --out <schema_report.json>
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

REQUIRED_SPEC = {
    "title": "必须存在且为 str",
    "authors": "必须存在、为 list 且非空",
    "date": "published/date/issued/publication_date 至少一个",
    "identifier": "doi/arxiv_id/pmid/record_id 至少一个",
}


def validate_record(record):
    violations = []
    if not isinstance(record, dict):
        return ["record_not_an_object"]
    title = record.get("title")
    if title is None:
        violations.append("title_missing")
    elif not isinstance(title, str):
        violations.append("title_wrong_type")
    authors = record.get("authors")
    if authors is None:
        violations.append("authors_missing")
    elif not isinstance(authors, list):
        violations.append("authors_wrong_type")
    elif len(authors) == 0:
        violations.append("authors_empty")
    _value, date_field = common.get_date_value(record)
    if date_field is None:
        violations.append("date_field_missing")
    if not common.get_identifiers(record):
        violations.append("identifier_missing")
    return violations


def build_report(materials_dir):
    files = []
    total_records = 0
    failed_records = 0
    for path in common.iter_material_files(materials_dir):
        entry = {"path": path, "skipped": False, "skip_reason": None,
                 "record_count": 0, "failed_count": 0, "failures": []}
        if common.is_versioned_snapshot(path):
            entry["skipped"] = True
            entry["skip_reason"] = "versioned_snapshot（历史快照，仅用于漂移检测）"
            files.append(entry)
            continue
        try:
            data = common.load_json(path)
        except Exception as exc:  # 解析失败交给台账与 gating 处理
            entry["skipped"] = True
            entry["skip_reason"] = "parse_error: %s: %s" % (type(exc).__name__, exc)
            files.append(entry)
            continue
        records, base_ptr = common.extract_records(data)
        if records is None:
            entry["skipped"] = True
            entry["skip_reason"] = "no_records_found（非题录源文件，如增量导入状态快照）"
            files.append(entry)
            continue
        entry["record_count"] = len(records)
        total_records += len(records)
        for idx, record in enumerate(records):
            violations = validate_record(record)
            if violations:
                failed_records += 1
                entry["failed_count"] += 1
                ids = common.get_identifiers(record)
                entry["failures"].append({
                    "locator": path + base_ptr + "/" + str(idx),
                    "index": idx,
                    "record_id": ids.get("record_id") or ids.get("id"),
                    "violations": violations,
                })
        files.append(entry)
    rate = (failed_records / total_records) if total_records else 0.0
    return {
        "generated_by": "validate_schema.py",
        "required_fields": REQUIRED_SPEC,
        "total_records": total_records,
        "failed_records": failed_records,
        "failure_rate": round(rate, 6),
        "files": files,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="题录 Schema 校验")
    parser.add_argument("--materials", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not os.path.isdir(args.materials):
        print("ERROR: 材料目录不存在: %s" % args.materials, file=sys.stderr)
        return 2
    report = build_report(args.materials)
    common.dump_json(report, args.out)
    print("validate_schema: 共 %d 条题录, %d 条未通过 (%.1f%%) -> %s"
          % (report["total_records"], report["failed_records"],
             report["failure_rate"] * 100, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
