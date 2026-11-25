#!/usr/bin/env python3
"""pipeline.py — 确定性检索筛查管线（契约驱动；筛查逻辑保持简单、可复算）。

用法:
  python3 pipeline.py --case /input/case.json --input-dir /input \
      --work /app/work --out /app/output [--overrides /app/work/overrides.json]

步骤（全部确定性，无网络）:
  1. ingest   递归解析 JSON/JSONL/CSV/TSV/RIS 中的文献记录，统一 schema，溯源到 文件!行号；
              署名清单键（attributed_papers 等）不作为记录来源，避免自匹配
  2. dedupe   DOI 相同 → 归一化标题相同 → 标题 token Jaccard≥0.85；夹具标记原样登记
  3. screen   从 research_question 派生年份窗与术语（拉丁词 + CJK 二元组 + 内置跨语词表
              LEXICON 扩展，跨语扩展仅取自 RQ 中真实出现的概念，不联网）；逐条
              include/exclude/uncertain + 理由码
  4. attest   自动定位署名文献清单并逐篇核验（matched/ambiguous/missing + 元数据差异）
  5. finalize 按 output_contract 装配 result.json；每个空契约字段都在 field_notes 写明原因

overrides.json（可选，人工/Agent 复核后写入）:
  [{"rid": "...", "disposition": "include|exclude", "reason": "...", "sq": "SQ-1"}]
"""
import argparse, csv, json, os, re, time

RECORD_KEYS = ("records", "results", "items", "export", "entries", "hits")
REFLIST_KEYS = ("attributed_papers", "reference_list", "references", "refs", "paper_list")
FIXTURE_KEYS = ("synthetic_duplicate", "duplicate_of", "is_fixture", "fixture",
                "conflict_opinion", "synthetic", "label")
STOPWORDS = set("""the a an and or of in on for to with by from at as is are was were be been
we our this that these those it its their between among within without into over under
study studies using based approach results show via new""".split())

# 内置跨语词表：仅当 RQ 中真实出现左侧中文概念时才扩展右侧英文检索词。
# 覆盖本题常见材料/能源领域；领域外 RQ 自动退化为拉丁词 + CJK 二元组，不臆造术语。
LEXICON = [
    ("钙钛矿", ["perovskite"]),
    ("太阳能", ["solar", "photovoltaic"]),
    ("光伏", ["photovoltaic", "solar cell"]),
    ("电池", ["cell", "battery"]),
    ("晶界", ["grain boundary", "grain-boundary"]),
    ("钝化", ["passivation", "passivate"]),
    ("缺陷", ["defect"]),
    ("效率", ["efficiency"]),
    ("光电转换", ["power conversion", "efficiency"]),
    ("稳定性", ["stability", "stable"]),
    ("降解", ["degradation", "degrade"]),
    ("界面", ["interface", "interfacial"]),
    ("载流子", ["carrier", "charge carrier"]),
    ("复合", ["recombination"]),
    ("掺杂", ["doping", "doped"]),
    ("薄膜", ["thin film", "film"]),
    ("量子点", ["quantum dot"]),
    ("催化", ["catalysis", "catalyst"]),
    ("电解", ["electrolyte", "electrolysis"]),
    ("锂", ["lithium", "li-ion"]),
    ("钠", ["sodium"]),
    ("超导", ["superconductor", "superconductivity"]),
    ("拓扑", ["topological"]),
    ("磁性", ["magnetic", "magnetism"]),
    ("神经网络", ["neural network"]),
    ("机器学习", ["machine learning"]),
    ("深度学习", ["deep learning"]),
    ("大语言模型", ["large language model", "llm"]),
    ("蛋白质", ["protein"]),
    ("基因", ["gene", "genomic"]),
    ("肿瘤", ["tumor", "cancer"]),
    ("药物", ["drug"]),
    ("单细胞", ["single-cell", "single cell"]),
    ("CRISPR", ["crispr"]),
]


# ---------- 文本切词 ----------
def text_tokens(t):
    """拉丁词 + CJK 二元组，用于相似度计算。"""
    t = (t or "").lower()
    toks = [w for w in re.findall(r"[a-z0-9]+", t)
            if w not in STOPWORDS and len(w) > 1]
    for run in re.findall(r"[\u4e00-\u9fff]+", t):
        toks.extend(run[i:i + 2] for i in range(len(run) - 1))
    return set(toks)


def norm_title(t):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (t or "").lower())


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------- ingest ----------
def unify(rec, origin):
    r = dict(rec) if isinstance(rec, dict) else {"value": rec}
    authors = r.get("authors") or r.get("author") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r";| and ", authors) if a.strip()]
    year = r.get("year") or r.get("publication_year") or r.get("date") or r.get("py")
    m = re.search(r"(19|20)\d{2}", str(year or ""))
    fixture = {k: r[k] for k in FIXTURE_KEYS if k in r}
    return {
        "rid": origin,
        "title": r.get("title") or r.get("TI") or "",
        "authors": authors,
        "year": int(m.group(0)) if m else None,
        "doi": (r.get("doi") or r.get("DO") or "").strip().lower() or None,
        "venue": r.get("venue") or r.get("journal") or r.get("JO") or r.get("source") or "",
        "type": (r.get("type") or r.get("TY") or r.get("doctype") or "").lower(),
        "abstract": r.get("abstract") or r.get("AB") or "",
        "fixture_flags": fixture,
    }


def find_record_lists(obj, path="$"):
    """深度优先寻找记录列表；命中 RECORD_KEYS 后不再下钻（防止重复计数）；
    通用列表分支排除署名清单键（避免清单文献被当作快照记录自匹配）。"""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in RECORD_KEYS and isinstance(v, list) and v and isinstance(v[0], dict):
                found.append(("%s.%s" % (path, k), v))
            else:
                found.extend(find_record_lists(v, "%s.%s" % (path, k)))
    elif isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        last = path.rsplit(".", 1)[-1]
        if last not in REFLIST_KEYS and any("title" in x or "doi" in x for x in obj[:5]):
            found.append((path, obj))
    return found


def parse_ris(text):
    recs, cur = [], {}
    tag = {"TI": "title", "T1": "title", "AU": "authors", "DO": "doi",
           "PY": "year", "JO": "venue", "JF": "venue", "TY": "type", "AB": "abstract"}
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])  - (.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k == "TY":
            cur = {"type": v}
        elif k == "ER":
            if cur:
                recs.append(cur)
            cur = {}
        elif k in tag:
            if tag[k] == "authors":
                cur.setdefault("authors", []).append(v)
            else:
                cur[tag[k]] = v
    if cur:
        recs.append(cur)
    return recs


def ingest(input_dir, case_path):
    records, failures, files = [], [], []
    for root, _d, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, input_dir)
            ext = os.path.splitext(n)[1].lower()
            try:
                if ext == ".jsonl":
                    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
                    for i, r in enumerate(rows):
                        records.append(unify(r, "%s!#%d" % (rel, i + 1)))
                    files.append({"path": rel, "kind": "jsonl",
                                  "record_lists": 1 if rows else 0})
                elif ext == ".json":
                    obj = json.load(open(p, encoding="utf-8"))
                    lists = find_record_lists(obj)
                    for lpath, rows in lists:
                        for i, r in enumerate(rows):
                            records.append(unify(r, "%s!%s#%d" % (rel, lpath, i + 1)))
                    files.append({"path": rel, "kind": "json", "record_lists": len(lists)})
                elif ext in (".csv", ".tsv"):
                    with open(p, encoding="utf-8", newline="") as fh:
                        rows = list(csv.DictReader(fh, delimiter="\t" if ext == ".tsv" else ","))
                    for i, r in enumerate(rows):
                        records.append(unify(r, "%s!row#%d" % (rel, i + 1)))
                    files.append({"path": rel, "kind": ext[1:], "record_lists": 1 if rows else 0})
                elif ext == ".ris":
                    rows = parse_ris(open(p, encoding="utf-8").read())
                    for i, r in enumerate(rows):
                        records.append(unify(r, "%s!ris#%d" % (rel, i + 1)))
                    files.append({"path": rel, "kind": "ris", "record_lists": 1 if rows else 0})
                else:
                    files.append({"path": rel, "kind": ext.lstrip(".") or "none",
                                  "record_lists": 0})
            except Exception as e:
                failures.append({"path": rel, "error": str(e)})
    return records, files, failures


# ---------- dedupe ----------
def dedupe(records):
    kept, dups = [], []
    for r in records:
        hit = None
        for k in kept:
            if r["doi"] and k["doi"] and r["doi"] == k["doi"]:
                hit = (k, "doi", 1.0)
                break
            if r["title"] and norm_title(r["title"]) == norm_title(k["title"]):
                hit = (k, "title_exact", 1.0)
                break
            sim = jaccard(text_tokens(r["title"]), text_tokens(k["title"]))
            if sim >= 0.85:
                hit = (k, "title_jaccard", round(sim, 3))
                break
        if hit:
            dups.append({"kept": hit[0]["rid"], "dropped": r["rid"],
                         "method": hit[1], "similarity": hit[2],
                         "synthetic_flag": bool(r["fixture_flags"] or hit[0]["fixture_flags"]),
                         "note": "输入夹具标记的合成重复" if r["fixture_flags"] else ""})
        else:
            kept.append(r)
    return kept, dups


# ---------- screen ----------
def derive_terms(rq):
    """从研究问题派生: 年份窗、拉丁词、CJK 二元组、跨语扩展（仅 RQ 出现的概念）。"""
    rq = rq or ""
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", rq)]
    window = [min(years), max(years)] if len(years) >= 2 else (
        [years[0], years[0]] if years else None)
    terms = set(t for t in re.findall(r"[a-z0-9]+", rq.lower())
                if t not in STOPWORDS and len(t) > 2)
    expanded = []
    for cjk, en_list in LEXICON:
        if cjk.lower() in rq.lower():
            terms.update(en_list)
            expanded.append({"concept": cjk, "terms": en_list})
    for run in re.findall(r"[\u4e00-\u9fff]+", rq):
        terms.update(run[i:i + 2] for i in range(len(run) - 1) if len(run) > 1)
    return window, sorted(terms), expanded


def screen(kept, rq, overrides):
    window, terms, expanded = derive_terms(rq)
    ov = {o.get("rid"): o for o in (overrides or [])}
    ledger, counts = [], {"included": 0, "excluded": 0, "uncertain": 0}
    need = max(2, min(4, len(terms) // 4)) if terms else 0
    for r in kept:
        text = " ".join([r["title"], r["abstract"], r["venue"]]).lower()
        hits = [t for t in terms if t in text]
        codes, disp = [], None
        if window and r["year"] and not (window[0] <= r["year"] <= window[1]):
            disp, codes = "exclude", ["year_out_of_window:%s!in:%s" % (r["year"], window)]
        elif r["type"] in ("review", "perspective", "editorial", "news"):
            disp, codes = "exclude", ["doctype_excluded:%s" % r["type"]]
        if disp is None:
            if need and len(hits) >= need:
                disp, codes = "include", ["term_hits:%d>=%d" % (len(hits), need)]
            elif hits:
                disp, codes = "uncertain", ["weak_term_hits:%d<%d" % (len(hits), need)]
            else:
                disp, codes = "exclude", ["no_term_hits"]
        if r["rid"] in ov:
            codes.append("manual_override")
            disp = ov[r["rid"]].get("disposition", disp)
        if r["fixture_flags"]:
            codes.append("fixture_labelled:" + ",".join(sorted(r["fixture_flags"])))
        counts[{"include": "included", "exclude": "excluded"}.get(disp, "uncertain")] += 1
        ledger.append({"rid": r["rid"], "disposition": disp, "reason_codes": codes,
                       "matched_terms": hits,
                       "override_reason": ov.get(r["rid"], {}).get("reason"),
                       "title": r["title"], "year": r["year"], "doi": r["doi"],
                       "source": r["rid"].split("!")[0]})
    return ledger, counts, {"year_window": window, "terms": terms,
                            "crosslingual_expansion": expanded, "hit_threshold": need}


# ---------- attest ----------
def find_reflist(input_dir, case):
    for key in REFLIST_KEYS:
        if isinstance(case.get(key), list) and case[key]:
            return "case.json!%s" % key, case[key]
    for root, _d, names in os.walk(input_dir):
        for n in sorted(names):
            if not n.endswith(".json"):
                continue
            p = os.path.join(root, n)
            try:
                obj = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            stack = [("", obj)]
            while stack:
                kp, cur = stack.pop()
                if isinstance(cur, dict):
                    for k, v in cur.items():
                        if k in REFLIST_KEYS and isinstance(v, list) and v:
                            return "%s!%s" % (os.path.relpath(p, input_dir), k), v
                        stack.append((k, v))
    return None, []


def attest(kept, input_dir, case):
    origin, refs = find_reflist(input_dir, case)
    if not refs:
        return {"status": "no_reference_list",
                "note": "输入中未找到署名文献清单；归属核验未执行", "papers": []}
    papers, stat = [], {"matched": 0, "ambiguous": 0, "missing": 0}
    for i, ref in enumerate(refs):
        ref = ref if isinstance(ref, dict) else {"title": str(ref)}
        rid = ref.get("ref_id") or ref.get("id") or "ref-%d" % (i + 1)
        rdoi = (ref.get("doi") or "").strip().lower()
        rtoks = text_tokens(ref.get("title", ""))
        best, best_sim, second = None, 0.0, 0.0
        for r in kept:
            if rdoi and r["doi"] == rdoi:
                best, best_sim = r, 1.0
                break
            sim = jaccard(rtoks, text_tokens(r["title"]))
            if sim > best_sim:
                best, best_sim, second = r, sim, best_sim
            elif sim > second:
                second = sim
        entry = {"ref_id": rid, "title": ref.get("title"), "doi": ref.get("doi") or None}
        if best is None or best_sim < 0.5:
            entry["status"] = "missing"
        elif best_sim < 0.85 and (best_sim - second) < 0.1:
            entry["status"] = "ambiguous"
            entry["match"] = {"rid": best["rid"], "similarity": round(best_sim, 3)}
        else:
            entry["status"] = "matched"
            diff = []
            if ref.get("year") and best["year"] and int(ref["year"]) != best["year"]:
                diff.append("year: 清单 %s vs 快照 %s" % (ref["year"], best["year"]))
            ra = ref.get("first_author") or (ref.get("authors") or [None])[0]
            ba = (best["authors"] or [None])[0]
            if ra and ba and ra.split()[-1].lower() != ba.split()[-1].lower():
                diff.append("first_author: 清单 %s vs 快照 %s" % (ra, ba))
            entry["match"] = {"rid": best["rid"], "similarity": round(best_sim, 3),
                              "metadata_diff": diff}
        stat[entry["status"]] += 1
        papers.append(entry)
    return {"status": "ok", "origin": origin, "total": len(refs), **stat, "papers": papers}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--overrides")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    case = json.load(open(args.case, encoding="utf-8")) if os.path.isfile(args.case) else {}
    overrides = []
    if args.overrides and os.path.isfile(args.overrides):
        overrides = json.load(open(args.overrides, encoding="utf-8"))

    records, files, failures = ingest(args.input_dir, args.case)
    kept, dups = dedupe(records)
    ledger, counts, criteria = screen(kept, case.get("research_question"), overrides)
    attrib = attest(kept, args.input_dir, case)
    cands = [{"rid": l["rid"], "title": l["title"], "year": l["year"], "doi": l["doi"],
              "matched_terms": l["matched_terms"], "source": l["source"]}
             for l in ledger if l["disposition"] == "include"]

    def dump(name, obj, where=None):
        with open(os.path.join(where or args.work, name), "w", encoding="utf-8") as fh:
            if name.endswith(".jsonl"):
                for row in obj:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            else:
                json.dump(obj, fh, ensure_ascii=False, indent=2)

    dump("records.jsonl", records)
    dump("deduped_records.jsonl", kept)
    dump("duplicates.jsonl", dups)
    dump("ingest_report.json", {"files": files, "records_total": len(records),
                                "failures": failures})
    dump("ledger.jsonl", ledger, args.out)
    dump("candidates.json", cands, args.out)
    dump("screening_summary.json", {"counts": counts, "criteria": criteria,
                                    "overrides_applied": len(overrides)}, args.out)
    dump("attribution.json", attrib, args.out)

    # ---- finalize: 按契约装配 result.json ----
    uncertainty = ["%d 个文件解析失败，详见 ingest_report.json" % len(failures)] if failures else []
    for l in ledger:
        if l["disposition"] == "include" and "conflict_opinion" in ",".join(l["reason_codes"]):
            uncertainty.append("冲突意见夹具记录 %s 已登记为争议证据，本管线不做学术裁决" % l["rid"])
    if attrib.get("status") == "no_reference_list":
        uncertainty.append(attrib["note"])
    for p in attrib.get("papers", []):
        if p["status"] == "missing":
            uncertainty.append("清单文献 %s 在快照中未找到匹配记录" % p["ref_id"])
        elif p.get("match", {}).get("metadata_diff"):
            uncertainty.append("清单文献 %s 元数据不一致: %s"
                               % (p["ref_id"], "; ".join(p["match"]["metadata_diff"])))
    if counts["uncertain"]:
        uncertainty.append("%d 条记录处置为 uncertain，需人工复核" % counts["uncertain"])
    status = "blocked" if not records else ("partial" if uncertainty else "complete")
    result = {
        "case_id": case.get("case_id"),
        "summary": ("解析 %d 条记录，去重移除 %d 条（含夹具标注合成重复 %d 条）；纳入 %d / "
                    "排除 %d / 待复核 %d；署名清单 %s 篇（匹配 %s/存疑 %s/缺失 %s）"
                    % (len(records), len(dups), sum(1 for d in dups if d["synthetic_flag"]),
                       counts["included"], counts["excluded"], counts["uncertain"],
                       attrib.get("total", "无"), attrib.get("matched", "-"),
                       attrib.get("ambiguous", "-"), attrib.get("missing", "-"))),
        "candidates": cands,
        "screening_log": ledger,
        "duplicates": dups,
        "attribution": attrib.get("papers", []),
        "omissions": [u for u in uncertainty],
        "sources": ([{"kind": "file", "path": f["path"]} for f in files if f.get("record_lists")] +
                    [{"kind": "artifact", "path": n} for n in
                     ("ledger.jsonl", "candidates.json", "screening_summary.json",
                      "attribution.json", "validate-report.json")]),
        "status": status,
        "uncertainty": uncertainty,
        "method": "a-contract-sentinel: probe→ingest→dedupe→screen→attest→validate",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    for f in contract_fields(case):
        if f not in result:
            result[f] = []
            uncertainty.append("output_contract 字段 %s 无对应产物，留空待补" % f)
    # field_notes: 每个空契约字段的明确说明（validate.py C4 的依据）
    notes = {}
    for f in contract_fields(case):
        v = result.get(f)
        if v in ([], "", {}):
            notes[f] = ("本字段为空的原因已在 uncertainty 中说明"
                        if any(f in u for u in uncertainty) else
                        "本次运行无此类条目（如实留空，非遗漏）")
    result["field_notes"] = notes
    result["uncertainty"] = uncertainty
    dump("result.json", result, args.out)
    print(json.dumps({"ok": True, "records": len(records), "kept": len(kept),
                      "candidates": len(cands), "status": status,
                      "uncertainty_items": len(uncertainty)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
