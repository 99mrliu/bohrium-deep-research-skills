#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""query_log.py — 查询台账与编排审计：每个来源库“实际执行的查询”以材料记录为准。

三档来源（按优先级合并，绝不臆造查询字符串）：
  1) 组织方已记录的查询台账材料（sniff=query_ledger，逐行 JSON）——逐条收录；
  2) 原始响应内嵌的请求信息（Crossref message.query / EuropePMC request）——补录；
  3) 两档均无的库——记 query_unrecorded=true，如实说明，绝不编造。

产出（--work 目录下）：
  query_ledger.jsonl   每行 {query_id, source_db, query_text, params, recorded_at,
                       total_hits, items_returned, page, response_file, notes,
                       provenance}
  query_audit.json     编排审计：
    - mechanical_copy：各库查询串逐库两两 diff（SequenceMatcher 相似度 + 词项差异）
    - pagination：items_returned 求和 vs total_hits 分页完整性（不吻合→
      suspected_truncation，并估算缺失区间）
    - rate_limit：限流/配额痕迹分类（observed / not_recorded，附命中模式）

退出码：0=成功（允许警告）；2=summary 缺失或无任何响应类材料（诚实降级）；
3=summary 非法（校验失败）。顶层未捕获异常汇总并以 exit 2 降级，绝不 crash。

用法：
  python3 query_log.py [--summary /app/work/case_summary.json]
      [--work /app/work] [--ledger-out query_ledger.jsonl] [--audit-out query_audit.json]
"""
import argparse
import difflib
import json
import os
import re
import sys
from itertools import combinations

# 响应类材料：unknown 文件已由 parse_case 的 unparsed_files 留痕，不再为其
# 臆造查询台账条目（台账只对可识别为响应容器的库建账）。
RESPONSE_SNIFFS = {"crossref", "europepmc", "publisher", "recordlist",
                   "jsonl", "csv"}

RATE_PATTERNS = [
    ("http_429", re.compile(r"\b429\b")),
    ("rate_limit", re.compile(r"rate[ _-]?limit", re.I)),
    ("x_ratelimit_header", re.compile(r"x-?ratelimit", re.I)),
    ("quota", re.compile(r"\bquota\b", re.I)),
    ("retry_after", re.compile(r"retry-?after", re.I)),
    ("throttling", re.compile(r"throttl", re.I)),
]

DEFAULT_ENTRY_KEYS = ["query_id", "source_db", "query_text", "params",
                      "recorded_at", "total_hits", "items_returned", "page",
                      "response_file", "notes", "provenance"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def db_name(sniff):
    return sniff if sniff in ("crossref", "europepmc", "publisher") else sniff


def embedded_request_info(path, sniff):
    """从原始响应中提取内嵌请求信息（材料记录为准）。失败返回 None。"""
    try:
        obj = load_json(path)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    info = {}
    if sniff == "crossref":
        msg = obj.get("message")
        if not isinstance(msg, dict):
            return None
        q = msg.get("query")
        q = q if isinstance(q, dict) else {}
        text = q.get("search-terms")
        if text is None and q:
            text = json.dumps(q, ensure_ascii=False, sort_keys=True)
        info["query_text"] = text
        info["params"] = dict(q)
        info["total_hits"] = msg.get("total-results")
        items = msg.get("items")
        info["items_returned"] = len(items) if isinstance(items, list) else (
            1 if isinstance(msg, dict) and ("DOI" in msg or "title" in msg) else None)
        info["page"] = {"rows": msg.get("items-per-page"),
                        "offset": q.get("start-index")}
    elif sniff == "europepmc":
        req = obj.get("request")
        if not isinstance(req, dict):
            return None
        info["query_text"] = req.get("query")
        info["params"] = dict(req)
        info["total_hits"] = obj.get("hitCount")
        rl = obj.get("resultList")
        res = rl.get("result") if isinstance(rl, dict) else None
        info["items_returned"] = len(res) if isinstance(res, list) else None
        info["page"] = {"rows": req.get("pageSize"), "offset": None,
                        "cursor": req.get("cursorMark")}
    else:
        # 通用启发：顶层 query/request/meta 键；仅当材料自己记录了才采用
        for k in ("request", "query", "meta"):
            v = obj.get(k)
            if isinstance(v, dict) and v:
                info["params"] = dict(v)
                info["query_text"] = v.get("query") or v.get("search") or \
                    json.dumps(v, ensure_ascii=False, sort_keys=True)
                break
        for k in ("total_hits", "totalHits", "total_results", "total-results",
                  "hitCount", "count"):
            if isinstance(obj.get(k), int):
                info["total_hits"] = obj[k]
                break
    return info if info else None


def normalize_organizer_entry(raw, seq):
    e = {k: raw.get(k) for k in DEFAULT_ENTRY_KEYS}
    e["source_db"] = str(raw.get("source_db") or raw.get("db") or "unknown_db")
    if not e.get("query_id"):
        e["query_id"] = "Q-ORG-%03d" % seq
    if e.get("params") is None:
        e["params"] = {}
    if e.get("notes") is None:
        e["notes"] = []
    elif isinstance(e["notes"], str):
        e["notes"] = [e["notes"]]
    e["provenance"] = "organizer_ledger"
    return e


def audit_mechanical_copy(entries):
    texts = {}
    for e in entries:
        t = e.get("query_text")
        if t:
            texts.setdefault(e.get("source_db"), []).append(str(t))
    pairwise = []
    worst = None
    for a, b in sorted(combinations(sorted(texts), 2)):
        ta, tb = texts[a][0], texts[b][0]
        ratio = difflib.SequenceMatcher(None, ta, tb).ratio()
        toks_a, toks_b = set(re.findall(r"\w+", ta.lower())), \
            set(re.findall(r"\w+", tb.lower()))
        diff = sorted(toks_a ^ toks_b)
        pairwise.append({"db_a": a, "db_b": b, "similarity": round(ratio, 4),
                         "differing_tokens": diff[:50]})
        worst = ratio if worst is None else max(worst, ratio)
    if not pairwise:
        verdict = "insufficient_data（无两库均记录的查询可比）"
    elif worst >= 0.98:
        verdict = "mechanical_copy_confirmed（各库查询串几乎一致，疑似机械复制）"
    elif worst >= 0.80:
        verdict = "partial_overlap（部分重叠，需人工确认语法适配）"
    else:
        verdict = "adapted（各库查询按方言分别构造，未见机械复制）"
    return {"pairwise": pairwise, "verdict": verdict,
            "dbs_with_recorded_query": sorted(texts)}


def audit_pagination(entries):
    by_db = {}
    for e in entries:
        by_db.setdefault(e.get("source_db"), []).append(e)
    out = []
    for db in sorted(by_db):
        es = by_db[db]
        returned = [e.get("items_returned") for e in es
                    if isinstance(e.get("items_returned"), int)]
        totals = [e.get("total_hits") for e in es
                  if isinstance(e.get("total_hits"), int)]
        total = max(totals) if totals else None
        s = sum(returned)
        pages = len(returned)
        if total is None:
            status, missing = "unknown", None
        elif s >= total:
            status, missing = "complete", None
        else:
            status = "suspected_truncation"
            missing = {"returned_sum": s, "total_hits": total,
                       "estimated_missing_range": [s, total - 1]}
        out.append({"source_db": db, "pages": pages, "returned_sum": s,
                    "total_hits": total, "status": status,
                    "query_unrecorded": all(e.get("query_unrecorded")
                                            for e in es),
                    "missing": missing})
    return out


def audit_rate_limit(summary, materials_by_path):
    out = {}
    for m in summary.get("materials") or []:
        if m.get("sniff") not in RESPONSE_SNIFFS:
            continue
        db = db_name(m.get("sniff"))
        hit = []
        try:
            text = read_text(m.get("path"))
        except OSError:
            text = ""
        for name, pat in RATE_PATTERNS:
            if pat.search(text):
                hit.append(name)
        out.setdefault(db, set()).update(hit)
    return {db: {"classification": "observed" if v else "not_recorded",
                 "matched_patterns": sorted(v)}
            for db, v in sorted(out.items())}


def main_inner(args):
    if not os.path.isfile(args.summary):
        print("ERROR: case_summary 不存在（材料不足）: %s；请先运行 parse_case.py。"
              % args.summary, file=sys.stderr)
        return 2
    try:
        summary = load_json(args.summary)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary 非法（校验失败）: %s" % e, file=sys.stderr)
        return 3

    materials = summary.get("materials") or []
    responses = [m for m in materials if m.get("sniff") in RESPONSE_SNIFFS]
    if not responses:
        print("ERROR: 无任何响应类材料（crossref/europepmc/publisher/...），"
              "无法建立查询台账，诚实降级。", file=sys.stderr)
        return 2

    entries, seq = [], 0
    ql_path = summary.get("query_ledger_material")
    if ql_path and os.path.isfile(ql_path):
        for ln in read_text(ql_path).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                raw = json.loads(ln)
            except json.JSONDecodeError as e:
                print("WARN: 组织方台账行解析失败，跳过留痕: %s (%s)"
                      % (e, ln[:80]), file=sys.stderr)
                continue
            if not isinstance(raw, dict):
                continue
            seq += 1
            entries.append(normalize_organizer_entry(raw, seq))

    covered = {os.path.basename(str(e.get("response_file") or ""))
               for e in entries if e.get("response_file")}
    for m in sorted(responses, key=lambda x: x.get("file") or ""):
        base = m.get("file") or ""
        if base in covered:
            continue
        info = embedded_request_info(m.get("path"), m.get("sniff"))
        seq += 1
        if info and info.get("query_text"):
            entries.append({
                "query_id": "Q-EMB-%03d" % seq,
                "source_db": db_name(m.get("sniff")),
                "query_text": info.get("query_text"),
                "params": info.get("params") or {},
                "recorded_at": None,
                "total_hits": info.get("total_hits"),
                "items_returned": info.get("items_returned"),
                "page": info.get("page"),
                "response_file": base,
                "notes": ["由响应内嵌请求信息补录；材料未提供 recorded_at"],
                "provenance": "embedded_request",
            })
        else:
            entries.append({
                "query_id": "Q-UNR-%03d" % seq,
                "source_db": db_name(m.get("sniff")),
                "query_text": None,
                "params": {},
                "recorded_at": None,
                "total_hits": None,
                "items_returned": m.get("item_count"),
                "page": None,
                "response_file": base,
                "notes": ["query_unrecorded: 材料未记录该库的查询参数，"
                          "不得臆造；请如实写入 uncertainty"],
                "query_unrecorded": True,
                "provenance": "query_unrecorded",
            })

    audit = {
        "mechanical_copy": audit_mechanical_copy(entries),
        "pagination": audit_pagination(entries),
        "rate_limit": audit_rate_limit(summary, materials),
    }
    unrecorded = [e["source_db"] for e in entries if e.get("query_unrecorded")]

    os.makedirs(args.work, exist_ok=True)
    ledger_out = args.ledger_out or os.path.join(args.work, "query_ledger.jsonl")
    audit_out = args.audit_out or os.path.join(args.work, "query_audit.json")
    with open(ledger_out, "w", encoding="utf-8") as f:
        for e in sorted(entries, key=lambda x: (x.get("source_db") or "",
                                                x.get("query_id") or "")):
            f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    with open(audit_out, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2, sort_keys=True)

    print("OK: query_ledger -> %s (entries=%d, unrecorded=%s)"
          % (ledger_out, len(entries), ",".join(unrecorded) or "-"))
    print("OK: query_audit -> %s (mechanical=%s, pagination=%s)"
          % (audit_out, audit["mechanical_copy"]["verdict"],
             "; ".join("%s:%s" % (p["source_db"], p["status"])
                       for p in audit["pagination"])))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="构建查询台账 + 编排审计（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--ledger-out", default=None, help="台账输出路径")
    ap.add_argument("--audit-out", default=None, help="审计输出路径")
    args = ap.parse_args()
    try:
        return main_inner(args)
    except Exception as e:
        print("ERROR: 未捕获异常，诚实降级 exit 2: %r" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
