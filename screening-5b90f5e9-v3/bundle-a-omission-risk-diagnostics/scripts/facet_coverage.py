#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""facet_coverage.py — 主题面覆盖核查（facet coverage）。

将研究问题分解得到的 facets（来自 case.json）与纳入集比对：
  - 对每个 facet，用其 keywords 在纳入记录的标题+摘要中做大小写不敏感子串匹配；
  - 命中数（命中纳入记录条数）为 0 的 facet 置 zero_inclusion_alarm：
    这不证明该主题面真为空，而是提示“可能是检索或筛选环节遗漏”（须人工回查）。
  - 本技能只有限快照，不做也不声称全局召回判断。

产物：work/facet_coverage.json；增量填充 result.json 的 facet_coverage 字段。
退出码：0=通过；2=facets/records/judgments 不足（诚实降级，写 skipped 段）；3=校验失败。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

EXIT_OK, EXIT_INSUFFICIENT, EXIT_INVALID = 0, 2, 3


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_material(input_dir, case, key, fallbacks):
    cands = []
    mats = (case or {}).get("materials") or {}
    if mats.get(key):
        cands.append(os.path.join(input_dir, mats[key]))
    cands.extend(os.path.join(input_dir, name) for name in fallbacks)
    for path in cands:
        if os.path.exists(path):
            return path
    return None


def load_judgments(path):
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError("judgments 文件结构不识别")


def load_records(path):
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    raise ValueError("records 文件结构不识别")


def ensure_result(result_path, case_id):
    if os.path.exists(result_path):
        return load_json(result_path)
    return {"case_id": case_id, "status": "partial",
            "sources": [], "uncertainty": [], "change_records": []}


def add_source(result, path, role):
    entry = {"path": path, "sha256": sha256_of(path), "role": role}
    sources = [s for s in (result.get("sources") or []) if s.get("path") != path]
    sources.append(entry)
    result["sources"] = sources


def add_uncertainty(result, note):
    unc = result.get("uncertainty") or []
    if note not in unc:
        unc.append(note)
    result["uncertainty"] = unc


def degrade(result, result_path, note):
    result["facet_coverage"] = {"status": "skipped", "reason": note}
    add_uncertainty(result, note)
    result["change_records"].append({
        "ts": utcnow(), "action": "facet_coverage: degraded", "files": [result_path]})
    save_json(result_path, result)
    print("facet_coverage 降级：%s" % note, file=sys.stderr)
    return EXIT_INSUFFICIENT


def main():
    ap = argparse.ArgumentParser(description="主题面覆盖核查")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    try:
        os.makedirs(args.work, exist_ok=True)
        os.makedirs(args.output_dir, exist_ok=True)
        result_path = os.path.join(args.output_dir, "result.json")
        case_path = os.path.join(args.input_dir, "case.json")
        if not os.path.exists(case_path):
            result = ensure_result(result_path, None)
            return degrade(result, result_path,
                           "case.json 缺失，无法获得研究问题 facets。")
        case = load_json(case_path)
        result = ensure_result(result_path, case.get("case_id"))

        facets = case.get("facets")
        if not facets:
            return degrade(result, result_path,
                           "case.json 未提供 facets 分解；无法执行主题面覆盖核查，"
                           "需人工补充 facet 定义后重跑。")

        records_path = find_material(args.input_dir, case, "records",
                                     ["records.json"])
        if not records_path:
            return degrade(result, result_path,
                           "records 题录文件缺失，无法做 facet 关键词匹配。")
        judgments_path = find_material(args.input_dir, case, "judgments",
                                       ["judgments.json", "decisions.json"])
        if not judgments_path:
            return degrade(result, result_path,
                           "judgments 缺失，无法确定纳入集。")

        try:
            records = {r.get("record_id"): r for r in load_records(records_path)}
            judgments = load_judgments(judgments_path)
        except (ValueError, json.JSONDecodeError) as e:
            print("输入校验失败: %s" % e, file=sys.stderr)
            return EXIT_INVALID

        included_ids = [it.get("record_id") for it in judgments
                        if it.get("decision") == "include"]
        facet_rows, alarms = [], []
        for facet in facets:
            fid = facet.get("facet_id")
            keywords = [str(k).lower() for k in (facet.get("keywords") or [])]
            hits = []
            for rid in included_ids:
                rec = records.get(rid) or {}
                text = ((rec.get("title") or "") + " " +
                        (rec.get("abstract") or "")).lower()
                matched = [k for k in keywords if k in text]
                if matched:
                    hits.append({"record_id": rid, "matched_keywords": matched})
            row = {
                "facet_id": fid,
                "label": facet.get("label"),
                "included_hits": len(hits),
                "matched_records": hits,
                "status": "ok" if hits else "zero_inclusion_alarm",
            }
            facet_rows.append(row)
            if not hits:
                alarms.append({
                    "facet_id": fid,
                    "label": facet.get("label"),
                    "alarm": "zero_inclusion_alarm",
                    "interpretation":
                        "纳入集在该主题面命中为 0。本快照无法区分“检索遗漏”“筛选过严”"
                        "与“该面真空”；须人工回查检索式与排除理由后方可定性。",
                })

        report = {
            "generated_by": "facet_coverage.py v1.0.0",
            "status": "completed",
            "included_total": len(included_ids),
            "facets": facet_rows,
            "alarms": alarms,
            "note": "覆盖核查基于题录关键词匹配，语义覆盖有限；不构成全局召回声明。",
        }
        out_path = os.path.join(args.work, "facet_coverage.json")
        save_json(out_path, report)

        result["facet_coverage"] = report
        add_source(result, records_path, "records")
        add_source(result, judgments_path, "judgments")
        result["change_records"].append({
            "ts": utcnow(),
            "action": "facet_coverage: facets=%d alarms=%d" % (len(facets), len(alarms)),
            "files": [out_path, result_path]})
        save_json(result_path, result)
        print("facet 覆盖核查完成：%d 个 facet，%d 个零纳入报警" % (
            len(facets), len(alarms)))
        return EXIT_OK
    except Exception as e:
        print("facet_coverage 未预期失败: %s" % e, file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
