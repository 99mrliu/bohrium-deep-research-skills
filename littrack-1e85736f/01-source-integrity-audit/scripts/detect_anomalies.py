#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detect_anomalies.py — 元数据一致性校验与异常检测（anomaly_report.json）。

检测项（详见 references/anomaly-taxonomy.md）：
  invalid_doi / invalid_arxiv / invalid_pmid      标识符格式非法
  future_date / invalid_date / missing_date       日期异常（以窗口终点为"现在"）
  empty_title                                     空标题
  retraction_flag / correction_flag               撤稿 / 更正标记
  duplicate_in_source                             源内重复条目
  schema_drift                                    同源 v1/v2 快照结构漂移
  source_record_disappeared                       增量导入状态中已导入、当前源快照消失

用法：
    python3 detect_anomalies.py --materials <材料目录> \
        --window-end YYYY-MM-DD [--window-start YYYY-MM-DD] \
        [--previous previous_snapshot.json] --out anomaly_report.json
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

SEVERITY = {
    "invalid_doi": "high",
    "future_date": "high",
    "retraction_flag": "high",
    "source_record_disappeared": "high",
    "duplicate_in_source": "medium",
    "invalid_pmid": "medium",
    "invalid_arxiv": "medium",
    "correction_flag": "medium",
    "schema_drift": "medium",
    "missing_date": "low",
    "invalid_date": "low",
    "empty_title": "low",
}

RETRACTION_TITLE_PREFIXES = (
    "retracted article", "retracted:", "retraction:", "retraction notice",
    "retraction note",
)
CORRECTION_TITLE_PREFIXES = (
    "correction:", "corrigendum", "erratum", "correction notice",
    "author correction", "publisher correction",
)


def _mk(atype, locator, detail, evidence=None, record_locator=None):
    item = {
        "type": atype,
        "severity": SEVERITY.get(atype, "medium"),
        "locator": locator,
        "detail": detail,
        "evidence": evidence,
    }
    if record_locator is not None:
        item["record_locator"] = record_locator
    return item


def check_record(record, record_locator, path, window_end):
    """单条题录的元数据一致性检查，返回异常列表。"""
    out = []
    if not isinstance(record, dict):
        out.append(_mk("invalid_date", record_locator,
                       "题录不是 JSON 对象，无法执行元数据校验"))
        return out
    ids = common.get_identifiers(record)

    doi = ids.get("doi")
    if doi and not common.valid_doi(doi):
        out.append(_mk("invalid_doi",
                       record_locator + "/doi",
                       "DOI 不符合语法 ^10\\.\\d{4,9}/\\S+$",
                       evidence=doi, record_locator=record_locator))

    arxiv = ids.get("arxiv_id") or ids.get("arxiv") or ids.get("eprint")
    if arxiv and not common.valid_arxiv(arxiv):
        out.append(_mk("invalid_arxiv",
                       record_locator + "/arxiv_id",
                       "arXiv 号不符合新格式 YYMM.NNNNN(vN) 或旧格式 arch/NNNNNNN",
                       evidence=arxiv, record_locator=record_locator))

    pmid = ids.get("pmid")
    if pmid and not common.valid_pmid(pmid):
        out.append(_mk("invalid_pmid",
                       record_locator + "/pmid",
                       "PMID 应为纯数字",
                       evidence=pmid, record_locator=record_locator))

    title = record.get("title")
    if isinstance(title, str) and not title.strip():
        out.append(_mk("empty_title",
                       record_locator + "/title",
                       "标题为空字符串",
                       evidence=title, record_locator=record_locator))

    raw_date, date_field = common.get_date_value(record)
    if date_field is None:
        out.append(_mk("missing_date",
                       record_locator,
                       "无任何日期字段（published/date/issued/...）",
                       record_locator=record_locator))
    else:
        parsed = common.parse_date(raw_date)
        if parsed is None:
            out.append(_mk("invalid_date",
                           record_locator + "/" + date_field,
                           "日期值无法解析",
                           evidence=raw_date, record_locator=record_locator))
        elif window_end is not None and parsed > window_end:
            out.append(_mk(
                "future_date",
                record_locator + "/" + date_field,
                "日期 %s 晚于窗口终点 %s（以窗口终点为'现在'，属未来日期）"
                % (parsed.isoformat(), window_end.isoformat()),
                evidence=str(raw_date), record_locator=record_locator))

    # 撤稿 / 更正标记
    is_retraction = False
    is_correction = False
    evidences = []
    if record.get("retracted") is True:
        is_retraction = True
        evidences.append({"field": "retracted", "value": True})
    if record.get("retraction"):
        is_retraction = True
        evidences.append({"field": "retraction", "value": record.get("retraction")})
    relation = record.get("relation")
    if isinstance(relation, dict):
        for key, val in relation.items():
            kl = str(key).lower()
            if "retraction" in kl:
                is_retraction = True
                evidences.append({"field": "relation." + str(key), "value": val})
            elif "correction" in kl or "erratum" in kl:
                is_correction = True
                evidences.append({"field": "relation." + str(key), "value": val})
    flags = record.get("flags")
    if isinstance(flags, list):
        for flag in flags:
            fl = str(flag).lower()
            if "retract" in fl:
                is_retraction = True
                evidences.append({"field": "flags", "value": flag})
            elif "correct" in fl or "erratum" in fl:
                is_correction = True
                evidences.append({"field": "flags", "value": flag})
    update_type = record.get("update-type") or record.get("update_type")
    if isinstance(update_type, str):
        if "retraction" in update_type.lower():
            is_retraction = True
            evidences.append({"field": "update-type", "value": update_type})
    if isinstance(title, str):
        tl = title.lower()
        if any(tl.startswith(p) for p in RETRACTION_TITLE_PREFIXES):
            is_retraction = True
            evidences.append({"field": "title", "value": title})
        elif any(tl.startswith(p) for p in CORRECTION_TITLE_PREFIXES):
            is_correction = True
            evidences.append({"field": "title", "value": title})
    if is_retraction:
        out.append(_mk("retraction_flag", record_locator,
                       "检测到撤稿标记（字段/关系/标题前缀）",
                       evidence=evidences, record_locator=record_locator))
    elif is_correction:
        out.append(_mk("correction_flag", record_locator,
                       "检测到更正/勘误标记（字段/关系/标题前缀）",
                       evidence=evidences, record_locator=record_locator))
    return out


def detect_duplicates(records, base_ptr, path):
    """源内重复：优先按规范化 DOI，其次按规范化标题。"""
    seen = {}
    out = []
    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        ids = common.get_identifiers(record)
        key = None
        key_kind = None
        doi = ids.get("doi")
        if doi:
            key = "doi:" + common.normalize_doi(doi)
            key_kind = "doi"
        else:
            nt = common.normalize_title(record.get("title"))
            if nt:
                key = "title:" + nt
                key_kind = "title"
        if key is None:
            continue
        if key in seen:
            first_idx = seen[key]
            out.append(_mk(
                "duplicate_in_source",
                path + base_ptr + "/" + str(idx),
                "与同源第 %d 条题录重复（按 %s 匹配）" % (first_idx, key_kind),
                evidence={"match_key_kind": key_kind,
                          "first_occurrence": path + base_ptr + "/" + str(first_idx)},
                record_locator=path + base_ptr + "/" + str(idx)))
        else:
            seen[key] = idx
    return out


def detect_drift(materials_dir):
    """同源 v1/v2（及更高版本）快照的结构漂移检测：比较顶层键与题录键集合。"""
    groups = {}
    for path in common.iter_material_files(materials_dir):
        m = common.SNAPSHOT_VERSION_RE.match(os.path.basename(path))
        if m:
            groups.setdefault(m.group(1), []).append((int(m.group(2)), path))
    out = []
    for prefix, versions in sorted(groups.items()):
        versions.sort()
        for (v1, p1), (v2, p2) in zip(versions, versions[1:]):
            try:
                d1 = common.load_json(p1)
                d2 = common.load_json(p2)
            except Exception as exc:
                out.append(_mk("schema_drift", p2 + "#",
                               "快照解析失败，无法对比: %s" % exc))
                continue
            r1, _b1 = common.extract_records(d1)
            r2, _b2 = common.extract_records(d2)
            r1 = r1 or []
            r2 = r2 or []
            keys1 = set()
            for r in r1:
                if isinstance(r, dict):
                    keys1.update(r.keys())
            keys2 = set()
            for r in r2:
                if isinstance(r, dict):
                    keys2.update(r.keys())
            top1 = set(d1.keys()) if isinstance(d1, dict) else set()
            top2 = set(d2.keys()) if isinstance(d2, dict) else set()
            added = sorted(keys2 - keys1)
            removed = sorted(keys1 - keys2)
            top_added = sorted(top2 - top1)
            top_removed = sorted(top1 - top2)
            if added or removed or top_added or top_removed:
                out.append(_mk(
                    "schema_drift", p2 + "#",
                    "源 '%s' v%d -> v%d 快照结构漂移：题录字段新增 %s、消失 %s"
                    % (prefix, v1, v2, added or "[]", removed or "[]"),
                    evidence={
                        "base_snapshot": p1,
                        "compared_snapshot": p2,
                        "record_fields_added": added,
                        "record_fields_removed": removed,
                        "top_level_fields_added": top_added,
                        "top_level_fields_removed": top_removed,
                    }))
    return out


def compare_previous(prev_path, current_ids, current_count):
    """与本地增量导入状态对比：已导入记录是否仍存在于当前源快照。"""
    anomalies = []
    info = {
        "path": prev_path,
        "taken_at": None,
        "imported_count": 0,
        "still_present": 0,
        "disappeared_count": 0,
        "disappeared": [],
        "current_record_count": current_count,
        "new_record_count": None,
    }
    try:
        data = common.load_json(prev_path)
    except Exception as exc:
        anomalies.append(_mk("source_record_disappeared", prev_path + "#",
                             "增量导入状态文件无法解析: %s" % exc))
        return anomalies, info
    info["taken_at"] = data.get("taken_at") if isinstance(data, dict) else None
    imported = data.get("imported") if isinstance(data, dict) else None
    if not isinstance(imported, list):
        imported = []
    info["imported_count"] = len(imported)
    for i, entry in enumerate(imported):
        ids = common.get_identifiers(entry)
        keys = set()
        if ids.get("doi"):
            keys.add("doi:" + common.normalize_doi(ids["doi"]))
        if ids.get("pmid"):
            keys.add("pmid:" + ids["pmid"])
        if ids.get("record_id") or ids.get("id"):
            keys.add("record_id:" + (ids.get("record_id") or ids.get("id")))
        if keys and (keys & current_ids):
            info["still_present"] += 1
        else:
            info["disappeared"].append({
                "locator": prev_path + common.json_pointer("imported", i),
                "imported_entry": entry,
            })
            anomalies.append(_mk(
                "source_record_disappeared",
                prev_path + common.json_pointer("imported", i),
                "该记录此前已导入本地，但当前源快照中不存在（上游删除/改版迹象）",
                evidence=entry))
    info["disappeared_count"] = len(info["disappeared"])
    info["new_record_count"] = current_count - info["still_present"]
    return anomalies, info


def build_report(materials_dir, window_start, window_end, previous_path):
    anomalies = []
    current_ids = set()
    total_records = 0

    for path in common.iter_material_files(materials_dir):
        if common.is_versioned_snapshot(path):
            continue  # 历史快照只做漂移对比
        try:
            data = common.load_json(path)
        except Exception:
            continue  # 解析失败由台账/gating 处理
        records, base_ptr = common.extract_records(data)
        if records is None:
            continue  # 非题录文件（如 previous_snapshot.json）
        total_records += len(records)
        for idx, record in enumerate(records):
            if isinstance(record, dict):
                ids = common.get_identifiers(record)
                if ids.get("doi"):
                    current_ids.add("doi:" + common.normalize_doi(ids["doi"]))
                if ids.get("pmid"):
                    current_ids.add("pmid:" + ids["pmid"])
                if ids.get("record_id") or ids.get("id"):
                    current_ids.add(
                        "record_id:" + (ids.get("record_id") or ids.get("id")))
            record_locator = path + base_ptr + "/" + str(idx)
            anomalies.extend(
                check_record(record, record_locator, path, window_end))
        anomalies.extend(detect_duplicates(records, base_ptr, path))

    anomalies.extend(detect_drift(materials_dir))

    prev_info = None
    if previous_path:
        if os.path.isfile(previous_path):
            prev_anoms, prev_info = compare_previous(
                previous_path, current_ids, total_records)
            anomalies.extend(prev_anoms)
        else:
            anomalies.append(_mk(
                "source_record_disappeared", previous_path + "#",
                "指定的增量导入状态文件不存在: %s" % previous_path))

    by_type = {}
    by_severity = {}
    for a in anomalies:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
        by_severity[a["severity"]] = by_severity.get(a["severity"], 0) + 1
    return {
        "generated_by": "detect_anomalies.py",
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
        "now_reference": "window_end（按规则以 case.json 窗口终点为'现在'）",
        "total_records": total_records,
        "anomaly_count": len(anomalies),
        "by_type": by_type,
        "by_severity": by_severity,
        "anomalies": anomalies,
        "previous_snapshot": prev_info,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="元数据一致性与异常检测")
    parser.add_argument("--materials", required=True)
    parser.add_argument("--window-end", required=True,
                        help="窗口终点 YYYY-MM-DD，作为'现在'判定未来日期")
    parser.add_argument("--window-start", default=None)
    parser.add_argument("--previous", default=None,
                        help="本地增量导入状态快照路径；缺省自动探测 "
                             "<materials>/previous_snapshot.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if not os.path.isdir(args.materials):
        print("ERROR: 材料目录不存在: %s" % args.materials, file=sys.stderr)
        return 2
    window_end = common.parse_date(args.window_end)
    if window_end is None:
        print("ERROR: --window-end 无法解析: %s" % args.window_end,
              file=sys.stderr)
        return 2
    window_start = (common.parse_date(args.window_start)
                    if args.window_start else None)
    previous = args.previous
    if previous is None:
        candidate = os.path.join(args.materials, "previous_snapshot.json")
        if os.path.isfile(candidate):
            previous = candidate

    report = build_report(args.materials, window_start, window_end, previous)
    common.dump_json(report, args.out)
    print("detect_anomalies: 共 %d 条题录, 检出 %d 个异常 (%s) -> %s"
          % (report["total_records"], report["anomaly_count"],
             report["by_type"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
