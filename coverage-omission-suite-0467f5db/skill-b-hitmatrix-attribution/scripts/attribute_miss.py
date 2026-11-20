#!/usr/bin/env python3
"""attribute_miss.py — 漏检决策树探针归因（本技能签名能力）。

对 hit_matrix 复算出的每条漏检记录，依次执行五类可执行探针：
  (e) 记录异常探针  —— 撤稿/重复/标识符冲突 → RECORD_ANOMALY
  (d) 来源探针      —— 记录的标识符是否存在于任一来源的本地索引文件 → SOURCE_ABSENT
  (c) 时间窗探针    —— 记录存在于某来源索引，但查询 date_window 将其排除 → TIME_WINDOW
  (b) 字段探针      —— 放宽字段限制后可命中而原字段不可 → FIELD_RESTRICTION
  (a) 词汇探针      —— 漏检记录的实际词汇未被任何查询词覆盖 → VOCAB_GAP
全部探针均无法解释时记 UNDETERMINED，并保留全部探针证据，绝不编造类别。

每条漏检恰好一个主归因类别，附带 probe_evidence（文件/字段/引用片段）与
致漏的 query_id、字段、时间窗指针。

本地查询模拟语义（与 supplement_eval.py 一致）：
  查询词取 query_string 中长度 >= 3 的小写 token；命中当且仅当全部查询词出现
  在被检记录受检字段拼接文本中，且年份落入 date_window（若有）。

输入: work/case_normalized.json, work/coverage.json, work/adjudication.json
输出: work/miss_attribution.json, out/miss_attribution.csv

用法:
  python3 attribute_miss.py --work /app/work --out /app/output

退出码: 0 成功; 2 材料不足; 3 校验失败。
仅使用 Python 3 标准库。
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adjudicate import (match_pair, record_ids, title_tokens, get_year,  # noqa: E402
                        norm_doi, norm_pmid, norm_arxiv)

CATEGORIES = ("RECORD_ANOMALY", "SOURCE_ABSENT", "TIME_WINDOW",
              "FIELD_RESTRICTION", "VOCAB_GAP", "UNDETERMINED")

CONTENT_FIELDS = ("title", "abstract", "keywords", "venue")


def query_tokens(query_string):
    """查询词：长度 >= 3 的小写 token 集合。"""
    return {t for t in title_tokens(query_string) if len(t) >= 3}


def record_field_text(record, fields):
    """按字段范围拼接记录可检文本。"""
    if not fields or "any" in fields:
        fields = CONTENT_FIELDS + ("authors", "author")
    parts = []
    for f in fields:
        v = record.get(f)
        if isinstance(v, list):
            parts.append(" ".join(str(x if not isinstance(x, dict)
                                  else x.get("name", "")) for x in v))
        elif v is not None:
            parts.append(str(v))
    return " ".join(parts).lower()


def simulate_query(record, query_string, fields, date_window):
    """本地布尔模拟：全部查询词命中受检字段且年份在时间窗内。"""
    toks = query_tokens(query_string)
    text = record_field_text(record, fields)
    if toks and not all(t in text for t in toks):
        return False
    if date_window:
        y = get_year(record)
        lo, hi = date_window.get("from"), date_window.get("to")
        if y is None:
            return False
        if lo is not None and y < int(lo):
            return False
        if hi is not None and y > int(hi):
            return False
    return True


def snippet(text, needle_tokens, width=60):
    """生成证据引用片段：定位首个命中的 token，截取上下文。"""
    low = text.lower()
    pos = -1
    for t in needle_tokens:
        pos = low.find(t)
        if pos >= 0:
            break
    if pos < 0:
        return text[:width]
    start = max(0, pos - width // 2)
    return "…" + text[start:start + width] + "…"


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_index_records(work_dir, case):
    """加载各来源本地索引文件：{source: (path, [record])}。

    索引来源按优先级：case.extra.sources[].index_file；否则回退为各查询的
    results_file（同一来源多文件合并）。
    """
    extra = case.get("extra") or {}
    indexes = {}
    for s in (extra.get("sources") or []):
        src, idx = s.get("source"), s.get("index_file")
        if not src or not idx:
            continue
        data = load_json(idx)
        if isinstance(data, dict):
            data = data.get("records") or data.get("results") or []
        indexes[src] = (idx, data if isinstance(data, list) else [])
    for q in case.get("search_log", []):
        src = q.get("source")
        if src in indexes:
            continue
        data = load_json(q.get("results_file"))
        if isinstance(data, dict):
            data = data.get("records") or data.get("results") or []
        indexes.setdefault(src, (q.get("results_file"), data or []))
    return indexes


def find_in_indexes(ref, indexes):
    """在全部来源索引中定位参考记录。返回 (found_list, id_conflict_list)。"""
    found, conflicts = [], []
    ref_ids = record_ids(ref)
    ref_toks = title_tokens(ref.get("title"))
    for src, (path, records) in indexes.items():
        for rec in records:
            r = match_pair(ref, rec)
            if r["status"] == "hit":
                found.append({"source": src, "index_file": path, "record": rec,
                              "match": r})
            elif r["level"] == "L3" and "identifier_conflict" in (r["reason"] or ""):
                conflicts.append({"source": src, "index_file": path,
                                  "reason": r["reason"],
                                  "conflicting_title": rec.get("title")})
        # 标识符出现但标题完全不同（match_pair 未覆盖的边界：ref 无标题等）
        for rec in records:
            rec_ids = record_ids(rec)
            for k in ("doi", "pmid", "arxiv"):
                if ref_ids.get(k) and rec_ids.get(k) and ref_ids[k] == rec_ids[k]:
                    inter = len(ref_toks & title_tokens(rec.get("title")))
                    if ref_toks and inter == 0 and not any(
                            c["conflicting_title"] == rec.get("title") for c in conflicts):
                        conflicts.append({"source": src, "index_file": path,
                                          "reason": "id_equal_title_disjoint",
                                          "conflicting_title": rec.get("title")})
    return found, conflicts


def attribute_one(ref, queries, indexes, all_index_records):
    """对单条漏检执行决策树探针。返回归因记录 dict。"""
    evidence = []
    rid = ref.get("ref_id")

    # (e) 记录异常探针
    if ref.get("retracted"):
        return {"ref_id": rid, "primary_category": "RECORD_ANOMALY",
                "sub_reason": "retracted",
                "probe_evidence": [{"probe": "record_anomaly",
                                    "file": "case.reference_set",
                                    "field": "retracted",
                                    "snippet": "retracted=true"}],
                "query_id": None, "field": None, "date_window": None}
    if ref.get("duplicate_of"):
        return {"ref_id": rid, "primary_category": "RECORD_ANOMALY",
                "sub_reason": "duplicate",
                "probe_evidence": [{"probe": "record_anomaly",
                                    "file": "case.reference_set",
                                    "field": "duplicate_of",
                                    "snippet": str(ref.get("duplicate_of"))}],
                "query_id": None, "field": None, "date_window": None}

    found, conflicts = find_in_indexes(ref, indexes)

    if conflicts and not found:
        c = conflicts[0]
        return {"ref_id": rid, "primary_category": "RECORD_ANOMALY",
                "sub_reason": "identifier_conflict",
                "probe_evidence": [{"probe": "record_anomaly",
                                    "file": c["index_file"],
                                    "field": "doi/pmid/arxiv+title",
                                    "snippet": c["reason"]}],
                "query_id": None, "field": None, "date_window": None}
    evidence.append({"probe": "record_anomaly", "result": "no_anomaly"})

    # (d) 来源探针
    queried_sources = {q.get("source") for q in queries}
    if not found:
        ref_ids = record_ids(ref)
        id_desc = {k: v for k, v in ref_ids.items() if v}
        checked = [{"probe": "source", "file": path, "field": "doi/pmid/arxiv/venue",
                    "snippet": "来源 %s 索引 %d 条记录，无匹配标识符 %s"
                               % (src, len(recs), id_desc)}
                   for src, (path, recs) in indexes.items()]
        return {"ref_id": rid, "primary_category": "SOURCE_ABSENT",
                "sub_reason": "identifier_not_in_any_source_index",
                "probe_evidence": evidence + checked,
                "query_id": None, "field": None, "date_window": None}

    found_sources = sorted({f["source"] for f in found})
    if not (set(found_sources) & queried_sources):
        f0 = found[0]
        evidence.append({"probe": "source", "file": f0["index_file"],
                         "field": "identifier/title",
                         "snippet": "记录仅收录于来源 %s，而检索记录未覆盖该来源"
                                    % f0["source"]})
        return {"ref_id": rid, "primary_category": "SOURCE_ABSENT",
                "sub_reason": "record_indexed_only_in_unqueried_source",
                "probe_evidence": evidence,
                "query_id": None, "field": None, "date_window": None}

    hit0 = next(f for f in found if f["source"] in queried_sources)
    src, rec = hit0["source"], hit0["record"]
    evidence.append({"probe": "source", "file": hit0["index_file"],
                     "field": "identifier/title",
                     "snippet": "来源 %s 索引中存在该记录（%s）"
                                % (src, (hit0["match"] or {}).get("reason"))})

    src_queries = [q for q in queries if q.get("source") == src]
    ref_year = get_year(ref)

    # (c) 时间窗探针：对同来源查询，移除时间窗即可命中而保留时间窗不可命中 → 时间窗截断
    if ref_year is not None:
        for q in src_queries:
            qs = q.get("query_string") or ""
            fields = q.get("fields") or ["any"]
            dw = q.get("date_window")
            if not dw:
                continue
            if not simulate_query(rec, qs, fields, dw) and \
                    simulate_query(rec, qs, fields, None):
                evidence.append({"probe": "time_window",
                                 "file": hit0["index_file"],
                                 "field": "year",
                                 "snippet": "记录年份 %d 落在查询 %s 时间窗 %s 之外；"
                                            "移除时间窗后同一查询可命中"
                                            % (ref_year, q.get("query_id"), dw)})
                return {"ref_id": rid, "primary_category": "TIME_WINDOW",
                        "sub_reason": "window_removal_makes_query_hit",
                        "probe_evidence": evidence,
                        "query_id": q.get("query_id"), "field": "date_window",
                        "date_window": dw}

    # (b) 字段探针：放宽字段可命中而原字段不可
    for q in src_queries:
        qs = q.get("query_string") or ""
        fields = q.get("fields") or ["any"]
        dw = q.get("date_window")
        if not simulate_query(rec, qs, fields, dw) and \
                simulate_query(rec, qs, ["any"], dw):
            text = record_field_text(rec, ["any"])
            evidence.append({"probe": "field",
                             "file": hit0["index_file"],
                             "field": ",".join(fields),
                             "snippet": snippet(text, query_tokens(qs))})
            return {"ref_id": rid, "primary_category": "FIELD_RESTRICTION",
                    "sub_reason": "query_terms_match_only_in_unrestricted_fields",
                    "probe_evidence": evidence,
                    "query_id": q.get("query_id"),
                    "field": ",".join(fields),
                    "date_window": dw}

    # (a) 词汇探针：记录的实际词汇未被任何查询覆盖
    rec_text_tokens = title_tokens(record_field_text(rec, CONTENT_FIELDS))
    all_query_toks = set()
    for q in queries:
        all_query_toks |= query_tokens(q.get("query_string") or "")
    ref_content = {t for t in title_tokens(
        " ".join([str(ref.get("title") or ""),
                  " ".join(str(k) for k in (ref.get("keywords") or []))])) if len(t) >= 3}
    uncovered = sorted(t for t in (ref_content & rec_text_tokens)
                       if t not in all_query_toks)
    if uncovered:
        evidence.append({"probe": "vocab",
                         "file": hit0["index_file"],
                         "field": "title/keywords",
                         "snippet": "未被任何查询覆盖的词汇: %s"
                                    % ", ".join(uncovered[:10])})
        nearest = min(src_queries or queries,
                      key=lambda q: -len(query_tokens(q.get("query_string") or "")
                                         & rec_text_tokens)) if (src_queries or queries) else None
        return {"ref_id": rid, "primary_category": "VOCAB_GAP",
                "sub_reason": "record_vocabulary_not_covered_by_any_query",
                "probe_evidence": evidence,
                "uncovered_tokens": uncovered,
                "query_id": nearest.get("query_id") if nearest else None,
                "field": "query_string",
                "date_window": None}

    # 兜底：诚实标记
    evidence.append({"probe": "all", "result": "no_probe_explains_miss"})
    return {"ref_id": rid, "primary_category": "UNDETERMINED",
            "sub_reason": "record_in_index_but_no_probe_conclusive",
            "probe_evidence": evidence,
            "query_id": None, "field": None, "date_window": None}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="漏检决策树探针归因：词汇/字段/时间窗/来源/记录异常五类可执行探针。")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--out", default="/app/output", help="产物目录（默认 /app/output）")
    args = ap.parse_args(argv)

    case = load_json(os.path.join(args.work, "case_normalized.json"))
    coverage = load_json(os.path.join(args.work, "coverage.json"))
    if case is None or coverage is None:
        print("ERROR: 缺少 case_normalized.json 或 coverage.json，"
              "请先运行 parse_case.py / adjudicate.py / hit_matrix.py", file=sys.stderr)
        return 2

    missed_ids = coverage.get("missed_ref_ids") or []
    if not missed_ids:
        result = {"attributions": [], "note": "无漏检记录，覆盖率 100%"}
    else:
        ref_by_id = {r["ref_id"]: r for r in case.get("reference_set", [])}
        queries = case.get("search_log", [])
        indexes = load_index_records(args.work, case)
        all_index_records = [rec for _, recs in indexes.values() for rec in recs]
        attributions = []
        for rid in missed_ids:
            ref = ref_by_id.get(rid)
            if ref is None:
                attributions.append({"ref_id": rid,
                                     "primary_category": "UNDETERMINED",
                                     "sub_reason": "ref_id_not_in_reference_set",
                                     "probe_evidence": [],
                                     "query_id": None, "field": None,
                                     "date_window": None})
                continue
            attributions.append(attribute_one(ref, queries, indexes, all_index_records))
        result = {"attributions": attributions,
                  "category_counts": {c: sum(1 for a in attributions
                                             if a["primary_category"] == c)
                                      for c in CATEGORIES}}

    work_path = os.path.join(args.work, "miss_attribution.json")
    with open(work_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "miss_attribution.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref_id", "primary_category", "sub_reason", "query_id",
                    "field", "date_window", "evidence_file", "evidence_field",
                    "evidence_snippet"])
        for a in result["attributions"]:
            ev = (a.get("probe_evidence") or [{}])[-1]
            w.writerow([a["ref_id"], a["primary_category"], a.get("sub_reason"),
                        a.get("query_id"), a.get("field"),
                        json.dumps(a.get("date_window"), ensure_ascii=False)
                        if a.get("date_window") else "",
                        ev.get("file", ""), ev.get("field", ""), ev.get("snippet", "")])

    counts = result.get("category_counts", {})
    print("attribute_miss: %d 条漏检已归因: %s"
          % (len(result["attributions"]),
             ", ".join("%s=%d" % (k, v) for k, v in counts.items() if v)))
    print("输出: %s ; %s" % (work_path, csv_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
