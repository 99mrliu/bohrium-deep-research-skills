#!/usr/bin/env python3
"""known_item_audit.py — known-item 召回审计 + 按契约装配 result.json。

把署名文献清单当作 known items，审计 foundry 锻造的查询族对它们的召回：
每篇清单文献——是否匹配到快照记录、被哪些查询命中、在每个查询的命中列表里
排第几；missing 时给出可复核诊断（快照缺席 / 年份出窗 / 术语缺口 / 弱命中 /
文献类型）。同时产出逐查询画像（命中数、known-item 命中、噪声估计）。

用法:
  python3 known_item_audit.py --case /input/case.json --input-dir /input \
      --work /app/work --out /app/output [--finalize]

前置: 必须先跑 foundry.py（需要 work/ 下的 records.jsonl、query-families.json、
hits.jsonl 与 out/ 下的 candidates.json、screening-ledger.jsonl）。

退出码: 0=审计完成（含 missing 诊断，属正常发现）；2=前置产物缺失/损坏
（--finalize 时会先写 blocked 骨架再退出）。
"""
import argparse, json, os, re, sys, time

REFLIST_KEYS = ("attributed_papers", "reference_list", "references", "refs", "paper_list")
EN_STOP = set("""the a an and or of in on for to with by from at as is are was were be been
we our this that these those it its their between among within without into over under
study studies using based approach results show via new with from""".split())


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    return rows


def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        for k in ("fields", "required"):
            if isinstance(c.get(k), list):
                return [str(x) for x in c[k]]
        return sorted(c.keys())
    return []


def title_tokens(t):
    t = (t or "").lower()
    toks = {w for w in re.findall(r"[a-z0-9]+", t) if w not in EN_STOP and len(w) > 2}
    for run in re.findall(r"[\u4e00-\u9fff]+", t):
        toks.update(run[i:i + 2] for i in range(len(run) - 1))
    return toks


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def derive_window(rq):
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", rq or "")]
    if len(years) >= 2:
        return [min(years), max(years)]
    if years:
        return [years[0], years[0]]
    return None


# ---------- 署名清单定位 ----------
def find_reflist(case, input_dir):
    for key in REFLIST_KEYS:
        if isinstance(case.get(key), list) and case[key]:
            return "case.json!%s" % key, case[key]
    for root, _d, names in os.walk(input_dir):
        for n in sorted(names):
            if not n.endswith(".json"):
                continue
            obj = load_json(os.path.join(root, n))
            stack = [obj]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    for k, v in cur.items():
                        if k in REFLIST_KEYS and isinstance(v, list) and v:
                            return "%s!%s" % (n, k), v
                        stack.append(v)
                elif isinstance(cur, list):
                    stack.extend(cur)
    return None, []


# ---------- known-item 与快照记录匹配 ----------
def match_record(ref, records):
    rdoi = (ref.get("doi") or "").strip().lower()
    if rdoi:
        for r in records:
            if r.get("doi") == rdoi:
                return r, 1.0
    rtoks = title_tokens(ref.get("title", ""))
    best, best_sim = None, 0.0
    for r in records:
        sim = jaccard(rtoks, title_tokens(r.get("title", "")))
        if sim > best_sim:
            best, best_sim = r, sim
    return (best, best_sim) if best_sim >= 0.6 else (None, best_sim)


def audit_known_items(refs, records, hits, ledger, queries, window):
    """逐篇审计。返回 (items, summary)。"""
    term_surfaces = set()
    for q in queries:
        for t in q["terms"]:
            term_surfaces.add(t["term"])
            term_surfaces.update(t.get("variants", []))
    ledger_by_rid = {l["rid"]: l for l in ledger}
    hits_by_rid = {}
    for h in hits:
        hits_by_rid.setdefault(h["rid"], []).append(h)
    candidate_rids = {l["rid"] for l in ledger if l["disposition"] == "include"}

    items, n_hit = [], 0
    for i, ref in enumerate(refs):
        ref = ref if isinstance(ref, dict) else {"title": str(ref)}
        rid_ref = ref.get("ref_id") or ref.get("id") or "KI-%d" % (i + 1)
        entry = {"ref_id": rid_ref, "title": ref.get("title"), "doi": ref.get("doi")}
        rec, sim = match_record(ref, records)
        if rec is None:
            entry.update({"status": "missing", "matched_rid": None,
                          "diagnosis": ["snapshot_absent: 快照内无 DOI 精确或标题 token "
                                        "相似度≥0.6 的记录（最高相似度 %.2f）" % sim],
                          "hit_queries": []})
            items.append(entry)
            continue
        qhits = hits_by_rid.get(rec["rid"], [])
        ranked = []
        for h in qhits:
            same_q = [x for x in hits if x["qid"] == h["qid"]]
            order = sorted(same_q, key=lambda x: (-len(x["matched"]), x["rid"]))
            rank = [x["rid"] for x in order].index(rec["rid"]) + 1
            ranked.append({"qid": h["qid"], "family": h["family"], "rank": rank,
                           "matched_terms": sorted({m["term"] for m in h["matched"]})})
        disp = ledger_by_rid.get(rec["rid"], {}).get("disposition")
        diagnosis = []
        if disp == "include":
            entry["status"] = "recalled"
            n_hit += 1
        else:
            entry["status"] = "missing"
            codes = ledger_by_rid.get(rec["rid"], {}).get("reason_codes", [])
            if any(c.startswith("year_out_of_window") for c in codes):
                diagnosis.append("year_gap: 记录年份 %s 在 RQ 年份窗 %s 之外，"
                                 "查询虽召回但被年份条款排除" % (rec["year"], window))
            if any(c.startswith("doctype_excluded") for c in codes):
                diagnosis.append("doctype_gap: 记录类型 %s 被条款排除" % rec["type"])
            if any(c == "fixture_duplicate_registered" for c in codes):
                diagnosis.append("fixture_duplicate: 记录带合成重复夹具标记，登记不入候选")
            if not qhits:
                diagnosis.append("query_recall_zero: 无任何查询命中该记录")
            elif any(c == "weak_single_term_hit" for c in codes):
                diagnosis.append("weak_recall: 仅单个术语查询命中，强度不足")
            # 术语缺口：清单标题中未被任何查询术语/变体覆盖的实义词
            uncovered = sorted(t for t in title_tokens(ref.get("title", ""))
                               if t not in term_surfaces
                               and not any(t in s or s in t for s in term_surfaces
                                           if len(s) > 2))
            if uncovered and entry["status"] == "missing":
                diagnosis.append("term_gap: 标题术语未被查询族覆盖: %s"
                                 % ", ".join(uncovered[:6]))
        entry.update({"matched_rid": rec["rid"], "match_similarity": round(sim, 3),
                      "disposition": disp, "hit_queries": ranked,
                      "diagnosis": diagnosis})
        items.append(entry)
    summary = {"total": len(refs), "recalled": n_hit,
               "missing": len(refs) - n_hit,
               "recall": ("%d/%d" % (n_hit, len(refs))) if refs else "0/0"}
    return items, summary


def query_report(queries, hits, items):
    """逐查询画像：命中数、known-item 命中、噪声估计（非清单命中条数，为噪声上限）。"""
    rid2refs = {}
    for it in items:
        if it.get("matched_rid"):
            rid2refs.setdefault(it["matched_rid"], []).append(it["ref_id"])
    per_query = []
    for q in queries:
        qh = [h for h in hits if h["qid"] == q["qid"]]
        known = sorted({ref for h in qh for ref in rid2refs.get(h["rid"], [])})
        per_query.append({"qid": q["qid"], "family": q["family"], "op": q["op"],
                          "terms": [t["term"] for t in q["terms"]],
                          "hits": len(qh),
                          "known_item_hits": known,
                          "noise_estimate": len(qh) - len({h["rid"] for h in qh
                                                         if h["rid"] in rid2refs})})
    families = {}
    for p in per_query:
        f = families.setdefault(p["family"], {"queries": 0, "hits": 0,
                                              "known_item_union": set()})
        f["queries"] += 1
        f["hits"] += p["hits"]
        f["known_item_union"].update(p["known_item_hits"])
    for f in families.values():
        f["known_item_union"] = sorted(f["known_item_union"])
    return {"per_query": per_query, "per_family": families,
            "note": "noise_estimate 为命中中不属于任何清单文献的条数（噪声上限估计，"
                    "非清单文献未必不相关）"}


def write_blocked(args, case, reasons):
    os.makedirs(args.out, exist_ok=True)
    skeleton = {"case_id": case.get("case_id"), "status": "blocked",
                "sources": [], "uncertainty": list(reasons),
                "method": "d-query-foundry: known_item_audit(blocked)",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    for f in contract_fields(case):
        if f not in skeleton:
            skeleton[f] = []
    skeleton["field_notes"] = {f: "前置产物缺失，本字段无法生成：%s" % "; ".join(reasons)
                               for f in contract_fields(case)}
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(skeleton, fh, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="known-item 召回审计 + 契约装配")
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--finalize", action="store_true",
                    help="审计后按 output_contract 装配 result.json")
    args = ap.parse_args()

    case = load_json(args.case, {}) or {}
    records = load_jsonl(os.path.join(args.work, "records.jsonl"))
    qf = load_json(os.path.join(args.work, "query-families.json"))
    hits = load_jsonl(os.path.join(args.work, "hits.jsonl"))
    ledger = load_jsonl(os.path.join(args.out, "screening-ledger.jsonl"))
    missing_inputs = [n for n, ok in
                      [("records.jsonl", bool(records)),
                       ("query-families.json", isinstance(qf, dict) and bool(qf.get("queries"))),
                       ("hits.jsonl", os.path.isfile(os.path.join(args.work, "hits.jsonl"))),
                       ("screening-ledger.jsonl", bool(ledger))] if not ok]
    if missing_inputs:
        reasons = ["foundry 前置产物缺失或为空: %s（请先运行 foundry.py）"
                   % ", ".join(missing_inputs)]
        if args.finalize:
            write_blocked(args, case, reasons)
        print(json.dumps({"ok": False, "blocked": reasons}, ensure_ascii=False))
        sys.exit(2)

    queries = qf["queries"]
    window = derive_window(case.get("research_question"))
    origin, refs = find_reflist(case, args.input_dir)

    uncertainty = []
    if not refs:
        audit = {"status": "no_reference_list",
                 "note": "输入中未找到署名文献清单，known-item 审计未执行",
                 "items": [], "summary": {"total": 0, "recalled": 0,
                                          "missing": 0, "recall": "0/0"}}
        uncertainty.append(audit["note"])
    else:
        items, summary = audit_known_items(refs, records, hits, ledger, queries, window)
        audit = {"status": "ok", "origin": origin, "items": items, "summary": summary}

    report = query_report(queries, hits, audit["items"])
    report["known_item_recall"] = audit["summary"]["recall"]

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "known-item-audit.json"), "w", encoding="utf-8") as fh:
        json.dump(audit, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "query-report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    if not args.finalize:
        print(json.dumps({"ok": True, "known_items": audit["summary"]["total"],
                          "recalled": audit["summary"]["recalled"],
                          "missing": audit["summary"]["missing"]}, ensure_ascii=False))
        sys.exit(0)

    # ---------- finalize: 按契约装配 result.json ----------
    candidates_obj = load_json(os.path.join(args.out, "candidates.json"), {}) or {}
    candidates = candidates_obj.get("candidates", [])
    ingest_report = load_json(os.path.join(args.work, "ingest-report.json"), {}) or {}

    for it in audit["items"]:
        if it["status"] == "missing":
            uncertainty.append("清单文献 %s 未被查询族召回到候选集: %s"
                               % (it["ref_id"], "; ".join(it["diagnosis"])))
    for l in ledger:
        if l["fixture"] and "conflict_opinion" in (l["fixture"] or {}):
            uncertainty.append("冲突意见夹具记录 %s 已登记为争议证据，不做学术裁决"
                               % l["rid"])
    unc = [l for l in ledger if l["disposition"] == "uncertain"]
    if unc:
        uncertainty.append("%d 条记录仅弱命中（uncertain），需人工复核" % len(unc))
    if ingest_report.get("failures"):
        uncertainty.append("%d 个文件解析失败，详见 ingest-report.json"
                           % len(ingest_report["failures"]))

    status = "blocked" if not records else ("partial" if uncertainty else "complete")
    counts = candidates_obj.get("counts", {})
    summary_text = ("查询族 %d 个（phrase/and2/term）在 %d 条快照记录上执行；纳入 %d / "
                    "待复核 %d / 排除 %d；known-item 召回 %s（%s）"
                    % (len(queries), len(records), counts.get("include", 0),
                       counts.get("uncertain", 0), counts.get("exclude", 0),
                       audit["summary"]["recall"],
                       "；".join("%s=%s" % (it["ref_id"], it["status"])
                                 for it in audit["items"]) or "无清单"))

    result = {
        "case_id": case.get("case_id"),
        "summary": summary_text,
        "candidates": candidates,
        "query_report": report,
        "known_item_audit": audit["items"],
        "screening_log": ledger,
        "omissions": [u for u in uncertainty],
        "status": status,
        "sources": ([{"kind": "file", "path": f["path"]}
                     for f in ingest_report.get("files", []) if f.get("records")] +
                    [{"kind": "artifact", "path": n} for n in
                     ("candidates.json", "query-execution.json", "query-report.json",
                      "known-item-audit.json", "screening-ledger.jsonl")]),
        "uncertainty": uncertainty,
        "method": "d-query-foundry: foundry(terms→variants→queries→execute→screen)"
                  " → known_item_audit(recall diagnose) → finalize",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    # 契约字段动态装配：无对应产物的字段留空 + field_notes 说明（空≠漏）
    notes = {}
    for f in contract_fields(case):
        if f not in result:
            result[f] = []
            uncertainty.append("output_contract 字段 %s 无对应产物，留空待补" % f)
        if result.get(f) in ([], "", {}) and f not in ("uncertainty",):
            notes[f] = ("本字段为空的原因已在 uncertainty 中说明"
                        if any(f in u for u in uncertainty) else
                        "本次运行无此类条目（如实留空，非遗漏）")
    result["field_notes"] = notes
    result["uncertainty"] = uncertainty
    if "omissions" in contract_fields(case):
        result["omissions"] = [u for u in uncertainty]

    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "known_items": audit["summary"]["total"],
                      "recalled": audit["summary"]["recalled"],
                      "missing": audit["summary"]["missing"],
                      "candidates": len(candidates), "status": status,
                      "uncertainty_items": len(uncertainty)}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
