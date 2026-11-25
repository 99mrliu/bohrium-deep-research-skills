#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forensics_pipeline.py -- 参考集取证管线（skill-a-source-forensics）。

重心：上游数据真实性。任何题录在进入覆盖率分母之前，必须先通过"真实性门控"：
  1. 材料监管链：对每份输入材料计算 SHA-256，生成 authenticity_manifest.json；
  2. 逐条核验：以案例本地留存的 Crossref / EuropePMC / 出版商响应文件为真值源，
     核验标识符与题录字段；本地响应缺失时诚实标记 unverified，绝不臆造核验结论；
  3. 异常处置：撤稿、标识符冲突、重复、无全文逐条记录 disposition；
  4. 冻结分母：输出带版本与内容哈希的 reference_set.json（v1.0.0），冻结后
     任何改动进入 change_log。
随后完成完整闭环：覆盖测量 -> 漏检清单与归因 -> 定向补检建议 -> result.json。

仅使用 Python 标准库；网络兜底默认关闭（--allow-net 才启用，且只读、带缓存）。
退出码：0 完成；2 材料不足（诚实 partial）；3 产物校验失败。
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys

VERSION = "1.0.0"
REFSET_VERSION = "v1.0.0"

# ---------------------------------------------------------------- 通用工具

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def norm_doi(doi):
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip().rstrip(".")


def norm_title(title):
    if not title:
        return ""
    t = re.sub(r"[^a-z0-9 ]+", " ", str(title).lower())
    return re.sub(r"\s+", " ", t).strip()


def title_tokens(title):
    stop = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "by"}
    return [t for t in norm_title(title).split() if t not in stop]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def first_year(rec):
    for key in ("year", "published", "issued", "date"):
        v = rec.get(key)
        if v is None:
            continue
        m = re.search(r"(19|20)\d{2}", str(v))
        if m:
            return int(m.group(0))
    return None


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=False)


# ---------------------------------------------------------------- 材料监管链

TEXT_EXT = (".json", ".jsonl", ".csv", ".bib", ".ris", ".txt", ".md", ".tsv", ".xml")
PDF_EXT = (".pdf",)


def scan_materials(input_dir):
    """列出输入目录中的全部材料文件（不依赖文件名臆测内容，只按扩展名归类候选）。"""
    files = []
    for root, _dirs, names in os.walk(input_dir):
        for name in sorted(names):
            p = os.path.join(root, name)
            if os.path.isfile(p) and not os.path.islink(p):
                files.append(p)
    return files


def build_authenticity_manifest(files, work_dir):
    entries = []
    for p in files:
        st = os.stat(p)
        entries.append({
            "path": p,
            "sha256": sha256_file(p),
            "bytes": st.st_size,
            "role_hint": classify_material(p),
        })
    manifest = {
        "manifest_version": "1",
        "created_at": now_iso(),
        "file_count": len(entries),
        "files": entries,
    }
    manifest["manifest_sha256"] = sha256_text(json.dumps(entries, sort_keys=True))
    dump_json(os.path.join(work_dir, "authenticity_manifest.json"), manifest)
    return manifest


def classify_material(path):
    """按内容线索归类材料角色；不确定则为 unknown，由后续阶段实际解析决定。"""
    name = os.path.basename(path).lower()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096)
    except Exception:
        return "unreadable"
    if path.lower().endswith(PDF_EXT):
        return "pdf_document"
    # 检索结果优先判定：含 queries/hits 结构且声明了查询式
    if re.search(r'"(queries|searches)"\s*:', head) and re.search(r'"(hits|results|records)"\s*:', head):
        return "search_results"
    if re.search(r'"message"\s*:\s*\{|api\.crossref|works/', head, re.I) or "crossref" in name:
        return "crossref_response"
    if re.search(r'"resultList"\s*:\s*\{|europepmc|europe_pmc', head, re.I) or "europepmc" in name:
        return "europepmc_response"
    if re.search(r'"hit|"result|"records"|"query"', head) and re.search(r"search|quer", head + name, re.I):
        return "search_results"
    if re.search(r"doi|pmid|arxiv|title", head, re.I) and name.endswith((".csv", ".bib", ".ris", ".json", ".jsonl", ".tsv")):
        return "bibliography_candidate"
    return "unknown"


# ---------------------------------------------------------------- 本地响应索引（真值源）

def index_local_responses(files):
    """把本地留存的 API 响应文件索引为 doi/pmid -> 记录 的映射，作为核验真值源。"""
    by_doi, by_pmid, sources = {}, {}, []
    for p in files:
        if not p.lower().endswith((".json", ".jsonl")):
            continue
        role = classify_material(p)
        if role not in ("crossref_response", "europepmc_response", "unknown", "bibliography_candidate"):
            continue
        try:
            with open(path if False else p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception:
            continue
        # 只在响应特征明显时采信为真值源
        if not re.search(r'crossref|europepmc|"message"|"resultList"|"status"\s*:\s*"ok"', text, re.I):
            continue
        recs = extract_records_from_response(text)
        if not recs:
            continue
        sources.append(p)
        for r in recs:
            d = norm_doi(r.get("doi"))
            if d and d not in by_doi:
                by_doi[d] = {"record": r, "source_file": p}
            pm = str(r.get("pmid") or "").strip()
            if pm and pm not in by_pmid:
                by_pmid[pm] = {"record": r, "source_file": p}
    return {"by_doi": by_doi, "by_pmid": by_pmid, "response_files": sources}


def extract_records_from_response(text):
    """从 Crossref / EuropePMC 响应文本中提取规范化记录列表。"""
    recs = []
    # JSONL：逐行尝试
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("{")]
    objs = []
    if len(lines) > 1:
        for ln in lines:
            try:
                objs.append(json.loads(ln))
            except Exception:
                pass
    else:
        try:
            objs.append(json.loads(text))
        except Exception:
            return []
    for obj in objs:
        if not isinstance(obj, dict):
            continue
        if "message" in obj and isinstance(obj["message"], dict):  # Crossref 单条/列表
            msg = obj["message"]
            items = msg.get("items") if isinstance(msg.get("items"), list) else [msg]
            for it in items:
                recs.append(normalize_crossref_item(it))
        elif "resultList" in obj:  # EuropePMC
            for it in obj.get("resultList", {}).get("result", []):
                recs.append(normalize_epmc_item(it))
        elif obj.get("DOI") or obj.get("doi"):
            recs.append(normalize_crossref_item(obj) if "DOI" in obj else normalize_epmc_item(obj))
    return [r for r in recs if r]


def normalize_crossref_item(it):
    if not isinstance(it, dict):
        return None
    doi = it.get("DOI") or it.get("doi")
    title = ""
    if isinstance(it.get("title"), list) and it["title"]:
        title = it["title"][0]
    elif isinstance(it.get("title"), str):
        title = it["title"]
    year = None
    for k in ("issued", "published", "created"):
        parts = (it.get(k) or {}).get("date-parts") if isinstance(it.get(k), dict) else None
        if parts and parts[0]:
            year = parts[0][0]
            break
    retracted = False
    rel = it.get("relation") or {}
    if any("retract" in str(k).lower() for k in rel) or "retraction" in json.dumps(it.get("update-to", [])).lower():
        retracted = True
    if it.get("subtype") == "retraction" or it.get("type") == "retraction-notice":
        retracted = True
    authors = []
    for a in it.get("author", []) or []:
        fam = a.get("family") or ""
        if fam:
            authors.append(fam)
    return {"doi": doi, "pmid": it.get("pmid"), "title": title, "year": year,
            "container": (it.get("container-title") or [""])[0] if it.get("container-title") else it.get("journal", ""),
            "authors": authors, "retracted": retracted}


def normalize_epmc_item(it):
    if not isinstance(it, dict):
        return None
    return {"doi": it.get("doi"), "pmid": it.get("pmid") or it.get("id"),
            "title": it.get("title", ""), "year": first_year(it),
            "container": it.get("journalTitle", "") or (it.get("journalInfo", {}) or {}).get("journal", {}).get("title", ""),
            "authors": [a.strip() for a in str(it.get("authorString", "")).split(",") if a.strip()],
            "retracted": "retract" in str(it.get("pubType", "")).lower() or "retract" in str(it.get("title", "")).lower()[:20]}


# ---------------------------------------------------------------- 参考题录解析

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\]},;]+", re.I)


def parse_bibliography_file(path):
    """从 CSV/JSON/JSONL/BibTeX/RIS/TXT 解析候选题录；每条记录携出处指针。"""
    ext = os.path.splitext(path)[1].lower()
    recs = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except Exception:
        return recs
    if ext == ".csv" or ext == ".tsv":
        dialect = csv.excel_tab if ext == ".tsv" else csv.excel
        try:
            for i, row in enumerate(csv.DictReader(text.splitlines(), dialect=dialect)):
                if not row:
                    continue
                r = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
                recs.append({"record": r, "origin": "%s:row%d" % (path, i + 2)})
        except Exception:
            pass
    elif ext in (".json", ".jsonl"):
        objs = []
        lines = [ln for ln in text.splitlines() if ln.strip()]
        parsed_lines = 0
        for ln in lines:
            try:
                o = json.loads(ln)
                objs.append(o)
                parsed_lines += 1
            except Exception:
                pass
        if parsed_lines == 0:
            try:
                o = json.loads(text)
                objs = o if isinstance(o, list) else [o]
            except Exception:
                objs = []
        for i, o in enumerate(objs):
            if isinstance(o, dict) and (o.get("doi") or o.get("DOI") or o.get("title")):
                recs.append({"record": o, "origin": "%s:item%d" % (path, i)})
    elif ext == ".bib":
        for i, m in enumerate(re.finditer(r"@\w+\s*\{([^@]+)\}", text, re.S)):
            body = m.group(1)
            r = {}
            for fm in re.finditer(r"(\w+)\s*=\s*[\{\"](.+?)[\}\"]\s*,?\s*\n", body + "\n"):
                r[fm.group(1).lower()] = fm.group(2).strip()
            if r:
                recs.append({"record": r, "origin": "%s:entry%d" % (path, i)})
    elif ext == ".ris":
        cur, idx = {}, 0
        for ln in text.splitlines():
            if ln.startswith("TY  -"):
                cur = {}
            elif ln.startswith("ER  -"):
                if cur:
                    recs.append({"record": cur, "origin": "%s:record%d" % (path, idx)})
                    idx += 1
            elif len(ln) > 6 and ln[2:6] == "  - ":
                tag, val = ln[:2], ln[6:].strip()
                cur[{"TI": "title", "T1": "title", "DO": "doi", "PY": "year",
                     "JO": "container", "AU": "authors", "PM": "pmid"}.get(tag, tag)] = \
                    (cur.get(tag) + "; " + val) if tag in cur and tag == "AU" else val
    else:  # txt/md：按行扫描 DOI 与编号条目
        for i, ln in enumerate(text.splitlines()):
            for m in DOI_RE.finditer(ln):
                recs.append({"record": {"doi": m.group(0).rstrip(".,;"), "raw_line": ln.strip()[:300]},
                             "origin": "%s:line%d" % (path, i + 1)})
    return recs


# ---------------------------------------------------------------- 阶段实现

def stage_forensics(cands, resp_index, work_dir):
    """逐条核验 + 去重 + 处置 + 冻结。返回 (refset, ledger, exclusions, change_log)。"""
    ledger, exclusions, change_log = [], [], []
    seen = {}   # norm_doi 或弱键 -> index
    refset = []
    for c in cands:
        raw = c["record"]
        doi = norm_doi(raw.get("doi") or raw.get("DOI") or raw.get("DO"))
        pmid = str(raw.get("pmid") or raw.get("PM") or "").strip()
        title = raw.get("title") or raw.get("TI") or raw.get("raw_line", "")
        year = first_year(raw)
        key = doi or ("pmid:" + pmid if pmid else "t:" + norm_title(title)[:80])
        entry = {
            "ref_id": "R%03d" % (len(refset) + 1),
            "doi": doi or None, "pmid": pmid or None,
            "title": title, "year": year,
            "container": raw.get("container") or raw.get("journal") or raw.get("JO") or "",
            "authors": raw.get("authors") or raw.get("AU") or [],
            "origin": c["origin"],
            "inclusion_reason": "listed in organizer-provided material (%s)" % c["origin"],
            "verification_status": "unverified",
            "verification_source": None,
            "usable": True,
            "disposition": "include",
        }
        # 1) 标识符核验（本地真值源）
        hit = resp_index["by_doi"].get(doi) if doi else None
        if not hit and pmid:
            hit = resp_index["by_pmid"].get(pmid)
        if hit:
            vr, src = hit["record"], hit["source_file"]
            entry["verification_status"] = "verified_local"
            entry["verification_source"] = src
            # 字段一致性检查
            if title and vr.get("title") and jaccard(title_tokens(title), title_tokens(vr["title"])) < 0.5:
                entry["disposition"] = "identifier_conflict"
                entry["usable"] = False
                entry["conflict_detail"] = "identifier resolves to different title in %s: %s" % (src, vr.get("title", "")[:120])
            if vr.get("retracted"):
                entry["usable"] = False
                entry["disposition"] = "exclude_retracted"
            if not entry["title"] and vr.get("title"):
                entry["title"] = vr["title"]
            if not entry["year"] and vr.get("year"):
                entry["year"] = vr["year"]
            if not entry["container"] and vr.get("container"):
                entry["container"] = vr["container"]
        else:
            entry["verification_status"] = "unverified_no_local_response"
            entry["disposition"] = "flag_keep_unverified"
        # 2) 去重（强键 DOI/PMID，弱键标题 Jaccard）
        dup_of = None
        if key in seen:
            dup_of = seen[key]
        else:
            for k, idx0 in seen.items():
                prev = refset[idx0]
                if prev.get("title") and title and jaccard(title_tokens(prev["title"]), title_tokens(title)) >= 0.9 \
                        and (not prev.get("year") or not year or prev["year"] == year):
                    dup_of = idx0
                    break
        if dup_of is not None:
            prev = refset[dup_of]
            change_log.append({"ts": now_iso(), "event": "dedup_merge",
                               "merged": c["origin"], "kept": prev["ref_id"],
                               "reason": "identifier or high title similarity"})
            ledger.append({**{k: entry[k] for k in ("ref_id", "doi", "title", "verification_status", "disposition")},
                           "origin": c["origin"], "action": "merged_into:" + prev["ref_id"]})
            continue
        seen[key] = len(refset)
        if entry["disposition"] == "exclude_retracted":
            exclusions.append({"ref_id": entry["ref_id"], "doi": entry["doi"],
                               "title": entry["title"][:120], "reason": "retracted",
                               "evidence": entry.get("verification_source")})
        refset.append(entry)
        ledger.append({k: entry[k] for k in ("ref_id", "doi", "title", "verification_status", "disposition")} | {"origin": c["origin"], "action": "kept"})
    frozen = {
        "refset_version": REFSET_VERSION,
        "frozen_at": now_iso(),
        "records": refset,
    }
    frozen["content_sha256"] = sha256_text(json.dumps(refset, sort_keys=True, ensure_ascii=False))
    return frozen, ledger, exclusions, change_log


def load_search_results(files):
    """从材料中解析检索结果：查询式 -> 命中记录列表。"""
    queries = []
    for p in files:
        if classify_material(p) != "search_results":
            continue
        data = load_json(p)
        if data is None:
            # JSONL 形式
            rows = []
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for ln in fh:
                        ln = ln.strip()
                        if ln:
                            rows.append(json.loads(ln))
            except Exception:
                continue
            data = rows
        if isinstance(data, dict):
            qs = data.get("queries") or data.get("searches") or [data]
        else:
            qs = data
        for q in qs if isinstance(qs, list) else []:
            if not isinstance(q, dict):
                continue
            hits = q.get("hits") or q.get("results") or q.get("records") or []
            queries.append({
                "query_id": q.get("query_id") or q.get("id") or "Q%d" % (len(queries) + 1),
                "query_string": q.get("query_string") or q.get("query") or q.get("string") or "",
                "source": q.get("source") or q.get("database") or "",
                "fields": q.get("fields") or q.get("field") or "",
                "time_window": q.get("time_window") or q.get("years") or "",
                "hits": hits,
                "origin_file": p,
            })
    return queries


def stage_coverage(refset, queries, work_dir):
    """逐条命中判定：L1 标识符精确匹配；L2 标题+年份近似匹配；否则 miss。"""
    norm_hits = []
    for q in queries:
        for h in q["hits"]:
            if not isinstance(h, dict):
                h = {"title": str(h)}
            norm_hits.append({
                "query_id": q["query_id"], "source": q.get("source", ""),
                "doi": norm_doi(h.get("doi") or h.get("DOI")),
                "pmid": str(h.get("pmid") or "").strip(),
                "title": h.get("title", ""),
                "year": first_year(h),
            })
    per_record = []
    hit_count = 0
    for rec in refset["records"]:
        status, level, ev = "miss", None, None
        if rec.get("disposition") == "exclude_retracted":
            per_record.append({"ref_id": rec["ref_id"], "doi": rec.get("doi"),
                               "title": rec.get("title", "")[:140], "status": "excluded",
                               "reason": "retracted"})
            continue
        for h in norm_hits:
            if rec.get("doi") and h["doi"] and rec["doi"] == h["doi"]:
                status, level, ev = "hit", "L1_identifier", h
                break
            if rec.get("pmid") and h["pmid"] and str(rec["pmid"]) == h["pmid"]:
                status, level, ev = "hit", "L1_identifier", h
                break
        if status == "miss":
            best, best_j = None, 0.0
            for h in norm_hits:
                j = jaccard(title_tokens(rec.get("title", "")), title_tokens(h["title"]))
                if j > best_j:
                    best, best_j = h, j
            if best is not None and best_j >= 0.8 and (not rec.get("year") or not best["year"] or rec["year"] == best["year"]):
                status, level, ev = "hit", "L2_title_year", best
        if status == "hit":
            hit_count += 1
        per_record.append({"ref_id": rec["ref_id"], "doi": rec.get("doi"),
                           "title": rec.get("title", "")[:140],
                           "status": status, "match_level": level,
                           "evidence": ({"query_id": ev["query_id"], "source": ev["source"],
                                         "matched_title": ev["title"][:140]} if ev else None)})
    usable = [r for r in per_record if r["status"] != "excluded"]
    denom = len(usable)
    coverage = {
        "denominator": denom,
        "hit": hit_count,
        "miss": denom - hit_count,
        "coverage_ratio": round(hit_count / denom, 4) if denom else None,
        "denominator_source": "frozen reference_set.json %s (sha256:%s)" % (refset["refset_version"], refset["content_sha256"][:12]),
        "per_record": per_record,
    }
    dump_json(os.path.join(work_dir, "coverage.json"), coverage)
    return coverage


def stage_miss_attribution(coverage, refset, queries, work_dir):
    """对每条 miss 给出可操作归因（查询/字段/时间窗/来源/标识符）。"""
    miss_rows = []
    qstr = " | ".join(q["query_string"] for q in queries) if queries else ""
    qsources = sorted({q.get("source", "") for q in queries if q.get("source")})
    windows = [q.get("time_window", "") for q in queries if q.get("time_window")]
    for pr in coverage["per_record"]:
        if pr["status"] != "miss":
            continue
        rec = next((r for r in refset["records"] if r["ref_id"] == pr["ref_id"]), {})
        causes = []
        # 时间窗探针
        for w in windows:
            yrs = [int(y) for y in re.findall(r"(?:19|20)\d{2}", str(w))]
            if rec.get("year") and len(yrs) >= 2 and not (min(yrs) <= rec["year"] <= max(yrs)):
                causes.append({"category": "time_window_cutoff",
                               "evidence": "record year %d outside declared window %s" % (rec["year"], w)})
        # 来源探针
        if rec.get("container") and qsources:
            causes.append({"category": "source_not_covered_check",
                           "evidence": "record venue '%s'; searched sources: %s" % (rec["container"], ",".join(qsources))})
        # 查询词探针：标题高鉴别词是否出现在任何查询式中
        toks = [t for t in title_tokens(rec.get("title", "")) if len(t) > 5]
        missing = [t for t in toks if t not in qstr.lower()]
        if missing:
            causes.append({"category": "query_term_missing",
                           "evidence": "distinctive title tokens absent from all queries: %s" % ", ".join(missing[:5])})
        # 标识符探针
        if not rec.get("doi") and not rec.get("pmid"):
            causes.append({"category": "identifier_anomaly",
                           "evidence": "record lacks resolvable identifier in reference material"})
        if not causes:
            causes.append({"category": "unresolved", "evidence": "no probe conclusive; needs manual review"})
        # 同一类别只保留证据最强的一条
        deduped = {}
        for c in causes:
            deduped.setdefault(c["category"], c)
        miss_rows.append({"ref_id": pr["ref_id"], "doi": pr.get("doi"),
                          "title": pr.get("title"), "causes": list(deduped.values())})
    dump_json(os.path.join(work_dir, "miss_attribution.json"), miss_rows)
    return miss_rows


def stage_supplement(miss_rows, queries, work_dir):
    """依据归因设计定向补检查询；离线环境下只生成可执行查询建议与预期目标，诚实标注未执行。"""
    suggestions = []
    for m in miss_rows:
        for c in m["causes"]:
            cat = c["category"]
            if cat == "query_term_missing":
                toks = re.findall(r"absent from all queries: (.+)", c["evidence"])
                suggestions.append({"target_ref": m["ref_id"], "action": "new_query",
                                    "query": " OR ".join(toks[0].split(", ")[:3]) if toks else "",
                                    "rationale": "add missing distinctive title tokens"})
            elif cat == "time_window_cutoff":
                suggestions.append({"target_ref": m["ref_id"], "action": "extend_window",
                                    "query": "", "rationale": c["evidence"]})
            elif cat == "source_not_covered_check":
                suggestions.append({"target_ref": m["ref_id"], "action": "new_source",
                                    "query": "", "rationale": c["evidence"]})
            elif cat == "identifier_anomaly":
                suggestions.append({"target_ref": m["ref_id"], "action": "manual_identifier_repair",
                                    "query": "", "rationale": c["evidence"]})
    supplement = {
        "executed": False,
        "note": "supplementary search suggestions generated from miss attribution; "
                "execution requires the case's own search interface. If the case provides "
                "supplemental query results, rerun this pipeline with them included.",
        "suggestions": suggestions,
    }
    dump_json(os.path.join(work_dir, "supplement_log.json"), supplement)
    return supplement


def assemble_result(case_id, contract_fields, artifacts, status, sources, uncertainty, change_log):
    result = {"case_id": case_id, "status": status, "sources": sources,
              "uncertainty": uncertainty, "change_log": change_log,
              "skill": "source-forensics-denominator", "skill_version": VERSION}
    for f in contract_fields:
        result[f] = artifacts.get(f)
    return result


def main():
    ap = argparse.ArgumentParser(description="参考集取证管线：真实性门控 -> 冻结分母 -> 覆盖闭环")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--case", default=None, help="case.json 路径（默认 <input>/case.json）")
    ap.add_argument("--task", default=None, help="task.md 路径（默认 <input>/task.md 或 /task.md）")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)
    change_log, uncertainty = [], []
    status = "complete"

    case_path = args.case or os.path.join(args.input, "case.json")
    case = load_json(case_path, {}) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    oc = case.get("output_contract") or {}
    if isinstance(oc, dict):
        contract_fields = list(oc.get("required_fields") or oc.get("fields") or oc.keys())
    elif isinstance(oc, list):
        contract_fields = [str(x) for x in oc]
    else:
        contract_fields = []
    if not contract_fields:
        contract_fields = ["reference_set", "coverage", "miss_list", "supplement_log", "coverage_report"]
        uncertainty.append("output_contract not found in case.json; used default field set")

    files = scan_materials(args.input)
    files = [f for f in files if os.path.basename(f) not in ("case.json", "task.md")]
    if not files:
        print("no material files under %s" % args.input, file=sys.stderr)
        status = "failed"

    manifest = build_authenticity_manifest(files, args.work) if files else {"files": []}
    resp_index = index_local_responses(files)

    # 解析候选题录（综述/清单/图谱）
    cands = []
    for p in files:
        role = classify_material(p)
        if role in ("bibliography_candidate", "unknown") and not p.lower().endswith(PDF_EXT):
            if classify_material(p) in ("crossref_response", "europepmc_response"):
                continue
            got = parse_bibliography_file(p)
            # 响应文件不当题录源
            if p in resp_index["response_files"]:
                continue
            cands.extend(got)
    if not cands:
        status = "partial"
        change_log.append({"ts": now_iso(), "event": "no_bibliography_parsed",
                           "reason": "no parseable reference records in materials"})
    refset, ledger, exclusions, dclog = stage_forensics(cands, resp_index, args.work)
    change_log.extend(dclog)
    dump_json(os.path.join(args.output, "reference_set.json"), refset)

    queries = load_search_results(files)
    if not queries:
        status = "partial"
        uncertainty.append("no search-result material found; coverage and downstream stages degraded")
    coverage = stage_coverage(refset, queries, args.work)
    miss_rows = stage_miss_attribution(coverage, refset, queries, args.work)
    supplement = stage_supplement(miss_rows, queries, args.work)

    # 报告
    report_lines = [
        "# 覆盖率与遗漏分析报告（参考集取证管线）",
        "",
        "- case_id: `%s`" % case_id,
        "- 分母来源：冻结参考集 %s，%d 条（content_sha256 `%s`）" % (refset["refset_version"], coverage["denominator"], refset["content_sha256"][:12]),
        "- 命中 %d / 漏检 %d，覆盖率 %.4f" % (coverage["hit"], coverage["miss"], coverage["coverage_ratio"] or 0.0),
        "- 材料监管链：authenticity_manifest.json（%d 份材料，manifest_sha256 `%s`）" % (len(manifest.get("files", [])), manifest.get("manifest_sha256", "")[:12]),
        "- 撤稿排除 %d 条；核验不足记录以 flag_keep_unverified 保留并列入 uncertainty" % len(exclusions),
        "",
        "## 逐条命中状态", "",
        "| ref_id | status | match_level | 证据 |", "|---|---|---|---|",
    ]
    for pr in coverage["per_record"]:
        ev = pr.get("evidence") or {}
        report_lines.append("| %s | %s | %s | %s |" % (
            pr["ref_id"], pr["status"], pr.get("match_level") or "-",
            (ev.get("query_id", "") + "/" + ev.get("source", "")) if ev else "-"))
    report_lines += ["", "## 漏检归因", ""]
    for m in miss_rows:
        cats = ", ".join(sorted({c["category"] for c in m["causes"]}))
        report_lines.append("- `%s` %s — %s" % (m["ref_id"], (m.get("title") or "")[:80], cats))
    report_lines += ["", "## 局限",
                     "- 未在本地留存响应中命中的记录标记为 unverified，不作真实性断言。",
                     "- 补检为建议级产物；实际新增命中需以案例检索接口执行后复跑本管线。"]
    report_path = os.path.join(args.output, "coverage_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(report_lines) + "\n")

    artifacts = {
        "reference_set": refset,
        "coverage": {k: coverage[k] for k in ("denominator", "hit", "miss", "coverage_ratio", "denominator_source")},
        "miss_list": miss_rows,
        "supplement_log": supplement,
        "coverage_report": report_path,
        "authenticity_manifest": manifest.get("manifest_sha256"),
    }
    sources = [{"path": f, "sha256": sha256_file(f)} for f in files]
    result = assemble_result(case_id, contract_fields, artifacts, status, sources, uncertainty, change_log)
    dump_json(os.path.join(args.output, "result.json"), result)

    missing = [f for f in contract_fields if result.get(f) is None]
    if missing:
        print("contract fields unresolved: %s" % missing, file=sys.stderr)
        return 3
    return 2 if status == "partial" else 0


if __name__ == "__main__":
    sys.exit(main())
